/* ADN Creations store admin - drives the server-rendered /admin/ page.
   ADMIN_TOKEN is defined as a global on the page. Every call sends ?token=. */
(function () {
  "use strict";

  var TOKEN = typeof ADMIN_TOKEN !== "undefined" ? ADMIN_TOKEN : "";
  var FB_PAGE = "https://www.facebook.com/61592937237761";
  var DEPTS = [
    { v: "religious", l: "Religious" },
    { v: "electronic", l: "Electronic" },
    { v: "gag", l: "Gag" }
  ];

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function $(id) { return document.getElementById(id); }

  function cardOf(el) { return el.closest(".admin-card"); }

  function noticeEl(card) {
    var n = card.querySelector(".card-notice");
    if (!n) {
      n = document.createElement("div");
      n.className = "card-notice";
      n.style.display = "none";
      card.insertBefore(n, card.firstChild);
    }
    return n;
  }

  function showErr(el, msg) {
    var card = cardOf(el);
    if (!card) return;
    var n = noticeEl(card);
    n.style.display = "block";
    n.className = "card-notice notice notice-err";
    n.textContent = msg;
    n.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function showOk(el, msg) {
    var card = cardOf(el);
    if (!card) return;
    var n = noticeEl(card);
    n.style.display = "block";
    n.className = "card-notice notice notice-ok";
    n.textContent = msg;
  }

  function clearNotice(el) {
    var card = cardOf(el);
    if (!card) return;
    var n = card.querySelector(".card-notice");
    if (n) { n.style.display = "none"; n.innerHTML = ""; }
  }

  async function call(path, opts) {
    opts = opts || {};
    var sep = path.indexOf("?") >= 0 ? "&" : "?";
    var r = await fetch(path + sep + "token=" + encodeURIComponent(TOKEN), opts);
    var data = null;
    try { data = await r.json(); } catch (e) { /* non-JSON */ }
    if (!r.ok) throw new Error((data && data.error) || "Request failed (" + r.status + ")");
    if (data && data.error) throw new Error(data.error);
    return data || {};
  }

  function jpost(path, body) {
    return call(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }

  function money(cents) { return "$" + (Number(cents || 0) / 100).toFixed(2); }

  function fmtDate(iso) {
    if (!iso) return "-";
    var d = new Date(iso);
    return isNaN(d) ? esc(iso) : d.toLocaleString();
  }

  function parseDepts(p) {
    var d = p.depts;
    if (Array.isArray(d)) return d;
    try { return JSON.parse(d || "[]"); } catch (e) { return []; }
  }

  function deptName(v) {
    var f = DEPTS.filter(function (d) { return d.v === v; })[0];
    return f ? f.l : v;
  }

  function tableWrap(html) {
    return '<div style="overflow-x:auto">' + html + "</div>";
  }

  /* ---------------- share ---------------- */

  function shareBlock(kind, id) {
    var wrap = document.createElement("div");
    wrap.className = "share-draft";
    return wrap;
  }

  async function doShare(kind, id, anchorEl) {
    var card = cardOf(anchorEl);
    clearNotice(anchorEl);
    var old = card.querySelectorAll(".share-draft");
    old.forEach(function (n) { n.remove(); });
    try {
      var draft = await call("/api/admin/share-draft?kind=" + encodeURIComponent(kind) +
        "&id=" + encodeURIComponent(id));
      var wrap = shareBlock(kind, id);
      wrap.innerHTML =
        "<strong>Share draft</strong>\n" + esc(draft.text) +
        '\n<span class="small muted">' + esc(draft.url) + "</span>";
      var btns = document.createElement("div");
      btns.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-top:12px";
      btns.innerHTML =
        '<button class="btn btn-sm btn-outline" data-act="copy" type="button">Copy text</button>' +
        '<a class="btn btn-sm btn-outline" href="' + FB_PAGE + '" target="_blank" rel="noopener">Open Making Stuff</a>' +
        '<button class="btn btn-sm btn-brass" data-act="publish" type="button">Publish to Making Stuff</button>';
      wrap.appendChild(btns);
      var result = document.createElement("div");
      result.style.marginTop = "10px";
      wrap.appendChild(result);
      anchorEl.closest(".admin-card").appendChild(wrap);
      wrap.scrollIntoView({ behavior: "smooth", block: "nearest" });

      btns.addEventListener("click", async function (e) {
        var act = e.target.getAttribute("data-act");
        if (act === "copy") {
          try {
            await navigator.clipboard.writeText(draft.text);
            e.target.textContent = "Copied";
            setTimeout(function () { e.target.textContent = "Copy text"; }, 2000);
          } catch (err) {
            var ta = document.createElement("textarea");
            ta.value = draft.text;
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand("copy"); e.target.textContent = "Copied"; } catch (e2) { /* ignore */ }
            ta.remove();
            setTimeout(function () { e.target.textContent = "Copy text"; }, 2000);
          }
        } else if (act === "publish") {
          e.target.disabled = true;
          result.innerHTML = '<p class="small muted">Publishing...</p>';
          try {
            var res = await jpost("/api/admin/share-publish", { kind: kind, id: id });
            if (res.published) {
              result.innerHTML = '<div class="notice notice-ok">Published: ' + esc(res.detail || "done") + "</div>";
            } else {
              result.innerHTML = '<div class="notice notice-err">Automatic publishing is not connected. ' +
                "Copy the text above and post it manually." +
                (res.detail ? "<br><span class=\"small\">" + esc(res.detail) + "</span>" : "") + "</div>";
            }
          } catch (err) {
            result.innerHTML = '<div class="notice notice-err">Automatic publishing is not connected. ' +
              "Copy the text above and post it manually." +
              '<br><span class="small">' + esc(err.message) + "</span></div>";
          }
          e.target.disabled = false;
        }
      });
    } catch (err) {
      showErr(anchorEl, "Could not load the share draft: " + err.message);
    }
  }

  /* ---------------- products ---------------- */

  var productCache = [];

  function buildDeptCheckboxes() {
    $("pf-depts").innerHTML = DEPTS.map(function (d) {
      return '<label><input type="checkbox" value="' + esc(d.v) + '"> ' + esc(d.l) + "</label>";
    }).join("");
  }

  function checkedDepts() {
    return Array.prototype.filter.call(
      $("pf-depts").querySelectorAll('input[type="checkbox"]'),
      function (c) { return c.checked; }
    ).map(function (c) { return c.value; });
  }

  function setCheckedDepts(list) {
    Array.prototype.forEach.call(
      $("pf-depts").querySelectorAll('input[type="checkbox"]'),
      function (c) { c.checked = list.indexOf(c.value) >= 0; }
    );
  }

  async function loadProducts() {
    var list = $("productList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/products");
      productCache = data.products || [];
      if (!productCache.length) {
        list.innerHTML = '<p class="muted">No products yet. Add one below.</p>';
        return;
      }
      var rows = productCache.map(function (p) {
        var depts = parseDepts(p).map(deptName).join(", ");
        return "<tr>" +
          "<td><strong>" + esc(p.name) + "</strong><br><span class=\"small muted\">" + esc(p.id) + "</span></td>" +
          "<td>" + esc(money(p.price_cents)) + "</td>" +
          "<td>" + esc(depts || "-") + "</td>" +
          "<td>" + (p.stock == null ? "Unlimited" : esc(p.stock)) + "</td>" +
          "<td>" + (p.preorder ? '<span class="badge badge-preorder">Preorder</span>' : "-") + "</td>" +
          "<td>" + (p.active ? "Yes" : "Hidden") + "</td>" +
          '<td><div class="admin-row-actions">' +
          '<button class="btn btn-sm btn-outline" data-pedit="' + esc(p.id) + '" type="button">Edit</button>' +
          '<button class="btn btn-sm btn-outline" data-pdel="' + esc(p.id) + '" type="button">Delete</button>' +
          '<button class="btn btn-sm btn-outline" data-pshare="' + esc(p.id) + '" type="button">Share</button>' +
          "</div></td></tr>";
      }).join("");
      list.innerHTML = tableWrap(
        '<table class="admin-table"><thead><tr><th>Name</th><th>Price</th><th>Departments</th>' +
        "<th>Stock</th><th>Preorder</th><th>Visible</th><th>Actions</th></tr></thead><tbody>" +
        rows + "</tbody></table>");
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load products: " + err.message);
    }
  }

  function fillProductForm(p) {
    $("pf-id").value = p.id || "";
    $("pf-name").value = p.name || "";
    $("pf-price").value = p.price_cents != null ? (p.price_cents / 100).toFixed(2) : "";
    $("pf-stock").value = p.stock == null ? "" : p.stock;
    $("pf-photo").value = p.photo || "";
    $("pf-photo-file").value = "";
    setCheckedDepts(parseDepts(p));
    $("pf-preorder").checked = !!p.preorder;
    $("pf-engravable").checked = !!p.engravable;
    $("pf-purchasable").checked = !!p.purchasable;
    $("pf-active").checked = p.active == null ? true : !!p.active;
    $("pf-shipdate").value = p.preorder_ship_date || "";
    $("pf-customlink").value = p.custom_link || "";
    $("pf-desc").value = p.description || "";
    toggleShipdate();
    $("productForm").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function clearProductForm() {
    $("productForm").reset();
    $("pf-id").value = "";
    $("pf-photo").value = "";
    $("pf-photo-file").value = "";
    setCheckedDepts([]);
    toggleShipdate();
  }

  function toggleShipdate() {
    $("pf-shipdate-wrap").style.display = $("pf-preorder").checked ? "block" : "none";
  }

  async function saveProduct(e) {
    e.preventDefault();
    clearNotice($("productForm"));
    var btn = $("productForm").querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      var photo = $("pf-photo").value.trim();
      var fileInput = $("pf-photo-file");
      if (fileInput.files.length) {
        var fd = new FormData();
        fd.append("file", fileInput.files[0]);
        var up = await call("/api/admin/upload", { method: "POST", body: fd });
        photo = up.url || photo;
        $("pf-photo").value = photo;
      }
      var stockRaw = $("pf-stock").value.trim();
      var editId = $("pf-id").value.trim();
      var existing = editId
        ? productCache.filter(function (p) { return p.id === editId; })[0]
        : null;
      var payload = {
        id: editId || "",
        name: $("pf-name").value.trim(),
        price: parseFloat($("pf-price").value) || 0,
        stock: stockRaw === "" ? "" : parseInt(stockRaw, 10),
        photo: photo,
        depts: checkedDepts(),
        preorder: $("pf-preorder").checked,
        preorder_ship_date: $("pf-shipdate").value.trim(),
        engravable: $("pf-engravable").checked,
        purchasable: $("pf-purchasable").checked,
        active: $("pf-active").checked,
        custom_link: $("pf-customlink").value.trim(),
        description: $("pf-desc").value.trim(),
        sort: existing ? (existing.sort || 0) : 0
      };
      await jpost("/api/admin/products", payload);
      showOk($("productForm"), "Product saved.");
      clearProductForm();
      await loadProducts();
    } catch (err) {
      showErr($("productForm"), "Could not save the product: " + err.message);
    }
    btn.disabled = false;
  }

  /* ---------------- announcements ---------------- */

  async function loadAnnouncements() {
    var list = $("annList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/announcements");
      var anns = data.announcements || [];
      if (!anns.length) {
        list.innerHTML = '<p class="muted">No announcements yet.</p>';
        return;
      }
      list.innerHTML = anns.map(function (a) {
        return '<div class="feed-item" data-aid="' + esc(a.id) + '">' +
          '<div class="feed-date">' + esc(fmtDate(a.created)) + "</div>" +
          "<h3>" + esc(a.title) + "</h3>" +
          "<p>" + esc(a.body) + "</p>" +
          '<div class="admin-row-actions" style="margin-top:10px">' +
          '<button class="btn btn-sm btn-outline" data-adel="' + esc(a.id) + '" type="button">Delete</button>' +
          '<button class="btn btn-sm btn-outline" data-ashare="' + esc(a.id) + '" type="button">Share</button>' +
          "</div></div>";
      }).join("");
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load announcements: " + err.message);
    }
  }

  async function saveAnnouncement(e) {
    e.preventDefault();
    clearNotice($("annForm"));
    try {
      await jpost("/api/admin/announcements", {
        title: $("af-title").value.trim(),
        body: $("af-body").value.trim()
      });
      $("annForm").reset();
      showOk($("annForm"), "Announcement published.");
      await loadAnnouncements();
    } catch (err) {
      showErr($("annForm"), "Could not publish the announcement: " + err.message);
    }
  }

  /* ---------------- work in progress ---------------- */

  var wipCache = [];

  async function loadWip() {
    var list = $("wipList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/wip");
      wipCache = data.projects || [];
      if (!wipCache.length) {
        list.innerHTML = '<p class="muted">No projects yet.</p>';
      } else {
        list.innerHTML = wipCache.map(function (p) {
          var updates = (p.updates || []).map(function (u) {
            return '<li><span class="log-date">' + esc(fmtDate(u.created)) + "</span>" + esc(u.text) + "</li>";
          }).join("");
          return '<div class="feed-item">' +
            "<h3>" + esc(p.project) + "</h3>" +
            '<p class="small muted">Status: ' + esc(p.status || "not set") + " | " +
            (p.updates || []).length + " updates</p>" +
            (updates ? '<ul class="wip-log">' + updates + "</ul>" : "") +
            '<div class="admin-row-actions" style="margin-top:10px">' +
            '<button class="btn btn-sm btn-outline" data-wdel="' + esc(p.id) + '" type="button">Delete</button>' +
            "</div></div>";
        }).join("");
      }
      $("wu-project").innerHTML = wipCache.map(function (p) {
        return '<option value="' + esc(p.id) + '">' + esc(p.project) + "</option>";
      }).join("");
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load projects: " + err.message);
    }
  }

  async function saveWipProject(e) {
    e.preventDefault();
    clearNotice($("wipForm"));
    try {
      await jpost("/api/admin/wip", {
        project: $("wf-project").value.trim(),
        status: $("wf-status").value.trim()
      });
      $("wipForm").reset();
      showOk($("wipForm"), "Project added.");
      await loadWip();
    } catch (err) {
      showErr($("wipForm"), "Could not add the project: " + err.message);
    }
  }

  async function saveWipUpdate(e) {
    e.preventDefault();
    clearNotice($("wipUpdateForm"));
    try {
      var pid = $("wu-project").value;
      if (!pid) throw new Error("add a project first");
      await jpost("/api/admin/wip-update", {
        project_id: pid,
        text: $("wu-text").value.trim()
      });
      $("wu-text").value = "";
      showOk($("wipUpdateForm"), "Update added.");
      await loadWip();
    } catch (err) {
      showErr($("wipUpdateForm"), "Could not add the update: " + err.message);
    }
  }

  /* ---------------- orders ---------------- */

  async function loadOrders() {
    var list = $("orderList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/orders");
      var orders = data.orders || [];
      var lamps = data.lamp_orders || [];
      if (!orders.length && !lamps.length) {
        list.innerHTML = '<p class="muted">No orders yet.</p>';
        return;
      }
      var rows = "";
      orders.forEach(function (o) {
        rows += "<tr>" +
          "<td>" + esc(fmtDate(o.created)) + "</td>" +
          "<td><strong>" + esc(o.product_name || o.product_id || "-") + "</strong></td>" +
          "<td>" + esc(o.qty == null ? 1 : o.qty) + "</td>" +
          "<td>" + esc(money(o.amount_cents)) + "</td>" +
          "<td>" + esc(o.engraving_text || "-") + "</td>" +
          "<td>" + (o.preorder ? "Yes" + (o.preorder_ship_date ? " (" + esc(o.preorder_ship_date) + ")" : "") : "-") + "</td>" +
          "<td>" + (o.paid ? "Yes" : "No") + "</td></tr>";
      });
      lamps.forEach(function (o) {
        rows += "<tr>" +
          "<td>" + esc(fmtDate(o.created)) + "</td>" +
          "<td><strong>Custom memorial lamp</strong><br><span class=\"small muted\">" +
          esc(o.pack === "set4" ? "4 copies" : "single") + "</span></td>" +
          "<td>1</td>" +
          "<td>" + esc(money(o.amount)) + "</td>" +
          "<td>-</td><td>-</td>" +
          "<td>" + (o.paid ? "Yes" : "No") + "</td></tr>";
      });
      list.innerHTML = tableWrap(
        '<table class="admin-table"><thead><tr><th>Date</th><th>Product</th><th>Qty</th>' +
        "<th>Amount</th><th>Engraving</th><th>Preorder</th><th>Paid</th></tr></thead><tbody>" +
        rows + "</tbody></table>");
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load orders: " + err.message);
    }
  }

  /* ---------------- engraving requests ---------------- */

  async function loadEngraving() {
    var list = $("engList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/engraving-requests");
      var reqs = data.requests || [];
      if (!reqs.length) {
        list.innerHTML = '<p class="muted">No engraving requests yet.</p>';
        return;
      }
      var rows = reqs.map(function (r) {
        return "<tr>" +
          "<td>" + esc(fmtDate(r.created)) + "</td>" +
          "<td><strong>" + esc(r.name) + "</strong></td>" +
          '<td><a href="mailto:' + esc(r.email) + '">' + esc(r.email) + "</a></td>" +
          "<td>" + esc(r.product || "-") + "</td>" +
          "<td>" + esc(r.message) + "</td></tr>";
      }).join("");
      list.innerHTML = tableWrap(
        '<table class="admin-table"><thead><tr><th>Date</th><th>Name</th><th>Email</th>' +
        "<th>Product</th><th>Message</th></tr></thead><tbody>" +
        rows + "</tbody></table>");
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load engraving requests: " + err.message);
    }
  }

  /* ---------------- events ---------------- */

  document.addEventListener("click", async function (e) {
    var t = e.target;
    var id;
    if ((id = t.getAttribute("data-pedit"))) {
      var p = productCache.filter(function (x) { return x.id === id; })[0];
      if (p) { clearNotice($("productForm")); fillProductForm(p); }
    } else if ((id = t.getAttribute("data-pdel"))) {
      if (confirm("Delete this product? This cannot be undone.")) {
        try {
          await call("/api/admin/products/" + encodeURIComponent(id), { method: "DELETE" });
          await loadProducts();
        } catch (err) { showErr($("productList"), "Could not delete the product: " + err.message); }
      }
    } else if ((id = t.getAttribute("data-pshare"))) {
      doShare("product", id, t);
    } else if ((id = t.getAttribute("data-adel"))) {
      if (confirm("Delete this announcement? This cannot be undone.")) {
        try {
          await call("/api/admin/announcements/" + encodeURIComponent(id), { method: "DELETE" });
          await loadAnnouncements();
        } catch (err) { showErr($("annList"), "Could not delete the announcement: " + err.message); }
      }
    } else if ((id = t.getAttribute("data-ashare"))) {
      doShare("announcement", id, t);
    } else if ((id = t.getAttribute("data-wdel"))) {
      if (confirm("Delete this project and all its updates? This cannot be undone.")) {
        try {
          await call("/api/admin/wip/" + encodeURIComponent(id), { method: "DELETE" });
          await loadWip();
        } catch (err) { showErr($("wipList"), "Could not delete the project: " + err.message); }
      }
    }
  });

  function init() {
    buildDeptCheckboxes();
    $("pf-preorder").addEventListener("change", toggleShipdate);
    toggleShipdate();
    $("productForm").addEventListener("submit", saveProduct);
    $("pf-cancel").addEventListener("click", function () { clearProductForm(); clearNotice($("productForm")); });
    $("annForm").addEventListener("submit", saveAnnouncement);
    $("wipForm").addEventListener("submit", saveWipProject);
    $("wipUpdateForm").addEventListener("submit", saveWipUpdate);
    loadProducts();
    loadAnnouncements();
    loadWip();
    loadOrders();
    loadEngraving();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
