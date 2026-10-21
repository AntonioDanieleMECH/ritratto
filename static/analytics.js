/* ADN Creations first-party analytics: pageviews, sources, navigation paths,
   outbound clicks. No cookies; ids live in session/local storage only. */
(function () {
  try {
    var sid = sessionStorage.getItem("adn_sid");
    if (!sid) {
      sid = Math.random().toString(36).slice(2) + Date.now().toString(36);
      sessionStorage.setItem("adn_sid", sid);
    }
    var vid = localStorage.getItem("adn_vid");
    if (!vid) {
      vid = Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem("adn_vid", vid);
    }
    function send(p) {
      p.sid = sid; p.vid = vid;
      var body = JSON.stringify(p);
      if (navigator.sendBeacon) {
        navigator.sendBeacon("/api/track", new Blob([body], { type: "application/json" }));
      } else {
        fetch("/api/track", { method: "POST", body: body, headers: { "Content-Type": "application/json" }, keepalive: true }).catch(function () {});
      }
    }
    var q = new URLSearchParams(location.search);
    send({
      type: "pageview",
      path: location.pathname,
      ref: document.referrer || "",
      utm_source: q.get("utm_source") || "",
      utm_medium: q.get("utm_medium") || "",
      utm_campaign: q.get("utm_campaign") || "",
      tz: (window.Intl && Intl.DateTimeFormat().resolvedOptions().timeZone) || "",
      lang: navigator.language || ""
    });
    document.addEventListener("click", function (e) {
      var a = e.target && e.target.closest ? e.target.closest("a") : null;
      if (!a || !a.href) return;
      try {
        var u = new URL(a.href, location.href);
        if (u.host && u.host !== location.host) {
          send({ type: "outbound", path: location.pathname, target: u.host + u.pathname });
        }
      } catch (_) {}
    });
  } catch (e) {}
})();
