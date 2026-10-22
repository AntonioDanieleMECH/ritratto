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
    $("pf-name-fr").value = p.name_fr || "";
    $("pf-price").value = p.price_cents != null ? (p.price_cents / 100).toFixed(2) : "";
    $("pf-addprice").value = p.additional_price_cents != null ? (p.additional_price_cents / 100).toFixed(2) : "";
    $("pf-stock").value = p.stock == null ? "" : p.stock;
    $("pf-photo").value = p.photo || "";
    $("pf-photo-file").value = "";
    setCheckedDepts(parseDepts(p));
    $("pf-preorder").checked = !!p.preorder;
    $("pf-engravable").checked = !!p.engravable;
    $("pf-inworks").checked = !!p.in_works;
    $("pf-purchasable").checked = !!p.purchasable;
    $("pf-active").checked = p.active == null ? true : !!p.active;
    $("pf-shipdate").value = p.preorder_ship_date || "";
    $("pf-customlink").value = p.custom_link || "";
    $("pf-desc").value = p.description || "";
    $("pf-desc-fr").value = p.description_fr || "";
    $("pf-story").value = p.story || "";
    $("pf-story-fr").value = p.story_fr || "";
    toggleShipdate();
    loadPhotoManager(p.id);
    $("productForm").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function clearProductForm() {
    $("productForm").reset();
    $("pf-id").value = "";
    $("pf-photo").value = "";
    $("pf-photo-file").value = "";
    $("pf-photos").innerHTML = "";
    setCheckedDepts([]);
    toggleShipdate();
  }

  /* ---------------- product photo gallery ---------------- */

  async function loadPhotoManager(pid) {
    var box = $("pf-photos");
    if (!pid) { box.innerHTML = '<p class="small muted">Save the product first, then add photos.</p>'; return; }
    try {
      var data = await call("/api/admin/photos?product_id=" + encodeURIComponent(pid));
      var photos = data.photos || [];
      if (!photos.length) {
        box.innerHTML = '<p class="small muted">No gallery photos yet. The main photo above is used.</p>';
        return;
      }
      box.innerHTML = photos.map(function (ph, i) {
        var isVid = (ph.kind || "photo") === "video";
        var thumb = isVid
          ? '<video src="' + esc(ph.photo) + '" muted preload="metadata" playsinline style="width:56px;height:56px;object-fit:cover;border-radius:8px"></video>'
          : '<img src="' + esc(ph.photo) + '" style="width:56px;height:56px;object-fit:cover;border-radius:8px">';
        var label = isVid ? "Video" : (ph.is_scale ? "Scale shot (shown last)" : "Photo " + (i + 1));
        return '<div class="photo-row" style="display:flex;gap:8px;align-items:center;margin:6px 0">' +
          thumb +
          '<span class="small muted" style="flex:1">' + label + "</span>" +
          '<button class="btn btn-sm btn-outline" data-phact="up" data-phid="' + esc(ph.id) + '" type="button">Up</button>' +
          '<button class="btn btn-sm btn-outline" data-phact="down" data-phid="' + esc(ph.id) + '" type="button">Down</button>' +
          ((!isVid && !ph.is_scale) ? '<button class="btn btn-sm btn-outline" data-phact="scale" data-phid="' + esc(ph.id) + '" type="button">Scale shot</button>' : "") +
          '<button class="btn btn-sm btn-outline" data-phact="del" data-phid="' + esc(ph.id) + '" type="button">Delete</button>' +
          "</div>";
      }).join("");
    } catch (err) {
      box.innerHTML = '<p class="small muted">Could not load photos.</p>';
    }
  }

  async function uploadGalleryPhoto() {
    var pid = $("pf-id").value.trim();
    if (!pid) { showErr($("productForm"), "Save the product first, then add photos."); return; }
    var fi = $("pf-photo-upload");
    var files = fi.files;
    if (!files.length) return;
    clearNotice($("productForm"));
    var btn = $("pf-photo-add");
    btn.disabled = true;
    try {
      for (var k = 0; k < files.length; k++) {
        btn.textContent = "Uploading " + (k + 1) + " of " + files.length + "...";
        var fd = new FormData();
        fd.append("file", files[k]);
        var up = await call("/api/admin/upload", { method: "POST", body: fd });
        await jpost("/api/admin/photos", { product_id: pid, photo: up.url, kind: up.kind || "photo" });
      }
      fi.value = "";
      showOk($("productForm"), files.length === 1 ? "Upload complete." : files.length + " uploads complete.");
      await loadPhotoManager(pid);
    } catch (err) {
      showErr($("productForm"), "Upload failed: " + err.message);
    }
    btn.textContent = "Upload";
    btn.disabled = false;
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
        name_fr: $("pf-name-fr").value.trim(),
        price: parseFloat($("pf-price").value) || 0,
        additional_price: $("pf-addprice").value.trim(),
        stock: stockRaw === "" ? "" : parseInt(stockRaw, 10),
        photo: photo,
        depts: checkedDepts(),
        preorder: $("pf-preorder").checked,
        preorder_ship_date: $("pf-shipdate").value.trim(),
        engravable: $("pf-engravable").checked,
        in_works: $("pf-inworks").checked,
        purchasable: $("pf-purchasable").checked,
        active: $("pf-active").checked,
        custom_link: $("pf-customlink").value.trim(),
        description: $("pf-desc").value.trim(),
        description_fr: $("pf-desc-fr").value.trim(),
        story: $("pf-story").value.trim(),
        story_fr: $("pf-story-fr").value.trim(),
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
        title_fr: $("af-title-fr").value.trim(),
        body: $("af-body").value.trim(),
        body_fr: $("af-body-fr").value.trim()
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
        project_fr: $("wf-project-fr").value.trim(),
        status: $("wf-status").value.trim(),
        status_fr: $("wf-status-fr").value.trim()
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
        text: $("wu-text").value.trim(),
        text_fr: $("wu-text-fr").value.trim()
      });
      $("wu-text").value = "";
      $("wu-text-fr").value = "";
      showOk($("wipUpdateForm"), "Update added.");
      await loadWip();
    } catch (err) {
      showErr($("wipUpdateForm"), "Could not add the update: " + err.message);
    }
  }

  /* ---------------- orders to dispatch ---------------- */

  var orderCache = { orders: [], lamps: [] };
  var orderShowAll = false;

  function normOrder(o, kind) {
    var items;
    if (kind === "lamp") {
      items = "Custom memorial lamp (" + (o.pack === "pack4" ? "4-pack" : "single") + ")";
    } else if (o.items && o.items.length) {
      items = o.items.map(function (i) {
        var s = (i.product_name || i.product_id) + " x" + i.qty;
        if (i.options) s += " (" + i.options + ")";
        return s;
      }).join(" · ");
      if (o.preorder) items += " (preorder" + (o.preorder_ship_date ? ": " + o.preorder_ship_date : "") + ")";
    } else {
      items = (o.product_name || o.product_id || "-") + " x" + (o.qty == null ? 1 : o.qty);
      if (o.engraving_text) items += ', engraved "' + o.engraving_text + '"';
      if (o.preorder) items += " (preorder" + (o.preorder_ship_date ? ": " + o.preorder_ship_date : "") + ")";
    }
    return {
      kind: kind,
      id: o.id,
      created: o.created,
      customer: o.customer_name || o.ship_name || "",
      email: o.email || "",
      phone: o.phone || "",
      items: items,
      amount: kind === "lamp" ? o.amount : o.amount_cents,
      address: o.ship_address || "",
      paid: !!o.paid,
      shipped: !!o.shipped,
      tracking: o.tracking_number || "",
      carrier: o.carrier || ""
    };
  }

  function orderStatusBadge(o) {
    if (o.shipped) return '<span class="badge">Dispatched</span>';
    if (o.paid) return '<span class="badge badge-preorder">To dispatch</span>';
    return '<span class="badge badge-stock">Unpaid</span>';
  }

  function orderRow(o) {
    var dispatchCell;
    if (o.paid && !o.shipped) {
      dispatchCell = '<div style="min-width:180px">' +
        '<input type="text" placeholder="Tracking number" data-trk style="width:100%;margin-bottom:6px">' +
        '<input type="text" placeholder="Carrier (optional)" data-car style="width:100%;margin-bottom:6px">' +
        '<button class="btn btn-sm btn-brass" data-dispatch="' + esc(o.id) + '" type="button">Mark dispatched &amp; email customer</button>' +
        "</div>";
    } else if (o.shipped) {
      dispatchCell = '<span class="small">' + esc(o.tracking) +
        (o.carrier ? "<br>" + esc(o.carrier) : "") + "</span>";
    } else {
      dispatchCell = '<span class="small muted">-</span>';
    }
    var customer = esc(o.customer || "-") +
      (o.email ? '<br><a href="mailto:' + esc(o.email) + '">' + esc(o.email) + "</a>" : "") +
      (o.phone ? '<br><a href="tel:' + esc(o.phone.replace(/[^+\d]/g, "")) + '">' + esc(o.phone) + "</a>" : "");
    var addr = o.address
      ? '<span class="small" style="white-space:pre-line">' + esc(o.address) + "</span>"
      : '<span class="small muted">-</span>';
    return "<tr>" +
      "<td>" + esc(fmtDate(o.created)) + '<br><span class="small muted">' + esc(o.id) + "</span></td>" +
      "<td>" + customer + "</td>" +
      "<td><strong>" + esc(o.items) + "</strong></td>" +
      "<td>" + esc(money(o.amount)) + "</td>" +
      "<td>" + addr + "</td>" +
      "<td>" + orderStatusBadge(o) + "</td>" +
      "<td>" + dispatchCell + "</td></tr>";
  }

  function renderOrders() {
    var list = $("orderList");
    var all = orderCache.orders.map(function (o) { return normOrder(o, "shop"); })
      .concat(orderCache.lamps.map(function (o) { return normOrder(o, "lamp"); }));
    all.sort(function (a, b) { return a.created < b.created ? 1 : -1; });
    var shown = orderShowAll ? all : all.filter(function (o) { return o.paid && !o.shipped; });
    var toDispatch = all.filter(function (o) { return o.paid && !o.shipped; }).length;
    $("ord-count").textContent = toDispatch === 1
      ? "1 order to dispatch"
      : toDispatch + " orders to dispatch";
    if (!shown.length) {
      list.innerHTML = orderShowAll
        ? '<p class="muted">No orders yet.</p>'
        : '<p class="muted">Nothing to dispatch. Everything paid is shipped.</p>';
      return;
    }
    list.innerHTML = tableWrap(
      '<table class="admin-table"><thead><tr><th>Date</th><th>Customer</th><th>Items</th>' +
      "<th>Total</th><th>Ship to</th><th>Status</th><th>Dispatch</th></tr></thead><tbody>" +
      shown.map(orderRow).join("") + "</tbody></table>");
  }

  async function loadOrders() {
    var list = $("orderList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/orders");
      orderCache = { orders: data.orders || [], lamps: data.lamp_orders || [] };
      renderOrders();
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load orders: " + err.message);
    }
  }

  /* ---------------- product views ---------------- */

  var viewCache = [];
  var viewTotals = { total: 0, last30: 0 };
  var viewSort = { key: "total", dir: -1 };

  async function loadProductViews() {
    var list = $("viewList");
    try {
      var data = await call("/api/admin/product-views");
      viewCache = data.views || [];
      viewTotals = { total: data.grand_total || 0, last30: data.grand_last30 || 0 };
      renderViews();
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load views: " + err.message);
    }
  }

  function renderViews() {
    var list = $("viewList");
    if (!list) return;
    var k = viewSort.key, d = viewSort.dir;
    var rows = viewCache.slice().sort(function (a, b) {
      var va = k === "name" ? (a.name || a.product_id || "").toLowerCase() : a[k];
      var vb = k === "name" ? (b.name || b.product_id || "").toLowerCase() : b[k];
      return (va > vb ? 1 : va < vb ? -1 : 0) * d;
    });
    var arrow = function (key) {
      return viewSort.key === key ? (viewSort.dir === 1 ? " \u25b2" : " \u25bc") : "";
    };
    var body = rows.map(function (v) {
      return "<tr><td><strong>" + esc(v.name || v.product_id) + "</strong></td>" +
        "<td>" + v.total + "</td><td>" + v.last30 + "</td></tr>";
    }).join("");
    list.innerHTML = tableWrap(
      '<table class="admin-table"><thead><tr>' +
      '<th><a href="#" data-vsort="name" style="color:inherit">Product' + arrow("name") + "</a></th>" +
      '<th><a href="#" data-vsort="total" style="color:inherit">Total views' + arrow("total") + "</a></th>" +
      '<th><a href="#" data-vsort="last30" style="color:inherit">Last 30 days' + arrow("last30") + "</a></th>" +
      "</tr></thead><tbody>" + (body || '<tr><td colspan="3" class="muted">No views recorded yet.</td></tr>') + "</tbody>" +
      "<tfoot><tr><td><strong>Total</strong></td><td><strong>" + viewTotals.total +
      "</strong></td><td><strong>" + viewTotals.last30 + "</strong></td></tr></tfoot></table>");
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

  /* ---------------- portrait ideas + notify-me ---------------- */

  async function loadPortraitIdeas() {
    var list = $("porList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/portrait-ideas");
      var ideas = data.ideas || [];
      if (!ideas.length) {
        list.innerHTML = '<p class="muted">No portrait ideas yet.</p>';
        return;
      }
      var rows = ideas.map(function (r) {
        return "<tr>" +
          "<td>" + esc(fmtDate(r.created)) + "</td>" +
          "<td><strong>" + esc(r.name) + "</strong></td>" +
          '<td><a href="mailto:' + esc(r.email) + '">' + esc(r.email) + "</a></td>" +
          "<td>" + esc(r.idea) + "</td></tr>";
      }).join("");
      list.innerHTML = tableWrap(
        '<table class="admin-table"><thead><tr><th>Date</th><th>Name</th><th>Email</th>' +
        "<th>Idea</th></tr></thead><tbody>" + rows + "</tbody></table>");
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load portrait ideas: " + err.message);
    }
  }

  async function loadSuggestions() {
    var list = $("sgList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/suggestions");
      var items = data.suggestions || [];
      if (!items.length) {
        list.innerHTML = '<p class="muted">No suggestions yet.</p>';
        return;
      }
      var rows = items.map(function (r) {
        return "<tr>" +
          "<td>" + esc(fmtDate(r.created)) + "</td>" +
          "<td><strong>" + esc(r.title) + "</strong><br><span class=\"small muted\">" + esc(r.category) + "</span></td>" +
          "<td><strong>" + esc(r.name) + '</strong><br><a href="mailto:' + esc(r.email) + '">' + esc(r.email) + "</a></td>" +
          "<td>" + esc(r.description) + "</td></tr>";
      }).join("");
      list.innerHTML = tableWrap(
        '<table class="admin-table"><thead><tr><th>Date</th><th>Idea</th><th>From</th>' +
        "<th>Description</th></tr></thead><tbody>" + rows + "</tbody></table>");
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load suggestions: " + err.message);
    }
  }

  async function loadNotifyMe() {
    var list = $("ntfList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/notify-me");
      var items = data.list || [];
      if (!items.length) {
        list.innerHTML = '<p class="muted">Nobody waiting yet.</p>';
        return;
      }
      var rows = items.map(function (r) {
        return "<tr>" +
          "<td>" + esc(fmtDate(r.created)) + "</td>" +
          "<td>" + esc(r.product_name || r.product_id) + "</td>" +
          '<td><a href="mailto:' + esc(r.email) + '">' + esc(r.email) + "</a></td></tr>";
      }).join("");
      list.innerHTML = tableWrap(
        '<table class="admin-table"><thead><tr><th>Date</th><th>Product</th><th>Email</th>' +
        "</tr></thead><tbody>" + rows + "</tbody></table>");
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load the notify list: " + err.message);
    }
  }

  async function loadReviews() {
    var list = $("revList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/reviews");
      var items = data.reviews || [];
      if (!items.length) {
        list.innerHTML = '<p class="muted">No reviews yet.</p>';
        return;
      }
      var rows = items.map(function (r) {
        var stars = "";
        for (var i = 0; i < 5; i++) stars += i < r.rating ? "\u2605" : "\u2606";
        var action = r.approved
          ? '<span class="small muted">Live</span>'
          : '<button class="btn btn-primary" data-rev-approve="' + esc(r.id) + '">Approve</button>';
        return "<tr>" +
          "<td>" + esc(fmtDate(r.created)) + "</td>" +
          "<td>" + esc(r.product_name || r.product_id) + "</td>" +
          "<td>" + stars + "</td>" +
          "<td><strong>" + esc(r.name) + "</strong><br>" + esc(r.text) + "</td>" +
          "<td>" + action +
          ' <button class="btn btn-outline" data-rev-delete="' + esc(r.id) + '">Delete</button></td></tr>';
      }).join("");
      list.innerHTML = tableWrap(
        '<table class="admin-table"><thead><tr><th>Date</th><th>Product</th><th>Stars</th>' +
        "<th>Review</th><th>Moderation</th></tr></thead><tbody>" + rows + "</tbody></table>");
      list.querySelectorAll("[data-rev-approve]").forEach(function (b) {
        b.addEventListener("click", async function () {
          await call("/api/admin/reviews/" + encodeURIComponent(b.getAttribute("data-rev-approve")) + "/approve", { method: "POST" });
          loadReviews();
        });
      });
      list.querySelectorAll("[data-rev-delete]").forEach(function (b) {
        b.addEventListener("click", async function () {
          if (!confirm("Delete this review?")) return;
          await call("/api/admin/reviews/" + encodeURIComponent(b.getAttribute("data-rev-delete")) + "/delete", { method: "POST" });
          loadReviews();
        });
      });
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load reviews: " + err.message);
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
    } else if ((id = t.getAttribute("data-dispatch"))) {
      var tr = t.closest("tr");
      var tn = tr.querySelector("input[data-trk]").value.trim();
      var car = tr.querySelector("input[data-car]").value.trim();
      if (!tn) { showErr($("orderList"), "Enter the tracking number first."); return; }
      t.disabled = true;
      try {
        var res = await jpost("/api/admin/dispatch",
          { order_id: id, tracking_number: tn, carrier: car });
        if (res.emailed) {
          showOk($("orderList"), "Marked dispatched. Tracking email sent to the customer.");
        } else {
          showOk($("orderList"), "Marked dispatched, but the email did NOT go out: " +
            (res.email_detail || "unknown reason") + ". Send the tracking number manually.");
        }
        await loadOrders();
      } catch (err) { showErr($("orderList"), "Dispatch failed: " + err.message); }
      t.disabled = false;
    } else if (t.getAttribute("data-vsort")) {
      e.preventDefault();
      var sk = t.getAttribute("data-vsort");
      if (viewSort.key === sk) { viewSort.dir *= -1; }
      else { viewSort = { key: sk, dir: sk === "name" ? 1 : -1 }; }
      renderViews();
    } else if (t.getAttribute("data-phact")) {
      var phid = t.getAttribute("data-phid");
      var act = t.getAttribute("data-phact");
      try {
        if (act === "del") {
          if (!confirm("Delete this photo?")) return;
          await call("/api/admin/photos/" + encodeURIComponent(phid), { method: "DELETE" });
        } else if (act === "scale") {
          await jpost("/api/admin/photos/" + encodeURIComponent(phid), { action: "scale" });
        } else if (act === "up" || act === "down") {
          await jpost("/api/admin/photos/" + encodeURIComponent(phid),
            { action: "move", direction: act === "up" ? -1 : 1 });
        }
        await loadPhotoManager($("pf-id").value.trim());
      } catch (err) { showErr($("productForm"), "Photo update failed: " + err.message); }
    }
  });

  function init() {
    buildDeptCheckboxes();
    $("pf-preorder").addEventListener("change", toggleShipdate);
    toggleShipdate();
    $("productForm").addEventListener("submit", saveProduct);
    $("pf-cancel").addEventListener("click", function () { clearProductForm(); clearNotice($("productForm")); });
    $("pf-photo-add").addEventListener("click", uploadGalleryPhoto);
    $("annForm").addEventListener("submit", saveAnnouncement);
    $("wipForm").addEventListener("submit", saveWipProject);
    $("wipUpdateForm").addEventListener("submit", saveWipUpdate);
    $("ord-showall").addEventListener("change", function () {
      orderShowAll = this.checked;
      renderOrders();
    });
    loadProducts();
    loadProductViews();
    loadAnnouncements();
    loadWip();
    loadOrders();
    loadEngraving();
    loadPortraitIdeas();
    loadSuggestions();
    loadNotifyMe();
    loadReviews();
    loadCoupons();
    $("couponForm").addEventListener("submit", saveCoupon);
  }

  async function loadCoupons() {
    var list = $("couponList");
    clearNotice(list);
    try {
      var data = await call("/api/admin/coupons");
      var items = data.coupons || [];
      if (!items.length) {
        list.innerHTML = '<p class="muted">No codes yet.</p>';
        return;
      }
      var rows = items.map(function (c) {
        var toggle = c.active
          ? '<button class="btn btn-outline" data-coupon-toggle="' + esc(c.code) + '" data-active="0">Deactivate</button>'
          : '<button class="btn btn-primary" data-coupon-toggle="' + esc(c.code) + '" data-active="1">Activate</button>';
        return "<tr>" +
          "<td><strong>" + esc(c.code) + "</strong>" + (c.active ? "" : ' <span class="small muted">(off)</span>') + "</td>" +
          "<td>" + esc(String(c.percent_off)) + "%</td>" +
          "<td>" + esc(String(c.commission_pct || 0)) + "%</td>" +
          "<td>" + esc(c.note || "") + "</td>" +
          "<td>" + toggle +
          ' <button class="btn btn-outline" data-coupon-delete="' + esc(c.code) + '">Delete</button></td></tr>';
      }).join("");
      list.innerHTML = tableWrap(
        '<table class="admin-table"><thead><tr><th>Code</th><th>Off</th><th>Commission</th><th>Note</th><th></th>' +
        "</tr></thead><tbody>" + rows + "</tbody></table>");
      list.querySelectorAll("[data-coupon-toggle]").forEach(function (b) {
        b.addEventListener("click", async function () {
          await call("/api/admin/coupons/" + encodeURIComponent(b.getAttribute("data-coupon-toggle")),
            { method: "POST", body: JSON.stringify({ active: b.getAttribute("data-active") === "1" }) });
          loadCoupons();
        });
      });
      list.querySelectorAll("[data-coupon-delete]").forEach(function (b) {
        b.addEventListener("click", async function () {
          if (!confirm("Delete code " + b.getAttribute("data-coupon-delete") + "?")) return;
          await call("/api/admin/coupons/" + encodeURIComponent(b.getAttribute("data-coupon-delete")), { method: "DELETE" });
          loadCoupons();
        });
      });
    } catch (err) {
      list.innerHTML = "";
      showErr(list, "Could not load coupons: " + err.message);
    }
  }

  async function saveCoupon(e) {
    e.preventDefault();
    var code = $("cf-code").value.trim().toUpperCase();
    var pct = parseInt($("cf-pct").value, 10);
    var comm = parseInt(($("cf-comm") || {}).value, 10) || 0;
    var note = $("cf-note").value.trim();
    if (!code || !pct) return;
    await call("/api/admin/coupons", { method: "POST", body: JSON.stringify({ code: code, percent_off: pct, commission_pct: comm, note: note }) });
    $("cf-code").value = ""; $("cf-pct").value = ""; $("cf-note").value = "";
    if ($("cf-comm")) $("cf-comm").value = "0";
    loadCoupons();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
