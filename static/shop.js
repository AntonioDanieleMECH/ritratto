/* ADN Creations shop - fetches products and renders cards, FR/EN aware.
   Buyable products go in #productGrid; in-the-works products go in the
   #soonGrid "coming soon" strip. Re-renders on language toggle. */
(function () {
  "use strict";

  var sectionsEl = document.getElementById("shopSections");
  var soonGrid = document.getElementById("soonGrid");
  var soonSection = document.getElementById("soonSection");
  var searchEl = document.getElementById("shopSearch");
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
      italian: { fr: "Italien", en: "Italian" },
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
    var detailUrl = "/product/" + esc(p.id);
    var tags = (p.depts || [])
      .map(function (d) { return '<span class="dept-tag">' + esc(deptLabel(d)) + "</span>"; })
      .join("");
    var mediaLink = '<a href="' + detailUrl + '" class="card-media-link" aria-label="' +
      esc(T("js.view")) + ": " + esc(name) + '">' + mediaHTML(p, name) + "</a>";
    var titleLink = '<a href="' + detailUrl + '" class="card-title-link">' + esc(name) + "</a>";

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

    return '<article class="card">' + mediaLink +
      '<div class="card-body">' +
      '<div class="dept-tags">' + tags + "</div>" +
      "<h3>" + titleLink + "</h3>" +
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

  /* Category divisors, religious first (Antonio 2026-10-20). Each product
     lands in the first section it matches; the search bar filters all. */
  var SECTIONS = [
    { key: "religious", title: "shop.sec_religious", has: function (p) { return (p.depts || []).indexOf("religious") >= 0; } },
    { key: "italian", title: "shop.sec_italian", has: function (p) { return (p.depts || []).indexOf("italian") >= 0; } },
    { key: "gag", title: "shop.sec_gag", has: function (p) { return (p.depts || []).indexOf("gag") >= 0; } },
    { key: "more", title: "shop.sec_more", has: function () { return true; } }
  ];

  function matchesSearch(p, q) {
    if (!q) return true;
    var hay = ((p.name || "") + " " + (p.name_fr || "") + " " +
      (p.description || "") + " " + (p.description_fr || "")).toLowerCase();
    return hay.indexOf(q) >= 0;
  }

  function sectionHTML(title, items) {
    return '<div class="shop-sec-head"><h2>' + esc(title) + '</h2></div>' +
      '<div class="grid grid-3">' + items.map(cardHTML).join("") + "</div>";
  }

  function render() {
    var dept = currentDept();
    var q = searchEl ? searchEl.value.trim().toLowerCase() : "";
    var buyable = cache.filter(function (p) { return !p.in_works && (p.price_cents || 0) > 0; });
    var soon = cache.filter(function (p) { return p.in_works; });
    var pool = buyable.filter(function (p) { return matchesSearch(p, q); });
    var html = "";
    if (dept) {
      var inDept = pool.filter(function (p) { return (p.depts || []).indexOf(dept) >= 0; });
      if (inDept.length) html = sectionHTML(deptLabel(dept), inDept);
    } else {
      var used = {};
      SECTIONS.forEach(function (s) {
        var items = pool.filter(function (p) { return !used[p.id] && s.has(p); });
        items.forEach(function (p) { used[p.id] = 1; });
        if (items.length) html += sectionHTML(T(s.title), items);
      });
    }
    if (!html) {
      html = '<div class="notice">' + esc(q ? T("shop.no_results") : T("js.empty")) + "</div>";
    }
    sectionsEl.innerHTML = html;
    if (soon.length && soonSection) {
      soonSection.style.display = "";
      soonGrid.innerHTML = soon.map(cardHTML).join("");
    } else if (soonSection) {
      soonSection.style.display = "none";
    }
  }

  async function load() {
    notice(sectionsEl, "", T("js.loading"));
    try {
      var r = await fetch("/api/products");
      if (!r.ok) throw new Error("could not load products");
      var data = await r.json();
      cache = data.products || [];
      render();
    } catch (e) {
      notice(sectionsEl, "err", T("js.load_err"));
      var rb = document.createElement("button");
      rb.className = "btn btn-outline"; rb.style.marginTop = "12px";
      rb.textContent = lang() === "fr" ? "Réessayer" : "Retry";
      rb.addEventListener("click", load);
      sectionsEl.appendChild(rb);
    }
  }

  if (searchEl) searchEl.addEventListener("input", render);

  window.adnRenderShop = render;
  load();
})();
