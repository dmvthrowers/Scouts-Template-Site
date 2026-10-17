#!/usr/bin/env python3
"""Pull upcoming events from a Google Calendar (or any iCalendar feed) into events.generated.json.

    CALENDAR_ICS_URL="https://calendar.google.com/calendar/ical/.../basic.ics" python3 scripts/sync_calendar.py

The deploy workflow runs this before every build, with the address kept in a repository secret. build.py then
merges the file into the Calendar page, the home page, the Event data for search engines, and calendar.ics.
Standard library only (Python 3.9+).

Safe by default:
  - No address set, or the feed can't be read: nothing is written and the site builds from site.jsonc alone.
  - Only the title, date, time and place are taken. A description is published only when it starts with
    "Public:" (everything after that word is used); otherwise it stays on the calendar.
  - Events marked Private or Confidential, and cancelled events, are skipped.
  - The address is never printed.

Options (or environment variables):
  --url / CALENDAR_ICS_URL   the feed address (https only)
  --file PATH                read a local .ics file instead (for testing)
  --tz / CALENDAR_TZ         the group's time zone, e.g. America/New_York (default: the feed's own, else as written)
  --days N                   how far ahead to look (default 180)
  --out PATH                 where to write (default: events.generated.json next to build.py)
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:                                                  # pragma: no cover (Python < 3.9)
    ZoneInfo = None

ROOT = Path(__file__).resolve().parent.parent
WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
MAX_STEPS = 5000


# ---------------------------------------------------------------- reading the feed

def unfold(text):
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def split_params(head):
    """'DTSTART;TZID=America/New_York;VALUE=DATE-TIME' -> ('DTSTART', {'TZID': ..., 'VALUE': ...})."""
    parts, cur, quoted = [], "", False
    for ch in head:
        if ch == '"':
            quoted = not quoted
        if ch == ";" and not quoted:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    params = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v.strip('"')
    return parts[0].upper(), params


def unescape(value):
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


def parse_events(text):
    """Returns (list of raw event dicts, calendar time zone name or None). Each prop is (value, params)."""
    events, cal_tz, cur, skip_depth = [], None, None, 0
    for line in unfold(text):
        if not line:
            continue
        head, _, value = line.partition(":")
        name, params = split_params(head)
        if name == "BEGIN":
            if value.upper() == "VEVENT":
                cur = {}
            elif cur is not None:
                skip_depth += 1                                      # a VALARM or similar inside the event
            continue
        if name == "END":
            if value.upper() == "VEVENT" and cur is not None and skip_depth == 0:
                events.append(cur)
                cur = None
            elif skip_depth:
                skip_depth -= 1
            continue
        if name == "X-WR-TIMEZONE" and cur is None:
            cal_tz = value.strip()
        if cur is not None and not skip_depth:
            cur.setdefault(name, []).append((value, params))
    return events, cal_tz


def first(ev, name):
    return ev[name][0] if ev.get(name) else (None, {})


def zone(name):
    if not name or ZoneInfo is None:
        return None
    try:
        return ZoneInfo(name)
    except Exception:                                                # unknown zone name
        return None


def to_local(value, params, tz):
    """Parse a DATE or DATE-TIME. Returns (date or naive datetime, is_all_day) in the group's wall-clock time."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return dt.datetime.strptime(value[:8], "%Y%m%d").date(), True
    utc = value.endswith("Z")
    naive = dt.datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    src = zone("UTC") if utc else zone(params.get("TZID"))
    if src is not None and tz is not None:
        return naive.replace(tzinfo=src).astimezone(tz).replace(tzinfo=None), False
    return naive, False


# ---------------------------------------------------------------- repeating events

def parse_rrule(value):
    rule = {}
    for part in value.split(";"):
        k, _, v = part.partition("=")
        rule[k.upper()] = v
    return rule


def day_spec(token):
    m = re.fullmatch(r"([+-]?\d+)?(MO|TU|WE|TH|FR|SA|SU)", token.strip().upper())
    return (int(m.group(1)) if m.group(1) else 0, WEEKDAYS.index(m.group(2))) if m else None


def month_days(year, month, rule, start):
    """Dates in one month that a monthly (or yearly) rule picks."""
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    days = [dt.date(year, month, d) for d in range(1, (nxt - dt.date(year, month, 1)).days + 1)]
    if rule.get("BYMONTHDAY"):
        want = [int(x) for x in rule["BYMONTHDAY"].split(",")]
        picked = [d for d in days if d.day in want or d.day - len(days) - 1 in want]
    elif rule.get("BYDAY"):
        picked = []
        for spec in filter(None, (day_spec(t) for t in rule["BYDAY"].split(","))):
            n, wd = spec
            same = [d for d in days if d.weekday() == wd]
            if n == 0:
                picked += same
            elif 0 < n <= len(same):
                picked.append(same[n - 1])
            elif n < 0 and -n <= len(same):
                picked.append(same[n])
        picked.sort()
    else:
        picked = [d for d in days if d.day == start.day]
    if rule.get("BYSETPOS") and picked:
        out = []
        for pos in (int(x) for x in rule["BYSETPOS"].split(",")):
            if 0 < pos <= len(picked):
                out.append(picked[pos - 1])
            elif pos < 0 and -pos <= len(picked):
                out.append(picked[pos])
        picked = sorted(set(out))
    return picked


def occurrences(start, rule, horizon):
    """Start times of a repeating event, from its first one up to `horizon` (a datetime). COUNT counts from the first."""
    all_day = not isinstance(start, dt.datetime)
    first_day = start if all_day else start.date()
    clock = dt.time() if all_day else start.time()
    freq = rule.get("FREQ", "")
    step = max(int(rule.get("INTERVAL", "1") or 1), 1)
    count = int(rule["COUNT"]) if rule.get("COUNT") else None
    until = None
    if rule.get("UNTIL"):
        u = rule["UNTIL"]
        until = dt.datetime.strptime(u[:8], "%Y%m%d").date()
    bydays = [d for d in (day_spec(t) for t in rule.get("BYDAY", "").split(",")) if d]

    def days():
        if freq == "DAILY":
            d = first_day
            while True:
                if not bydays or d.weekday() in [wd for _, wd in bydays]:
                    yield d
                d += dt.timedelta(days=step)
        elif freq == "WEEKLY":
            wds = sorted({wd for _, wd in bydays}) or [first_day.weekday()]
            monday = first_day - dt.timedelta(days=first_day.weekday())
            while True:
                for wd in wds:
                    d = monday + dt.timedelta(days=wd)
                    if d >= first_day:
                        yield d
                monday += dt.timedelta(weeks=step)
        elif freq == "MONTHLY":
            y, m = first_day.year, first_day.month
            while True:
                for d in month_days(y, m, rule, first_day):
                    if d >= first_day:
                        yield d
                m += step
                y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        elif freq == "YEARLY":
            y = first_day.year
            months = [int(x) for x in rule["BYMONTH"].split(",")] if rule.get("BYMONTH") else [first_day.month]
            while True:
                for m in months:
                    for d in month_days(y, m, rule, first_day):
                        if d >= first_day:
                            yield d
                y += step
        else:
            yield first_day

    out, n = [], 0
    for d in days():
        n += 1
        if n > MAX_STEPS or (count is not None and len(out) >= count):
            break
        if until and d > until:
            break
        occ = d if all_day else dt.datetime.combine(d, clock)
        if (dt.datetime.combine(d, clock) if not all_day else dt.datetime.combine(d, dt.time())) > horizon:
            break
        out.append(occ)
        if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
            break
    return out


def key_of(value):
    return value.isoformat()


# ---------------------------------------------------------------- turning the feed into site events

def build_events(text, today, days, tz_name=None):
    raw, cal_tz = parse_events(text)
    tz = zone(tz_name or cal_tz)
    horizon = dt.datetime.combine(today + dt.timedelta(days=days), dt.time())
    window_start = dt.datetime.combine(today, dt.time())

    def get(ev, name):
        return first(ev, name)[0]

    def usable(ev):
        if (get(ev, "STATUS") or "").upper() == "CANCELLED":
            return False
        if (get(ev, "CLASS") or "").upper() in ("PRIVATE", "CONFIDENTIAL"):
            return False
        return bool(get(ev, "DTSTART")) and bool((get(ev, "SUMMARY") or "").strip())

    masters, overrides = [], {}
    for ev in raw:
        if not get(ev, "DTSTART"):
            continue
        if get(ev, "RECURRENCE-ID"):
            v, p = first(ev, "RECURRENCE-ID")
            rid, _ = to_local(v, p, tz)
            overrides[(get(ev, "UID"), key_of(rid))] = ev
        else:
            masters.append(ev)

    used, found = set(), []

    def emit(ev, start, end, all_day):
        if (get(ev, "STATUS") or "").upper() == "CANCELLED" or (get(ev, "CLASS") or "").upper() in ("PRIVATE", "CONFIDENTIAL"):
            return
        title = unescape(get(ev, "SUMMARY") or "").strip()
        if not title:
            return
        rec = {"title": title}
        if all_day:
            last = end - dt.timedelta(days=1) if end else start
            if last < today:
                return
            rec["date"] = start.isoformat()
            if last > start:
                rec["end_date"] = last.isoformat()
        else:
            finish = end or start
            if finish < window_start:
                return
            rec["date"] = start.date().isoformat()
            rec["start"] = start.strftime("%H:%M")
            if end and end > start:
                rec["end"] = end.strftime("%H:%M")
                if end.date() > start.date() and not (end.time() == dt.time() and end.date() == start.date() + dt.timedelta(days=1)):
                    rec["end_date"] = end.date().isoformat()
        desc = unescape(get(ev, "DESCRIPTION") or "").strip()
        m = re.match(r"public:\s*(.*)", desc, re.I | re.S)
        if m and m.group(1).strip():
            rec["details"] = " ".join(m.group(1).split())[:300]
        place = " ".join(unescape(get(ev, "LOCATION") or "").split())
        if place:
            rec["place"] = place[:200]
        found.append(rec)

    for ev in masters:
        v, p = first(ev, "DTSTART")
        try:
            start, all_day = to_local(v, p, tz)
        except ValueError:
            continue
        dtend = first(ev, "DTEND")
        end = None
        if dtend[0]:
            try:
                end, _ = to_local(dtend[0], dtend[1], tz)
            except ValueError:
                end = None
        if end is None and get(ev, "DURATION"):
            m = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", get(ev, "DURATION").strip())
            if m:
                w, d, h, mi = (int(x or 0) for x in m.groups())
                end = start + dt.timedelta(weeks=w, days=d, hours=h, minutes=mi)
        length = (end - start) if end is not None else None
        rr = get(ev, "RRULE")
        if rr:
            starts = occurrences(start, parse_rrule(rr), horizon)
            skip = set()
            for value, params in ev.get("EXDATE", []):
                for item in value.split(","):
                    try:
                        skip.add(key_of(to_local(item, params, tz)[0]))
                    except ValueError:
                        pass
            for occ in starts:
                k = key_of(occ)
                if k in skip:
                    continue
                over = overrides.get((get(ev, "UID"), k))
                if over is not None:
                    used.add((get(ev, "UID"), k))
                    emit_override(over, tz, emit)
                else:
                    emit(ev, occ, occ + length if length is not None else None, all_day)
        else:
            emit(ev, start, end, all_day)

    for (uid, k), over in overrides.items():                         # changed instance whose repeating event isn't in the feed
        if (uid, k) not in used and not any(get(m, "UID") == uid and get(m, "RRULE") for m in masters):
            emit_override(over, tz, emit)

    seen, out = set(), []
    for rec in sorted(found, key=lambda r: (r["date"], r.get("start", ""), r["title"].lower())):
        ident = (rec["date"], rec.get("start", ""), rec["title"].lower())
        if ident not in seen and rec["date"] <= horizon.date().isoformat():
            seen.add(ident)
            out.append(rec)
    return out


def emit_override(ev, tz, emit):
    v, p = first(ev, "DTSTART")
    start, all_day = to_local(v, p, tz)
    dtend = first(ev, "DTEND")
    end = to_local(dtend[0], dtend[1], tz)[0] if dtend[0] else None
    emit(ev, start, end, all_day)


# ---------------------------------------------------------------- command line

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("CALENDAR_ICS_URL", ""))
    ap.add_argument("--file")
    ap.add_argument("--tz", default=os.environ.get("CALENDAR_TZ", ""))
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--out", default=str(ROOT / "events.generated.json"))
    ap.add_argument("--today", help="pretend today is YYYY-MM-DD (for testing)")
    args = ap.parse_args()

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.url.strip():
        url = args.url.strip()
        if not url.startswith("https://"):
            print("Calendar sync skipped: the calendar address must start with https://")
            return 0
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "calendar-sync"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read(5_000_000).decode("utf-8", "replace")
        except Exception as e:                                       # never print the address
            print(f"Calendar sync skipped: could not read the calendar ({type(e).__name__}). The site builds from site.jsonc.")
            return 0
        if "BEGIN:VCALENDAR" not in text:
            print("Calendar sync skipped: the address did not return a calendar. Check the secret.")
            return 0
    else:
        print("Calendar sync skipped: no calendar address set (CALENDAR_ICS_URL).")
        return 0

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    events = build_events(text, today, args.days, args.tz or None)
    Path(args.out).write_text(json.dumps({"synced": today.isoformat(), "events": events}, indent=1) + "\n", encoding="utf-8")
    print(f"Calendar sync: {len(events)} upcoming event(s) in the next {args.days} days.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
