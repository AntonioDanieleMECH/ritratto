/* ADN Creations shop - fetches products and renders cards, FR/EN aware.
   Buyable products go in #productGrid; in-the-works products go in the
   #soonGrid "coming soon" strip. Re-renders on language toggle. */
(function () {
  "use strict";

  var grid = document.getElementById("productGrid");
  var soonGrid = document.getElementById("soonGrid");
  var soonSection = document.getElementById("soonSection");
  var tabs = document.getElementById("deptTabs");
  var cache = [];

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function T(k) { return window.adnT(k); }
  function lang() { return window.adnGetLang ? window.adnGetLang() : "fr"; }
  function loc(p, field) {
    if (lang() === "fr" && (p[field + "_fr"] || "").trim()) return p[field + "_fr"];
    return p[field] || "";
  }

  function deptLabel(d) {
    var map = {
      religious: { fr: "Religieux", en: "Religious" },
      electronic: { fr: "Électronique", en: "Electronic" },
      gag: { fr: "Humour", en: "Gag" }
    };
    return (map[d] || {})[lang()] || d;
  }

  function trunc(s, n) {
    s = String(s || "").trim();
    if (s.length <= n) return s;
    return s.slice(0, n).replace(/\s+\S*$/, "") + "...";
  }

  function mediaHTML(p, name) {
    var photos = p.photos || [];
    var first = photos.length ? photos[0].photo : p.photo;
    var kind = photos.length ? (photos[0].kind || "photo") : "photo";
    if (first && kind === "video") {
      return '<div class="card-media"><video src="' + esc(first) + '" muted preload="metadata" playsinline style="width:100%"></video></div>';
    }
    return first
      ? '<div class="card-media"><img src="' + esc(first) + '" alt="' + esc(name) + '" loading="lazy"></div>'
      : '<div class="card-media"><div class="photo-placeholder">' + esc(T("photo.soon")) + "</div></div>";
  }

  function cardHTML(p) {
    var name = loc(p, "name");
    var tags = (p.depts || [])
      .map(function (d) { return '<span class="dept-tag">' + esc(deptLabel(d)) + "</span>"; })
      .join("");

    var badges = "";
    if (p.in_works) badges += '<span class="badge badge-stock">' + esc(T("js.in_works")) + "</span>";
    if (p.preorder) badges += '<span class="badge badge-preorder">' + esc(T("js.preorder")) + "</span>";
    if (p.stock != null && p.stock <= 3 && p.purchasable && !p.in_works) {
      badges += '<span class="badge badge-stock">' + esc(T("js.only_left").replace("{n}", p.stock)) + "</span>";
    }
    if (!p.purchasable && !p.in_works) badges += '<span class="badge badge-soon">' + esc(T("js.coming_soon")) + "</span>";
    var badgeRow = badges ? '<div style="display:flex;gap:6px;flex-wrap:wrap">' + badges + "</div>" : "";

    var links = '<a class="btn btn-sm btn-outline" href="/product/' + esc(p.id) + '">' + esc(T("js.view")) + "</a>";
    if (p.custom_link && p.purchasable && !p.in_works) {
      links += ' <a class="btn btn-sm btn-outline" href="' + esc(p.custom_link) + '">' + esc(T("js.design")) + "</a>";
    }
    if (p.in_works) {
      links += ' <a class="btn btn-sm btn-outline" href="/progress.html">' + esc(T("home.build_btn")) + "</a>";
    }
    var foot = '<div class="card-foot"><span class="price">' + esc(p.price) +
      '</span><span style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end">' + links + "</span></div>";

    return '<article class="card">' + mediaHTML(p, name) +
      '<div class="card-body">' +
      '<div class="dept-tags">' + tags + "</div>" +
      "<h3>" + esc(name) + "</h3>" +
      badgeRow +
      "<p>" + esc(trunc(loc(p, "description"), 120)) + "</p>" +
      foot +
      "</div></article>";
  }

  function notice(el, kind, msg) {
    el.innerHTML = '<div class="notice ' + (kind === "err" ? "notice-err" : "") + '">' + esc(msg) + "</div>";
  }

  function currentDept() {
    return new URLSearchParams(window.location.search).get("dept") || "";
  }

  function setActiveTab(dept) {
    var btns = tabs.querySelectorAll(".dept-tab");
    btns.forEach(function (b) {
      b.classList.toggle("active", (b.getAttribute("data-dept") || "") === dept);
    });
  }

  function render() {
    var dept = currentDept();
    var buyable = cache.filter(function (p) { return !p.in_works; });
    var soon = cache.filter(function (p) { return p.in_works; });
    if (!buyable.length) {
      notice(grid, "", T("js.empty"));
    } else {
      grid.innerHTML = buyable.map(cardHTML).join("");
    }
    if (soon.length && soonSection) {
      soonSection.style.display = "";
      soonGrid.innerHTML = soon.map(cardHTML).join("");
    } else if (soonSection) {
      soonSection.style.display = "none";
    }
  }

  async function load() {
    notice(grid, "", T("js.loading"));
    try {
      var dept = currentDept();
      var r = await fetch("/api/products?dept=" + encodeURIComponent(dept));
      if (!r.ok) throw new Error("could not load products");
      var data = await r.json();
      cache = data.products || [];
      setActiveTab(dept);
      render();
    } catch (e) {
      notice(grid, "err", T("js.load_err"));
    }
  }

  tabs.addEventListener("click", function (e) {
    var btn = e.target.closest(".dept-tab");
    if (!btn) return;
    var dept = btn.getAttribute("data-dept") || "";
    setActiveTab(dept);
    var url = new URL(window.location.href);
    if (dept) url.searchParams.set("dept", dept); else url.searchParams.delete("dept");
    window.history.replaceState(null, "", url.toString());
    load();
  });

  window.adnRenderShop = render;
  load();
})();
