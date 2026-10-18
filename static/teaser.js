/* Shared "follow the build" teaser strip for home + shop.
   Shows up to 3 work-in-progress projects that have a photo, linking to /progress.html. */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function loc(row, field) {
    var lang = window.adnGetLang ? window.adnGetLang() : "fr";
    if (lang === "fr" && (row[field + "_fr"] || "").trim()) return row[field + "_fr"];
    return row[field] || "";
  }

  function renderTeaser() {
    var el = document.getElementById("buildStrip");
    if (!el) return;
    fetch("/api/wip").then(function (r) { return r.json(); }).then(function (j) {
      var ps = (j.projects || []).filter(function (p) { return p.photo; }).slice(0, 3);
      if (!ps.length) { el.style.display = "none"; return; }
      el.style.display = "";
      el.innerHTML = ps.map(function (p) {
        var name = loc(p, "project");
        return '<a class="card" href="/progress.html" style="text-decoration:none;color:inherit">' +
          '<div class="card-media"><img src="' + esc(p.photo) + '" alt="' + esc(name) + '" loading="lazy"></div>' +
          '<div class="card-body"><h3>' + esc(name) + "</h3></div></a>";
      }).join("");
    }).catch(function () { el.style.display = "none"; });
  }

  window.adnRenderTeaser = renderTeaser;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderTeaser);
  } else {
    renderTeaser();
  }
})();
