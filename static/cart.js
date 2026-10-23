/* ADN Creations shopping cart.
   The cart lives in localStorage; checkout posts the lines to
   /api/cart-checkout, which re-prices everything server-side, so the
   prices shown here are display-only estimates using the same rules
   (size variants + tiered memorial-lamp pricing). */
(function () {
  "use strict";

  var KEY = "adn_cart_v1";
  var SHIP_KEY = "adn_ship_country";
  var SHIP_CENTS = { CA: 500, US: 1000, INT: 1500 };
  var PACK4 = 9999;
  var INITIALS_CENTS = 500; /* raised-initials add-on (card-case): CA$5 per
    UNIQUE initials string across the cart — the same initials on several
    lines/cases is one customization, charged once (server enforces this;
    this file only mirrors it for the displayed totals) */

  var S = {
    fr: {
      cart: "Panier", empty: "Votre panier est vide.",
      subtotal: "Sous-total", shipping: "Expédition", total: "Total",
      checkout: "Passer à la caisse", remove: "Retirer",
      coupon_ph: "Code promo (facultatif)", discount: "Rabais",
      ship_to: "Pays de livraison",
      ship_ca: "Canada — 5 $ CAD", ship_us: "États-Unis — 10 $ CAD",
      ship_intl: "International — 15 $ CAD",
      added: "Ajouté ✓", failed: "Le paiement a échoué. Réessayez.",
      preparing: "Préparation..."
    },
    en: {
      cart: "Cart", empty: "Your cart is empty.",
      subtotal: "Subtotal", shipping: "Shipping", total: "Total",
      checkout: "Checkout", remove: "Remove",
      coupon_ph: "Coupon code (optional)", discount: "Discount",
      ship_to: "Shipping country",
      ship_ca: "Canada — $5 CAD", ship_us: "United States — $10 CAD",
      ship_intl: "International — $15 CAD",
      added: "Added ✓", failed: "Checkout failed. Please try again.",
      preparing: "Preparing..."
    }
  };

  function lang() {
    var l = (window.adnGetLang && window.adnGetLang()) ||
      document.documentElement.getAttribute("lang") || "fr";
    return l === "en" ? "en" : "fr";
  }
  function T(k) { return (S[lang()] || S.fr)[k] || k; }
  function money(c) { return "$" + (c / 100).toFixed(2) + " CAD"; }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || []; }
    catch (e) { return []; }
  }
  function save(items) {
    try { localStorage.setItem(KEY, JSON.stringify(items)); } catch (e) {}
  }
  var COLOR_NAMES = {
    chrome: { fr: "Chrome", en: "Chrome" },
    blue: { fr: "Bleu", en: "Blue" },
    black: { fr: "Noir", en: "Black" }
  };
  function colorName(c) {
    var m = COLOR_NAMES[c];
    return m ? m[lang()] : c;
  }
  function keyOf(it) {
    return [it.pid, it.design || "", it.saint || "", it.size || "",
            it.color || "", it.initials || "", it.engraving || ""].join("|");
  }
  function lineTotal(it, withIni) {
    var q = it.qty || 1;
    var t;
    if (it.add_cents && q > 1) {
      var packs = Math.floor(q / 4), rest = q % 4;
      t = packs * PACK4;
      if (rest) t += it.unit_cents + (rest - 1) * it.add_cents;
    } else {
      t = (it.unit_cents || 0) * q;
    }
    /* The initials charge lands only on the first line carrying each
       distinct string; render() decides via iniCharged and passes the
       verdict in as withIni. */
    if (it.initials && withIni) t += INITIALS_CENTS;
    return t;
  }
  function optionsText(it) {
    var parts = [];
    if (it.design) parts.push(it.design);
    if (it.saint) parts.push("Saint: " + it.saint);
    if (it.size) parts.push("Size: " + it.size);
    if (it.color) parts.push((lang() === "fr" ? "Couleur" : "Color") + ": " + colorName(it.color));
    if (it.initials) parts.push("Initials: " + it.initials);
    if (it.engraving) parts.push(it.engraving);
    return parts.join(" · ");
  }
  function shipCountry() {
    var c = "CA";
    try { c = localStorage.getItem(SHIP_KEY) || "CA"; } catch (e) {}
    return SHIP_CENTS[c] ? c : "CA";
  }

  var pctOff = 0;
  var priceMap = null;

  /* ---------- UI ---------- */
  var style = document.createElement("style");
  style.textContent =
    ".cart-btn{position:relative;background:none;border:1px solid rgba(140,120,80,.55);" +
    "border-radius:999px;padding:6px 12px;cursor:pointer;font:inherit;font-size:1rem;line-height:1}" +
    ".cart-count{position:absolute;top:-7px;right:-7px;background:#A33232;color:#fff;" +
    "border-radius:999px;min-width:19px;height:19px;font-size:.72rem;font-weight:700;" +
    "display:flex;align-items:center;justify-content:center;padding:0 4px}" +
    ".cart-count.bump{transform:scale(1.3);transition:transform .15s}" +
    "#cartOverlay{position:fixed;inset:0;background:rgba(20,16,10,.45);opacity:0;" +
    "pointer-events:none;transition:opacity .2s;z-index:1200}" +
    "#cartOverlay.open{opacity:1;pointer-events:auto}" +
    "#cartDrawer{position:fixed;top:0;right:0;height:100dvh;width:min(420px,94vw);" +
    "background:#FFFDF8;z-index:1201;transform:translateX(102%);transition:transform .25s;" +
    "display:flex;flex-direction:column;box-shadow:-8px 0 28px rgba(0,0,0,.18)}" +
    "#cartDrawer.open{transform:none}" +
    ".cart-head{display:flex;justify-content:space-between;align-items:center;" +
    "padding:16px 18px;border-bottom:1px solid #E8E0CF}" +
    ".cart-head strong{font-size:1.15rem}" +
    ".cart-x{background:none;border:none;font-size:1.5rem;cursor:pointer;line-height:1;padding:2px 6px}" +
    "#cartItems{flex:1;overflow-y:auto;padding:12px 18px}" +
    ".cart-line{display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #F0E9D8}" +
    ".cart-line img{width:56px;height:56px;object-fit:cover;border-radius:8px;background:#F3EDDD}" +
    ".cart-line .cl-main{flex:1;min-width:0}" +
    ".cart-line .cl-name{font-weight:600;font-size:.95rem}" +
    ".cart-line .cl-opts{font-size:.8rem;color:#7A7261;word-break:break-word}" +
    ".cart-line .cl-row{display:flex;justify-content:space-between;align-items:center;margin-top:6px}" +
    ".qty-ctl{display:inline-flex;align-items:center;gap:2px;border:1px solid #D8CFB8;border-radius:999px}" +
    ".qty-ctl button{background:none;border:none;width:26px;height:26px;cursor:pointer;font-size:1rem;line-height:1}" +
    ".qty-ctl span{min-width:20px;text-align:center;font-weight:600}" +
    ".cl-rm{background:none;border:none;color:#A33232;cursor:pointer;font-size:.8rem;padding:2px 0}" +
    ".cart-foot{border-top:1px solid #E8E0CF;padding:14px 18px 18px}" +
    ".cart-row{display:flex;justify-content:space-between;margin:4px 0;font-size:.95rem}" +
    ".cart-row.total{font-weight:700;font-size:1.08rem;margin-top:8px}" +
    ".cart-foot select,.cart-foot input[type=text]{width:100%;padding:9px 10px;margin:6px 0;" +
    "border:1px solid #D8CFB8;border-radius:8px;background:#fff;font:inherit}" +
    ".cart-foot label{font-size:.85rem;color:#7A7261}" +
    "#cartCheckoutBtn{width:100%;margin-top:10px}" +
    "#cartMsg{margin-top:8px}";
  document.head.appendChild(style);

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "cart-btn";
  btn.setAttribute("aria-label", "Cart");
  btn.innerHTML = "🛒<span class=\"cart-count\" id=\"cartCount\" style=\"display:none\">0</span>";

  var overlay = document.createElement("div");
  overlay.id = "cartOverlay";
  var drawer = document.createElement("aside");
  drawer.id = "cartDrawer";
  drawer.setAttribute("aria-label", "Shopping cart");
  drawer.innerHTML =
    '<div class="cart-head"><strong id="cartTitle"></strong>' +
    '<button type="button" class="cart-x" id="cartClose" aria-label="Close">&times;</button></div>' +
    '<div id="cartItems"></div>' +
    '<div class="cart-foot" id="cartFoot">' +
    '<div class="cart-row"><span id="cartSubL"></span><span id="cartSub"></span></div>' +
    '<div class="cart-row" id="cartDiscRow" style="display:none"><span id="cartDiscL"></span><span id="cartDisc"></span></div>' +
    '<label id="cartShipL" for="cartShipSel"></label>' +
    '<select id="cartShipSel">' +
    '<option value="CA"></option><option value="US"></option><option value="INT"></option>' +
    "</select>" +
    '<div class="cart-row"><span id="cartShipAmtL"></span><span id="cartShipAmt"></span></div>' +
    '<input type="text" id="cartCoupon" maxlength="32" style="text-transform:uppercase">' +
    '<div class="cart-row total"><span id="cartTotalL"></span><span id="cartTotal"></span></div>' +
    '<button type="button" class="btn btn-brass" id="cartCheckoutBtn"></button>' +
    '<div id="cartMsg"></div>' +
    "</div>";

  function mount() {
    var inner = document.querySelector(".header-inner");
    if (inner) {
      var toggle = inner.querySelector(".lang-toggle");
      if (toggle) inner.insertBefore(btn, toggle);
      else inner.appendChild(btn);
    }
    document.body.appendChild(overlay);
    document.body.appendChild(drawer);
    btn.addEventListener("click", open);
    overlay.addEventListener("click", close);
    document.getElementById("cartClose").addEventListener("click", close);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
    var sel = document.getElementById("cartShipSel");
    sel.value = shipCountry();
    sel.addEventListener("change", function () {
      try { localStorage.setItem(SHIP_KEY, sel.value); } catch (e) {}
      render();
    });
    var cp = document.getElementById("cartCoupon");
    var cpTimer = null;
    cp.addEventListener("input", function () {
      clearTimeout(cpTimer);
      cpTimer = setTimeout(function () { validateCoupon(cp.value); }, 500);
    });
    document.getElementById("cartCheckoutBtn").addEventListener("click", checkout);
    drawer.addEventListener("click", function (e) {
      var b = e.target.closest("[data-act]");
      if (!b) return;
      changeQty(b.getAttribute("data-k"), b.getAttribute("data-act"));
    });
    render();
    detectCountry();
  }

  function detectCountry() {
    var stored = null;
    try { stored = localStorage.getItem(SHIP_KEY); } catch (e) {}
    if (stored) return;
    try {
      var ctl = new AbortController();
      var to = setTimeout(function () { ctl.abort(); }, 4000);
      fetch("https://ipapi.co/country/", { signal: ctl.signal }).then(function (r) {
        return r.text();
      }).then(function (cc) {
        clearTimeout(to);
        cc = (cc || "").trim().toUpperCase();
        var v = cc === "CA" ? "CA" : cc === "US" ? "US" :
          (/^[A-Z]{2}$/.test(cc) ? "INT" : null);
        if (v) {
          try { localStorage.setItem(SHIP_KEY, v); } catch (e) {}
          document.getElementById("cartShipSel").value = v;
          render();
        }
      }).catch(function () { clearTimeout(to); });
    } catch (e) {}
  }

  function validateCoupon(code) {
    code = (code || "").trim().toUpperCase();
    if (!code) { pctOff = 0; render(); return; }
    fetch("/api/coupons/validate?code=" + encodeURIComponent(code))
      .then(function (r) { return r.json(); })
      .then(function (j) { pctOff = j.ok ? j.percent_off : 0; render(); })
      .catch(function () { pctOff = 0; render(); });
  }

  function count() {
    return load().reduce(function (n, it) { return n + (it.qty || 1); }, 0);
  }

  function render() {
    var items = load();
    var cc = document.getElementById("cartCount");
    var n = count();
    cc.textContent = n;
    cc.style.display = n ? "flex" : "none";
    document.getElementById("cartTitle").textContent = T("cart") +
      (n ? " (" + n + ")" : "");
    var box = document.getElementById("cartItems");
    var foot = document.getElementById("cartFoot");
    if (!items.length) {
      box.innerHTML = '<p class="muted" style="padding:18px 0">' + esc(T("empty")) + "</p>";
      foot.style.display = "none";
      return;
    }
    foot.style.display = "";
    /* Initials dedupe (mirrors the server): the first line carrying each
       distinct initials string bears the CA$5 charge; later lines with
       the same string are not charged again. */
    var seenIni = {}, iniCharged = {};
    items.forEach(function (it) {
      if (it.initials && !seenIni[it.initials]) {
        seenIni[it.initials] = true;
        iniCharged[keyOf(it)] = true;
      }
    });
    function lt(it) { return lineTotal(it, !!iniCharged[keyOf(it)]); }
    box.innerHTML = items.map(function (it) {
      var k = keyOf(it);
      var opts = optionsText(it);
      return '<div class="cart-line">' +
        (it.img ? '<img src="' + esc(it.img) + '" alt="">' : "") +
        '<div class="cl-main"><div class="cl-name">' + esc(it.name) + "</div>" +
        (opts ? '<div class="cl-opts">' + esc(opts) + "</div>" : "") +
        '<div class="cl-row"><span class="qty-ctl">' +
        '<button type="button" data-act="dec" data-k="' + esc(k) + '" aria-label="-">−</button>' +
        "<span>" + (it.qty || 1) + "</span>" +
        '<button type="button" data-act="inc" data-k="' + esc(k) + '" aria-label="+">+</button>' +
        "</span><strong>" + money(lt(it)) + "</strong></div>" +
        '<button type="button" class="cl-rm" data-act="rm" data-k="' + esc(k) + '">' +
        esc(T("remove")) + "</button>" +
        "</div></div>";
    }).join("");
    var sub = items.reduce(function (s, it) { return s + lt(it); }, 0);
    var disc = pctOff ? Math.round(sub * pctOff / 100) : 0;
    var ship = SHIP_CENTS[shipCountry()];
    document.getElementById("cartSubL").textContent = T("subtotal");
    document.getElementById("cartSub").textContent = money(sub);
    var drow = document.getElementById("cartDiscRow");
    drow.style.display = disc ? "flex" : "none";
    if (disc) {
      document.getElementById("cartDiscL").textContent = T("discount") + " (" + pctOff + "%)";
      document.getElementById("cartDisc").textContent = "−" + money(disc);
    }
    document.getElementById("cartShipL").textContent = T("ship_to");
    var sel = document.getElementById("cartShipSel");
    sel.options[0].textContent = T("ship_ca");
    sel.options[1].textContent = T("ship_us");
    sel.options[2].textContent = T("ship_intl");
    document.getElementById("cartShipAmtL").textContent = T("shipping");
    document.getElementById("cartShipAmt").textContent = money(ship);
    document.getElementById("cartCoupon").setAttribute("placeholder", T("coupon_ph"));
    document.getElementById("cartTotalL").textContent = T("total");
    document.getElementById("cartTotal").textContent = money(sub - disc + ship);
    document.getElementById("cartCheckoutBtn").textContent = T("checkout");
  }

  function open() { render(); drawer.classList.add("open"); overlay.classList.add("open"); }
  function close() { drawer.classList.remove("open"); overlay.classList.remove("open"); }

  function changeQty(k, act) {
    var items = load();
    for (var i = 0; i < items.length; i++) {
      if (keyOf(items[i]) !== k) continue;
      if (act === "rm") items.splice(i, 1);
      else if (act === "inc") items[i].qty = Math.min(10, (items[i].qty || 1) + 1);
      else if (act === "dec") items[i].qty = Math.max(1, (items[i].qty || 1) - 1);
      break;
    }
    save(items);
    render();
  }

  function add(it) {
    if (!it || !it.pid) return;
    it.qty = Math.max(1, Math.min(10, it.qty || 1));
    var items = load();
    var k = keyOf(it);
    var found = false;
    for (var i = 0; i < items.length; i++) {
      if (keyOf(items[i]) === k) {
        items[i].qty = Math.min(10, (items[i].qty || 1) + it.qty);
        found = true;
        break;
      }
    }
    if (!found) items.push(it);
    save(items);
    render();
    // first-party analytics: record the add (product id only, no personal data)
    try {
      var _b = JSON.stringify({ type: "addcart", path: location.pathname, target: it.pid,
        sid: sessionStorage.getItem("adn_sid") || "", vid: localStorage.getItem("adn_vid") || "" });
      if (navigator.sendBeacon) navigator.sendBeacon("/api/track", new Blob([_b], { type: "application/json" }));
    } catch (e) {}
    var cc = document.getElementById("cartCount");
    cc.classList.add("bump");
    setTimeout(function () { cc.classList.remove("bump"); }, 200);
  }

  function checkout() {
    var items = load();
    if (!items.length) return;
    var btnEl = document.getElementById("cartCheckoutBtn");
    var msg = document.getElementById("cartMsg");
    btnEl.disabled = true;
    btnEl.textContent = T("preparing");
    msg.innerHTML = "";
    var payload = {
      items: items.map(function (it) {
        return {
          product_id: it.pid, qty: it.qty || 1,
          engraving_text: it.engraving || "", design: it.design || "",
          saint: it.saint || "", size: it.size || "", color: it.color || "",
          initials: it.initials || ""
        };
      }),
      coupon: document.getElementById("cartCoupon").value.trim(),
      ship_country: shipCountry(),
      lang: lang()
    };
    fetch("/api/cart-checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.url) { window.location = j.url; return; }
      msg.innerHTML = '<div class="notice notice-err">' + esc(j.error || T("failed")) + "</div>";
      btnEl.disabled = false;
      btnEl.textContent = T("checkout");
    }).catch(function () {
      msg.innerHTML = '<div class="notice notice-err">' + esc(T("failed")) + "</div>";
      btnEl.disabled = false;
      btnEl.textContent = T("checkout");
    });
  }

  /* ---------- adding from pages ---------- */
  function ensurePrices(cb) {
    if (priceMap) { cb(priceMap); return; }
    fetch("/api/products").then(function (r) { return r.json(); })
      .then(function (list) {
        priceMap = {};
        (list.products || list || []).forEach(function (p) { priceMap[p.id] = p; });
        cb(priceMap);
      }).catch(function () { priceMap = {}; cb(priceMap); });
  }

  function addFromProductPage(addBtn) {
    var m = window.location.pathname.match(/\/product\/(.+)$/);
    if (!m) return;
    var pid = decodeURIComponent(m[1]);
    ensurePrices(function (map) {
      var p = map[pid] || {};
      var qtyEl = document.getElementById("qty");
      var qty = qtyEl ? (parseInt(qtyEl.value, 10) || 1) : 1;
      var unit = p.price_cents || 0;
      var size = "", saint = "", design = "", engraving = "", color = "";
      var cs = document.getElementById("colorSelect");
      if (cs) color = cs.value;
      var sz = document.getElementById("sizeSelect");
      if (sz) {
        size = sz.value;
        var dp = sz.options[sz.selectedIndex].getAttribute("data-price");
        if (dp) unit = parseInt(dp, 10);
      }
      var ss = document.getElementById("saintSelect");
      if (ss) saint = ss.value;
      var initials = "";
      var iniT = document.getElementById("initialsText"),
        iniC = document.getElementById("initialsToggle");
      if (iniT && iniC && iniC.checked) initials = iniT.value.trim().toUpperCase();
      var eng = document.getElementById("engraving");
      if (eng) engraving = eng.value.trim();
      var dmode = document.querySelector('input[name="designmode"]:checked');
      if (dmode) {
        if (dmode.value === "gallery") {
          var ds = document.getElementById("designSelect");
          if (ds) design = ds.value;
        } else {
          var du = document.getElementById("designUploadId");
          if (du && du.value) design = "Custom upload " + du.value;
        }
      }
      var name = p.name || "";
      if (lang() === "fr" && (p.name_fr || "").trim()) name = p.name_fr;
      if (!name) {
        var h1 = document.querySelector(".buy-box h1");
        name = h1 ? h1.textContent.trim() : pid;
      }
      var img = "";
      var gim = document.querySelector("#galMainWrap img, .product-gallery img");
      if (gim) img = gim.getAttribute("src") || "";
      add({
        pid: pid, name: name, img: img, qty: qty,
        unit_cents: unit, add_cents: p.additional_price_cents || 0,
        design: design, saint: saint, size: size, color: color,
        initials: initials, engraving: engraving
      });
      if (addBtn) {
        var orig = addBtn.textContent;
        addBtn.textContent = T("added");
        setTimeout(function () { addBtn.textContent = orig; }, 1500);
      }
    });
  }

  function bind() {
    var addBtn = document.getElementById("addCartBtn");
    if (addBtn) addBtn.addEventListener("click", function () { addFromProductPage(addBtn); });
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-addcart]");
      if (!b) return;
      add({
        pid: b.getAttribute("data-pid"),
        name: b.getAttribute("data-name") || "",
        img: b.getAttribute("data-img") || "",
        qty: 1,
        unit_cents: parseInt(b.getAttribute("data-price"), 10) || 0,
        add_cents: parseInt(b.getAttribute("data-add"), 10) || 0,
        design: "", saint: "", size: "", color: "", initials: "", engraving: ""
      });
      var orig = b.textContent;
      b.textContent = T("added");
      setTimeout(function () { b.textContent = orig; }, 1200);
    });
  }

  window.adnCart = { add: add, open: open, count: count };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { mount(); bind(); });
  } else {
    mount();
    bind();
  }
})();
