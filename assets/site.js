/* Opens and closes the phone menu, and loads the Google Calendar only when asked. The rest of the site works without JavaScript. */
(function () {
  // Calendar page: the Google Calendar frame loads only after a click, so Google is not contacted until then.
  var gate = document.getElementById("cal-gate");
  var load = document.getElementById("cal-load");
  if (gate && load) {
    load.hidden = false;
    load.addEventListener("click", function () {
      // Only a Google Calendar embed address is ever put in the frame.
      var src;
      try { src = new URL(gate.getAttribute("data-src"), location.href); } catch (e) { return; }
      if (src.protocol !== "https:" || src.hostname !== "calendar.google.com" || src.pathname.indexOf("/calendar/") !== 0) return;
      var frame = document.createElement("iframe");
      frame.className = "cal-frame";
      frame.title = "Calendar";
      frame.src = src.href;
      gate.replaceWith(frame);
      frame.focus();
    });
  }
})();
(function () {
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (!toggle || !nav) return;
  function setOpen(open) {
    nav.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }
  toggle.addEventListener("click", function () {
    setOpen(!nav.classList.contains("open"));
  });
  // Escape closes the menu and puts focus back on the menu button.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && nav.classList.contains("open")) {
      setOpen(false);
      toggle.focus();
    }
  });
})();
