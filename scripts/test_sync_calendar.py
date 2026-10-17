"""Tests for scripts/sync_calendar.py:  python3 -m unittest discover -s scripts -p "test_*.py" """
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_calendar as sc

FEED = """BEGIN:VCALENDAR
VERSION:2.0
X-WR-TIMEZONE:America/New_York
BEGIN:VEVENT
UID:meet@x
DTSTART;TZID=America/New_York:20261001T183000
DTEND;TZID=America/New_York:20261001T200000
RRULE:FREQ=MONTHLY;BYDAY=1TH,3TH
EXDATE;TZID=America/New_York:20261015T183000
SUMMARY:Pack Meeting
LOCATION:Covington-Harper Elementary\\, 2500 River Heritage Blvd
DESCRIPTION:Bring your handbook. Call Pat at 555-0100.
BEGIN:VALARM
TRIGGER:-PT10M
ACTION:DISPLAY
DESCRIPTION:Reminder
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:meet@x
RECURRENCE-ID;TZID=America/New_York:20261105T183000
DTSTART;TZID=America/New_York:20261105T190000
DTEND;TZID=America/New_York:20261105T203000
SUMMARY:Pack Meeting (Pinewood Derby)
DESCRIPTION:Public: Build night\\, bring your car.
END:VEVENT
BEGIN:VEVENT
UID:camp@x
DTSTART;VALUE=DATE:20261113
DTEND;VALUE=DATE:20261115
SUMMARY:Fall Campout
END:VEVENT
BEGIN:VEVENT
UID:utc@x
DTSTART:20261201T230000Z
DTEND:20261202T010000Z
SUMMARY:Holiday Service
END:VEVENT
BEGIN:VEVENT
UID:priv@x
DTSTART;VALUE=DATE:20261120
CLASS:PRIVATE
SUMMARY:Leaders Only
END:VEVENT
BEGIN:VEVENT
UID:gone@x
DTSTART;VALUE=DATE:20261121
STATUS:CANCELLED
SUMMARY:Cancelled Thing
END:VEVENT
BEGIN:VEVENT
UID:old@x
DTSTART;VALUE=DATE:20260901
SUMMARY:Already Happened
END:VEVENT
BEGIN:VEVENT
UID:fold@x
DTSTART;VALUE=DATE:20261210
SUMMARY:A very long title that the calendar folded onto a second line because it was too
  long
END:VEVENT
END:VCALENDAR
"""
TODAY = dt.date(2026, 10, 17)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.ev = sc.build_events(FEED, TODAY, 90)
        self.by = {(e["date"], e["title"]): e for e in self.ev}

    def test_monthly_rule_with_exdate_and_override(self):
        dates = [e["date"] for e in self.ev if e["title"].startswith("Pack Meeting")]
        self.assertEqual(dates, ["2026-11-05", "2026-11-19", "2026-12-03", "2026-12-17", "2027-01-07"][:len(dates)])
        self.assertNotIn("2026-10-15", dates)                       # EXDATE
        self.assertIn(("2026-11-05", "Pack Meeting (Pinewood Derby)"), self.by)   # moved instance replaced the normal one
        self.assertNotIn(("2026-11-05", "Pack Meeting"), self.by)
        moved = self.by[("2026-11-05", "Pack Meeting (Pinewood Derby)")]
        self.assertEqual((moved["start"], moved["end"]), ("19:00", "20:30"))

    def test_times_places_and_privacy(self):
        regular = self.by[("2026-11-19", "Pack Meeting")]
        self.assertEqual((regular["start"], regular["end"]), ("18:30", "20:00"))
        self.assertEqual(regular["place"], "Covington-Harper Elementary, 2500 River Heritage Blvd")
        self.assertNotIn("details", regular)                        # description without "Public:" stays private
        self.assertEqual(self.by[("2026-11-05", "Pack Meeting (Pinewood Derby)")]["details"], "Build night, bring your car.")
        titles = [e["title"] for e in self.ev]
        for hidden in ("Leaders Only", "Cancelled Thing", "Already Happened"):
            self.assertNotIn(hidden, titles)

    def test_all_day_range_utc_and_folding(self):
        camp = self.by[("2026-11-13", "Fall Campout")]
        self.assertEqual(camp["end_date"], "2026-11-14")           # DTEND is the day after the last day
        self.assertNotIn("start", camp)
        svc = self.by[("2026-12-01", "Holiday Service")]            # 23:00 UTC is 18:00 Eastern
        self.assertEqual((svc["start"], svc["end"]), ("18:00", "20:00"))
        self.assertIn(("2026-12-10", "A very long title that the calendar folded onto a second line because it was too long"), self.by)

    def test_window_and_sorting(self):
        self.assertTrue(all(e["date"] <= "2027-01-15" for e in self.ev))
        self.assertEqual(self.ev, sorted(self.ev, key=lambda e: (e["date"], e.get("start", ""), e["title"].lower())))

    def test_weekly_count_until_and_interval(self):
        feed = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nDTSTART;VALUE=DATE:20261015\nRRULE:FREQ=WEEKLY;INTERVAL=2;COUNT=3\nSUMMARY:Biweekly\nEND:VEVENT\n"
                "BEGIN:VEVENT\nUID:b\nDTSTART;VALUE=DATE:20261016\nRRULE:FREQ=WEEKLY;BYDAY=FR;UNTIL=20261030\nSUMMARY:Fridays\nEND:VEVENT\nEND:VCALENDAR\n")
        out = sc.build_events(feed, TODAY, 60)
        self.assertEqual([e["date"] for e in out if e["title"] == "Biweekly"], ["2026-10-29", "2026-11-12"])  # 10/15 already passed
        self.assertEqual([e["date"] for e in out if e["title"] == "Fridays"], ["2026-10-23", "2026-10-30"])

    def test_last_friday_setpos_and_negative_ordinal(self):
        feed = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nDTSTART;VALUE=DATE:20261001\nRRULE:FREQ=MONTHLY;BYDAY=-1FR\nSUMMARY:Last Friday\nEND:VEVENT\nEND:VCALENDAR\n")
        out = sc.build_events(feed, TODAY, 70)
        self.assertEqual([e["date"] for e in out], ["2026-10-30", "2026-11-27", "2026-12-25"])

    def test_junk_in_does_not_crash(self):
        self.assertEqual(sc.build_events("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:garbage\nSUMMARY:x\nEND:VEVENT\nEND:VCALENDAR", TODAY, 30), [])


if __name__ == "__main__":
    unittest.main()
