/* ADN Creations shop - fetches products and renders cards. */
(function () {
  "use strict";

  var grid = document.getElementById("productGrid");
  var tabs = document.getElementById("deptTabs");

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function deptLabel(d) {
    var map = { religious: "Religious", electronic: "Electronic", gag: "Gag" };
    return map[d] || d;
  }

  function trunc(s, n) {
    s = String(s || "").trim();
    if (s.length <= n) return s;
    return s.slice(0, n).replace(/\s+\S*$/, "") + "...";
  }

  function cardHTML(p) {
    var media = p.photo
      ? '<div class="card-media"><img src="' + esc(p.photo) + '" alt="' +
        esc(p.name) + '" loading="lazy"></div>'
      : '<div class="card-media"><div class="photo-placeholder">Photo coming soon</div></div>';

    var tags = (p.depts || [])
      .map(function (d) { return '<span class="dept-tag">' + esc(deptLabel(d)) + "</span>"; })
      .join("");

    var badges = "";
    if (p.preorder) badges += '<span class="badge badge-preorder">Preorder</span>';
    if (p.stock != null && p.stock <= 3) badges += '<span class="badge badge-stock">Only ' + esc(p.stock) + " left</span>";
    if (!p.purchasable) badges += '<span class="badge badge-soon">Coming soon</span>';
    var badgeRow = badges ? '<div style="display:flex;gap:6px;flex-wrap:wrap">' + badges + "</div>" : "";

    var foot;
    if (p.purchasable) {
      var links = '<a class="btn btn-sm btn-outline" href="/product/' + esc(p.id) + '">View</a>';
      if (p.custom_link) links += ' <a class="btn btn-sm btn-outline" href="' + esc(p.custom_link) + '">Design yours</a>';
      foot = '<div class="card-foot"><span class="price">' + esc(p.price) +
        '</span><span style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end">' + links + "</span></div>";
    } else {
      foot = '<div class="card-foot"><span class="price">' + esc(p.price) + "</span></div>";
    }

    return '<article class="card">' + media +
      '<div class="card-body">' +
      '<div class="dept-tags">' + tags + "</div>" +
      "<h3>" + esc(p.name) + "</h3>" +
      badgeRow +
      "<p>" + esc(trunc(p.description, 120)) + "</p>" +
      foot +
      "</div></article>";
  }

  function notice(kind, msg) {
    grid.innerHTML = '<div class="notice ' + (kind === "err" ? "notice-err" : "") + '">' + esc(msg) + "</div>";
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

  async function load(dept) {
    notice("", "Loading the collection...");
    try {
      var r = await fetch("/api/products?dept=" + encodeURIComponent(dept));
      if (!r.ok) throw new Error("could not load products");
      var data = await r.json();
      var products = data.products || [];
      if (!products.length) {
        notice("", "Nothing in this department yet. Check back soon.");
        return;
      }
      grid.innerHTML = products.map(cardHTML).join("");
    } catch (e) {
      notice("err", "Sorry, the shop could not be loaded. Please refresh the page and try again.");
    }
  }

  tabs.addEventListener("click", function (e) {
    var btn = e.target.closest(".dept-tab");
    if (!btn) return;
    var dept = btn.getAttribute("data-dept") || "";
    setActiveTab(dept);
    var url = dept ? "/shop.html?dept=" + encodeURIComponent(dept) : "/shop.html";
    window.history.replaceState(null, "", url);
    load(dept);
  });

  var initial = currentDept();
  setActiveTab(initial);
  load(initial);
})();
