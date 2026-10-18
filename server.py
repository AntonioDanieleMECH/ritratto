#!/usr/bin/env python3
"""
ADN Creations: engineering design company site + store.

Pages (static in /static): index, work, shop, engraving, progress,
about, contact, thank-you, custom-lamp (4-sided lamp designer).
Server-rendered: /product/<id>, /announcement/<id>, /admin/ (token-gated).

Store: products live in SQLite (admin-manageable), Stripe Checkout in CAD.
Departments are tag-based: religious / electronic / gag.
Preorders: flagged per product with an expected ship date, recorded on orders.

Env vars:
  STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, SITE_URL, SECRET_KEY,
  ADMIN_TOKEN (protects /admin/ and /api/admin/*),
  DEMO_MODE=true (skip real payments),
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM (optional: email
    notifications for engraving requests; stored in DB regardless),
  FB_PAGE_TOKEN (optional: enables one-tap publish to the Making Stuff
    Facebook Page via the Graph API; without it the admin composes a
    ready-to-copy draft instead).
"""
import os
import re
import json
import uuid
import sqlite3
import shutil
import threading
import time
import smtplib
from email.message import EmailMessage
from datetime import datetime
from html import escape as h

import requests
from PIL import Image, ImageOps
from flask import Flask, request, jsonify, send_file, abort, redirect

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE, "static")
DATA_DIR = os.environ.get("DATA_DIR", BASE)  # /var/data on Render (persistent disk)
UPLOADS = os.path.join(DATA_DIR, "uploads")
LAMP_UPLOAD_DIR = os.path.join(STATIC_DIR, "lamp_uploads")
PRODUCT_IMG_DIR = os.path.join(STATIC_DIR, "img", "products")
DB = os.path.join(DATA_DIR, "jobs.db")
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(LAMP_UPLOAD_DIR, exist_ok=True)
os.makedirs(PRODUCT_IMG_DIR, exist_ok=True)

STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000").rstrip("/")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"
SUPPORT_EMAIL = "antonio.learningisfun@gmail.com"
FB_PAGE_ID = "1274653932393890"
FB_PAGE_URL = "https://www.facebook.com/61592937237761"
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")

DEPTS = ["religious", "electronic", "gag"]
DEPT_LABELS = {"religious": "Religious", "electronic": "Electronic", "gag": "Gag"}

app = Flask(__name__, static_folder="static", static_url_path="")
_secret = os.environ.get("SECRET_KEY")
if not _secret and not DEMO_MODE:
    raise RuntimeError("SECRET_KEY env var is required in production")
app.secret_key = _secret or "dev-secret-change-me"


# ---------- db ----------
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS products "
        "(id TEXT PRIMARY KEY, name TEXT, price_cents INTEGER DEFAULT 0, "
        " photo TEXT DEFAULT '', description TEXT DEFAULT '', "
        " depts TEXT DEFAULT '[]', stock INTEGER, preorder INTEGER DEFAULT 0, "
        " preorder_ship_date TEXT DEFAULT '', engravable INTEGER DEFAULT 0, "
        " purchasable INTEGER DEFAULT 1, custom_link TEXT DEFAULT '', "
        " active INTEGER DEFAULT 1, sort INTEGER DEFAULT 0, created TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS orders "
        "(id TEXT PRIMARY KEY, created TEXT, product_id TEXT, product_name TEXT, "
        " amount_cents INTEGER, qty INTEGER DEFAULT 1, engraving_text TEXT DEFAULT '', "
        " preorder INTEGER DEFAULT 0, preorder_ship_date TEXT DEFAULT '', "
        " email TEXT DEFAULT '', paid INTEGER DEFAULT 0, stripe_session TEXT DEFAULT '')"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS announcements "
        "(id TEXT PRIMARY KEY, created TEXT, title TEXT, body TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS wip_projects "
        "(id TEXT PRIMARY KEY, project TEXT, status TEXT DEFAULT '', "
        " photo TEXT DEFAULT '', sort INTEGER DEFAULT 0, created TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS wip_updates "
        "(id TEXT PRIMARY KEY, project_id TEXT, created TEXT, text TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS engraving_requests "
        "(id TEXT PRIMARY KEY, created TEXT, name TEXT, email TEXT, "
        " product TEXT, message TEXT)"
    )
    # legacy lamp designer orders
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lamp_orders "
        "(id TEXT PRIMARY KEY, created TEXT, design TEXT, pack TEXT, "
        " amount INTEGER, paid INTEGER DEFAULT 0, stripe_session TEXT, sides TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS visits "
        "(day TEXT, path TEXT, count INTEGER DEFAULT 0, PRIMARY KEY (day, path))"
    )
    return conn


def track_visit(path):
    try:
        day = datetime.utcnow().strftime("%Y-%m-%d")
        conn = db()
        conn.execute("INSERT OR IGNORE INTO visits (day, path, count) VALUES (?,?,0)",
                     (day, path))
        conn.execute("UPDATE visits SET count = count + 1 WHERE day=? AND path=?",
                     (day, path))
        conn.commit()
        conn.close()
    except Exception:  # noqa: BLE001
        pass


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")


# ---------- seed data ----------
SEED_PRODUCTS = [
    {"id": "carlo-lamp", "name": "Carlo Acutis 4-Face Prayer Lamp", "price_cents": 2499,
     "photo": "/img/products/carlo-lamp.jpg",
     "description": "Four lithophane faces of Carlo Acutis glow from within: portrait, with the Eucharist, his Assisi sanctuary, and the Virgin Mary. Warm LED light, 10 x 7 x 7 cm. Hand crafted in LaSalle, Montreal from plant-based bioplastic.",
     "depts": ["religious", "electronic"], "stock": None, "sort": 1},
    {"id": "sheen-lamp", "name": "Fulton Sheen 4-Face Prayer Lamp", "price_cents": 1999,
     "photo": "",
     "description": "Four lithophane faces of Blessed Fulton Sheen in warm LED light. Hand crafted in LaSalle, Montreal from plant-based bioplastic.",
     "depts": ["religious", "electronic"], "stock": None, "sort": 2},
    {"id": "memorial-lamp", "name": "Custom Memorial Lamp", "price_cents": 2000,
     "photo": "/img/products/memorial-lamp.jpg",
     "description": "Your photos or our saint illustrations on four glowing faces. $20 for the first lamp of a design, $15 for each additional copy of the same design. Use the lamp designer to compose your four sides.",
     "depts": ["religious", "electronic"], "stock": None, "custom_link": "/custom-lamp.html", "sort": 3},
    {"id": "bust-collector", "name": "Saint Frere Andre Bust, Collector's Edition", "price_cents": 225000,
     "photo": "/img/products/bust.jpg",
     "description": "One of one. 39 cm hand finished bust on a dark stained wood base with a brass Fr. Andre name plate. Heavy, highly detailed, made with additive manufacturing and plant-based materials with very little waste. Free shipping.",
     "depts": ["religious"], "stock": 1, "sort": 4},
    {"id": "nativity", "name": "Nativity Scene Lamp", "price_cents": 3999,
     "photo": "/img/products/nativity.jpg",
     "description": "The Nativity rendered as a glowing lithophane lamp. Warm LED light. Hand crafted in LaSalle, Montreal from plant-based bioplastic.",
     "depts": ["religious", "electronic"], "stock": None, "sort": 5},
    {"id": "lighter", "name": "Engraved Lighter", "price_cents": 2400,
     "photo": "/img/products/lighter.jpg",
     "description": "Zippo-style lighter with your text or artwork laser engraved. Add your engraving text at checkout and we will lay it out for you.",
     "depts": ["gag"], "stock": None, "engravable": 1, "sort": 6},
    {"id": "mug", "name": "Engraved Contigo Travel Mug", "price_cents": 3400,
     "photo": "/img/products/mug.jpg",
     "description": "Contigo travel mug with your text laser engraved. Add your engraving text at checkout.",
     "depts": [], "stock": None, "engravable": 1, "sort": 7},
    {"id": "card-case", "name": "Italian Playing-Card Case", "price_cents": 2500,
     "photo": "",
     "description": "Fitted case for Italian playing cards, Scopa and Briscola sizes. Hand crafted from plant-based bioplastic.",
     "depts": [], "stock": None, "sort": 8},
    {"id": "giftcard-case", "name": "Gift-Card Case", "price_cents": 1500,
     "photo": "",
     "description": "A keepsake case that turns a gift card into a real gift. Hand crafted from plant-based bioplastic.",
     "depts": [], "stock": None, "sort": 9},
    {"id": "battery-door", "name": "Threaded Battery Door", "price_cents": 1200,
     "photo": "",
     "description": "Precision threaded battery door, printed to fit. Hand crafted from plant-based bioplastic.",
     "depts": [], "stock": None, "sort": 10},
    {"id": "gag-soon", "name": "Gag Department", "price_cents": 0,
     "photo": "",
     "description": "Novelty and funny items are on the way. Check back soon.",
     "depts": ["gag"], "purchasable": 0, "sort": 11},
]


def seed():
    conn = db()
    n = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if n == 0:
        for p in SEED_PRODUCTS:
            conn.execute(
                "INSERT INTO products (id, name, price_cents, photo, description, depts, "
                "stock, preorder, preorder_ship_date, engravable, purchasable, custom_link, "
                "active, sort, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p["id"], p["name"], p["price_cents"], p.get("photo", ""),
                 p.get("description", ""), json.dumps(p.get("depts", [])),
                 p.get("stock"), 0, "", p.get("engravable", 0),
                 p.get("purchasable", 1), p.get("custom_link", ""), 1,
                 p.get("sort", 0), now_iso()))
    if conn.execute("SELECT COUNT(*) FROM announcements").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO announcements (id, created, title, body) VALUES (?,?,?,?)",
            ("seed1", "2026-10-18T09:00:00",
             "The ADN Creations store is now live",
             "You can now order directly from this site. Every piece is designed and hand crafted in LaSalle, Montreal."))
        conn.execute(
            "INSERT INTO announcements (id, created, title, body) VALUES (?,?,?,?)",
            ("seed2", "2026-10-18T09:00:00",
             "Ordering direct",
             "Our Etsy shop is temporarily under review, so all ordering happens right here for now. Same products, same maker, direct from the workshop."))
    if conn.execute("SELECT COUNT(*) FROM wip_projects").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO wip_projects (id, project, status, photo, sort, created) VALUES (?,?,?,?,?,?)",
            ("clock", "Mechanical Regulator Clock", "In development", "", 1, now_iso()))
        conn.execute(
            "INSERT INTO wip_updates (id, project_id, created, text) VALUES (?,?,?,?)",
            ("c1", "clock", "2026-10-16T12:00:00",
             "Case design v4 complete: arched printed case with raised-numeral two-colour dials, deadbeat escapement, 135:1 going train and 12:1 hour motion work."))
        conn.execute(
            "INSERT INTO wip_updates (id, project_id, created, text) VALUES (?,?,?,?)",
            ("c2", "clock", "2026-10-18T09:00:00",
             "Fit test next: verifying the going train meshes cleanly before the full kit print. Spring torque still to be validated."))
        conn.execute(
            "INSERT INTO wip_projects (id, project, status, photo, sort, created) VALUES (?,?,?,?,?,?)",
            ("bust", "Saint Frere Andre Collector's Edition Bust", "Complete", "/img/work/bust-front.jpg", 2, now_iso()))
        conn.execute(
            "INSERT INTO wip_updates (id, project_id, created, text) VALUES (?,?,?,?)",
            ("b1", "bust", "2026-10-18T09:00:00",
             "Finished. 1 of 1. 39 cm on a dark stained wood base with a brass Fr. Andre name plate. Listed in the shop."))
    conn.commit()
    conn.close()


# ---------- shared HTML shell (mirrors static pages) ----------
FONT_LINK = ("<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">"
             "<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>"
             "<link href=\"https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700"
             "&family=Inter:wght@400;500;600;700&display=swap\" rel=\"stylesheet\">")

NAV_LINKS = [("work", "Work", "/work.html"), ("shop", "Shop", "/shop.html"),
             ("engraving", "Engraving", "/engraving.html"),
             ("progress", "Progress", "/progress.html"),
             ("about", "About", "/about.html"), ("contact", "Contact", "/contact.html")]


def shell(title, description, body, active="", og_image="", og_url=""):
    nav = "".join(
        f'<a href="{u}" class="{"active" if k == active else ""}">{l}</a>'
        for k, l, u in NAV_LINKS)
    og = ""
    if og_image:
        og = (f'<meta property="og:title" content="{h(title)}">'
              f'<meta property="og:description" content="{h(description)}">'
              f'<meta property="og:type" content="website">'
              f'<meta property="og:url" content="{h(og_url)}">'
              f'<meta property="og:image" content="{h(og_image)}">'
              '<meta name="twitter:card" content="summary_large_image">')
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{h(title)} | ADN Creations</title>
<meta name="description" content="{h(description)}">
{FONT_LINK}
<link rel="stylesheet" href="/style.css">
{og}
</head>
<body>
<header class="site-header"><div class="wrap header-inner">
<a class="brand" href="/">ADN <span>Creations</span></a>
<nav class="nav-links" id="navLinks">{nav}<a href="/shop.html" class="nav-cta">Shop now</a></nav>
<button class="hamburger" id="navToggle" aria-label="Menu">&#9776;</button>
</div></header>
{body}
<footer class="site-footer"><div class="wrap footer-inner">
<div class="footer-grid">
<div>
<div class="footer-brand">ADN <span>Creations</span></div>
<p class="small" style="color:#B9AE97">Engineering design company. Hand crafted additive manufacturing in LaSalle, Montreal, from plant-based materials.</p>
<a class="social-btn" href="{FB_PAGE_URL}" target="_blank" rel="noopener">Follow our builds on Making Stuff</a>
</div>
<div><h4>Explore</h4><ul class="footer-links">
<li><a href="/work.html">Work</a></li><li><a href="/shop.html">Shop</a></li>
<li><a href="/engraving.html">Engraving</a></li><li><a href="/progress.html">Progress</a></li>
<li><a href="/about.html">About</a></li><li><a href="/contact.html">Contact</a></li>
</ul></div>
<div><h4>Contact</h4><ul class="footer-links">
<li><a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></li>
<li>LaSalle, Montreal, QC</li><li>NEQ 2281797763</li>
</ul></div>
</div>
<div class="footer-bottom"><span>&copy; 2026 ADN Creations. All rights reserved.</span><span>Designed and built in Montreal.</span></div>
</div></footer>
<script>document.getElementById('navToggle').addEventListener('click',function(){{document.getElementById('navLinks').classList.toggle('open')}});</script>
</body>
</html>"""


def abs_url(path):
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return SITE_URL + path


def money(cents):
    return f"${cents / 100:,.2f}"


def get_product(pid):
    conn = db()
    row = conn.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
    conn.close()
    return row


def product_badges(p):
    out = []
    if p["preorder"]:
        out.append('<span class="badge badge-preorder">Preorder</span>')
    if p["stock"] is not None and p["stock"] <= 3 and p["purchasable"]:
        out.append(f'<span class="badge badge-stock">Only {p["stock"]} left</span>')
    return " ".join(out)


def product_media(p, cls="card-media"):
    if p["photo"]:
        return f'<div class="{cls}"><img src="{h(p["photo"])}" alt="{h(p["name"])}" loading="lazy"></div>'
    return f'<div class="{cls}"><div class="photo-placeholder">Photo coming soon</div></div>'


# ---------- public pages ----------
@app.route("/")
def index():
    track_visit("/")
    return app.send_static_file("index.html")


@app.route("/product/<pid>")
def product_page(pid):
    p = get_product(pid)
    if not p:
        abort(404)
    track_visit(f"/product/{pid}")
    depts = json.loads(p["depts"] or "[]")
    tags = " ".join(f'<span class="dept-tag">{DEPT_LABELS.get(d, d)}</span>' for d in depts)
    engraving_field = ""
    if p["engravable"]:
        engraving_field = ('<div class="field"><label for="engraving">Custom engraving text '
                           '(optional)</label><input type="text" id="engraving" maxlength="120" '
                           'placeholder="e.g. Aku, Est. 2026"></div>')
    preorder_note = ""
    if p["preorder"]:
        preorder_note = (f'<div class="preorder-note">This is a preorder. Expected to ship '
                         f'{h(p["preorder_ship_date"] or "soon")}. You will be charged today.</div>')
    buy_html = ""
    if p["purchasable"]:
        if p["stock"] is not None and p["stock"] <= 0:
            buy_html = '<div class="notice notice-err">Sold out.</div>'
        else:
            label = "Preorder now" if p["preorder"] else "Buy now"
            buy_html = (f'<button class="btn btn-brass btn-block" id="buyBtn">{label} &middot; {money(p["price_cents"])}</button>'
                        '<p class="small muted" style="margin-top:10px">Secure checkout with Stripe. Flat-rate shipping for Canada and the US calculated at checkout.</p>')
    else:
        buy_html = '<div class="notice">Coming soon. Not available for order yet.</div>'
    custom = ""
    if p["custom_link"]:
        custom = f'<a class="btn btn-outline btn-block" href="{h(p["custom_link"])}" style="margin-top:10px">Design yours</a>'
    body = f"""
<div class="wrap"><div class="product-detail">
<div>
<div class="product-gallery">{product_media(p, "").replace('class="card-media"', 'class=""') if p["photo"] else '<div class="photo-placeholder">Photo coming soon</div>'}</div>
</div>
<div>
<div class="buy-box">
<p class="kicker">ADN Creations</p>
<h1 style="font-size:2rem">{h(p["name"])}</h1>
<div class="dept-tags" style="margin-bottom:12px">{tags} {product_badges(p)}</div>
<p class="price">{money(p["price_cents"])}</p>
<p class="muted">{h(p["description"])}</p>
{preorder_note}
<div class="field"><label for="qty">Quantity</label>
<input type="number" id="qty" value="1" min="1" max="10"></div>
{engraving_field}
{buy_html}{custom}
<div id="buyMsg" style="margin-top:12px"></div>
</div>
</div>
</div></div>
<script>
document.getElementById('buyBtn') && document.getElementById('buyBtn').addEventListener('click', async function() {{
  var btn = this; btn.disabled = true; btn.textContent = 'Preparing checkout...';
  var payload = {{ product_id: {json.dumps(p["id"])}, qty: parseInt(document.getElementById('qty').value) || 1 }};
  var eng = document.getElementById('engraving');
  if (eng) payload.engraving_text = eng.value;
  try {{
    var r = await fetch('/api/checkout', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(payload) }});
    var j = await r.json();
    if (j.url) window.location = j.url;
    else {{ document.getElementById('buyMsg').innerHTML = '<div class="notice notice-err">' + (j.error || 'Checkout failed.') + '</div>'; btn.disabled = false; }}
  }} catch(e) {{ document.getElementById('buyMsg').innerHTML = '<div class="notice notice-err">Checkout failed. Please try again.</div>'; btn.disabled = false; }}
}});
</script>"""
    return shell(p["name"], p["description"][:160],
                 body, active="shop",
                 og_image=abs_url(p["photo"]), og_url=f"{SITE_URL}/product/{pid}")


@app.route("/announcement/<aid>")
def announcement_page(aid):
    conn = db()
    a = conn.execute("SELECT * FROM announcements WHERE id=?", (aid,)).fetchone()
    conn.close()
    if not a:
        abort(404)
    track_visit(f"/announcement/{aid}")
    try:
        dt = datetime.fromisoformat(a["created"]).strftime("%B %d, %Y")
    except ValueError:
        dt = a["created"][:10]
    body = f"""
<div class="wrap section"><div style="max-width:680px">
<p class="kicker"><a href="/progress.html" style="text-decoration:none">Announcements</a></p>
<p class="feed-date">{h(dt)}</p>
<h1>{h(a["title"])}</h1>
<p class="lede">{h(a["body"])}</p>
</div></div>"""
    return shell(a["title"], a["body"][:160], body, active="progress",
                 og_image=abs_url("/img/products/carlo-lamp.jpg"),
                 og_url=f"{SITE_URL}/announcement/{aid}")


# ---------- public APIs ----------
@app.route("/api/products")
def api_products():
    dept = (request.args.get("dept") or "").strip()
    conn = db()
    rows = conn.execute("SELECT * FROM products WHERE active=1 ORDER BY sort, name").fetchall()
    conn.close()
    out = []
    for p in rows:
        depts = json.loads(p["depts"] or "[]")
        if dept and dept not in depts:
            continue
        out.append({"id": p["id"], "name": p["name"], "price_cents": p["price_cents"],
                    "price": money(p["price_cents"]), "photo": p["photo"],
                    "description": p["description"], "depts": depts,
                    "stock": p["stock"], "preorder": bool(p["preorder"]),
                    "preorder_ship_date": p["preorder_ship_date"],
                    "engravable": bool(p["engravable"]),
                    "purchasable": bool(p["purchasable"]),
                    "custom_link": p["custom_link"]})
    return jsonify({"products": out, "depts": DEPT_LABELS})


@app.route("/api/announcements")
def api_announcements():
    conn = db()
    rows = conn.execute("SELECT * FROM announcements ORDER BY created DESC LIMIT 30").fetchall()
    conn.close()
    return jsonify({"announcements": [dict(r) for r in rows]})


@app.route("/api/wip")
def api_wip():
    conn = db()
    projects = conn.execute("SELECT * FROM wip_projects ORDER BY sort, created").fetchall()
    out = []
    for pr in projects:
        updates = conn.execute(
            "SELECT * FROM wip_updates WHERE project_id=? ORDER BY created DESC",
            (pr["id"],)).fetchall()
        d = dict(pr)
        d["updates"] = [dict(u) for u in updates]
        out.append(d)
    conn.close()
    return jsonify({"projects": out})


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    data = request.get_json(force=True)
    pid = (data.get("product_id") or "").strip()
    qty = max(1, min(10, int(data.get("qty") or 1)))
    engraving = (data.get("engraving_text") or "").strip()[:200]
    p = get_product(pid)
    if not p or not p["purchasable"]:
        return jsonify({"error": "unknown product"}), 404
    if p["stock"] is not None and p["stock"] < qty:
        return jsonify({"error": "not enough stock"}), 400
    amount = p["price_cents"] * qty
    oid = "ord_" + uuid.uuid4().hex[:12]
    conn = db()
    conn.execute(
        "INSERT INTO orders (id, created, product_id, product_name, amount_cents, qty, "
        "engraving_text, preorder, preorder_ship_date, paid) VALUES (?,?,?,?,?,?,?,?,?,0)",
        (oid, now_iso(), pid, p["name"], amount, qty, engraving,
         p["preorder"], p["preorder_ship_date"]))
    conn.commit()
    conn.close()
    label = p["name"] + (f" x{qty}" if qty > 1 else "")
    if p["preorder"]:
        label = "PREORDER: " + label
    if engraving:
        label += f" (engraving: {engraving[:60]})"
    if not STRIPE_SECRET:
        if DEMO_MODE:
            mark_order_paid(oid, "")
            return jsonify({"url": f"{SITE_URL}/thank-you.html?order={oid}", "demo": True})
        return jsonify({"error": "payments are not configured yet, please try again later"}), 503
    import stripe
    stripe.api_key = STRIPE_SECRET
    sess = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price_data": {
            "currency": "cad", "unit_amount": amount,
            "product_data": {"name": label}}, "quantity": 1}],
        mode="payment",
        shipping_address_collection={"allowed_countries": ["CA", "US"]},
        shipping_options=[{"shipping_rate_data": {
            "type": "fixed_amount",
            "fixed_amount": {"amount": 1000, "currency": "cad"},
            "display_name": "Flat-rate shipping (CA/US)"}}],
        success_url=f"{SITE_URL}/thank-you.html?order={oid}",
        cancel_url=f"{SITE_URL}/product/{pid}?cancelled=1",
        metadata={"order_id": oid, "kind": "shop"},
    )
    conn = db()
    conn.execute("UPDATE orders SET stripe_session=? WHERE id=?", (sess.id, oid))
    conn.commit()
    conn.close()
    return jsonify({"url": sess.url})


@app.route("/api/order/<oid>")
def api_order(oid):
    if not re.fullmatch(r"ord_[0-9a-f]{12}", oid or ""):
        abort(404)
    conn = db()
    o = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    conn.close()
    if not o:
        abort(404)
    d = dict(o)
    d["price"] = money(d["amount_cents"])
    return jsonify(d)


def mark_order_paid(oid, email=""):
    conn = db()
    conn.execute("UPDATE orders SET paid=1, email=? WHERE id=?", (email, oid))
    row = conn.execute("SELECT product_id FROM orders WHERE id=?", (oid,)).fetchone()
    if row:
        conn.execute("UPDATE products SET stock = stock - "
                     "(SELECT qty FROM orders WHERE id=?) "
                     "WHERE id=? AND stock IS NOT NULL", (oid, row["product_id"]))
    conn.commit()
    conn.close()


# ---------- engraving requests ----------
def send_email(to, subject, body):
    host = os.environ.get("SMTP_HOST", "")
    if not host:
        return False, "SMTP not configured"
    try:
        msg = EmailMessage()
        msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", ""))
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
            s.send_message(msg)
        return True, "sent"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


@app.route("/api/engraving-request", methods=["POST"])
def api_engraving_request():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()[:120]
    email = (data.get("email") or "").strip()[:160]
    product = (data.get("product") or "").strip()[:120]
    message = (data.get("message") or "").strip()[:2000]
    if not name or not message or "@" not in email:
        return jsonify({"error": "please include your name, a valid email, and what you want engraved"}), 400
    rid = "eng_" + uuid.uuid4().hex[:10]
    conn = db()
    conn.execute(
        "INSERT INTO engraving_requests (id, created, name, email, product, message) "
        "VALUES (?,?,?,?,?,?)", (rid, now_iso(), name, email, product, message))
    conn.commit()
    conn.close()
    ok, _ = send_email(
        SUPPORT_EMAIL, f"New engraving request from {name}",
        f"Name: {name}\nEmail: {email}\nProduct: {product or 'not specified'}\n\n{message}\n")
    return jsonify({"ok": True, "emailed": ok})


# ---------- custom 4-sided lamp designer (kept from Ritratto, rebranded) ----------
GALLERY = {
    "solanus-casey": {"name": "Blessed Solanus Casey", "image": "/lamps/gallery/solanus-casey.jpg"},
    "frere-andre": {"name": "Frere Andre", "image": "/lamps/gallery/bishop-example.jpg"},
    "padrepio-face": {"name": "Padre Pio", "image": "/lamps/gallery/padrepio-face.jpg"},
    "padrepio-mass": {"name": "Padre Pio at Mass", "image": "/lamps/gallery/padrepio-mass.jpg"},
    "ourlady-child": {"name": "Our Lady with Child", "image": "/lamps/gallery/ourlady-child.jpg"},
    "carlo-standing": {"name": "Carlo Acutis, Standing", "image": "/lamps/carlo-standing.jpg"},
    "carlo-monstrance": {"name": "Carlo Acutis with the Eucharist", "image": "/lamps/carlo-monstrance.jpg"},
    "our-lady": {"name": "Our Lady of the Rosary", "image": "/lamps/our-lady.jpg"},
    "basilica-padrepio": {"name": "Basilica", "image": "/lamps/basilica-padrepio.jpg"},
}
LAMP_SINGLE = 2000   # $20 first of a design
LAMP_SET4 = 6000     # $60 for 4 copies of the same design
LAMP_SHIPPING = 1000


def load_upright(stream):
    return ImageOps.exif_transpose(Image.open(stream)).convert("RGB")


@app.route("/api/lamp-upload", methods=["POST"])
def lamp_upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400
    name = "side_" + uuid.uuid4().hex[:10] + ".jpg"
    path = os.path.join(LAMP_UPLOAD_DIR, name)
    try:
        img = load_upright(f.stream)
        img.thumbnail((1200, 1200), Image.LANCZOS)
        img.save(path, "JPEG", quality=88)
    except Exception:
        return jsonify({"error": "could not read that image"}), 400
    return jsonify({"file": name, "url": "/lamp_uploads/" + name})


@app.route("/api/gallery")
def api_gallery():
    return jsonify({"gallery": [{"id": k, **v} for k, v in GALLERY.items()],
                    "single_cents": LAMP_SINGLE, "set4_cents": LAMP_SET4})


def validate_sides(sides):
    if not isinstance(sides, list) or len(sides) != 4:
        raise ValueError("choose all 4 sides")
    clean, names = [], []
    for s in sides:
        kind = (s or {}).get("kind")
        if kind == "gallery":
            gid = s.get("id") or ""
            if gid not in GALLERY:
                raise ValueError("unknown illustration")
            clean.append({"kind": "gallery", "id": gid})
            names.append(GALLERY[gid]["name"])
        elif kind == "upload":
            fname = s.get("file") or ""
            if not re.fullmatch(r"side_[0-9a-f]{10}\.jpg", fname):
                raise ValueError("unknown upload")
            if not os.path.isfile(os.path.join(LAMP_UPLOAD_DIR, fname)):
                raise ValueError("upload not found")
            clean.append({"kind": "upload", "file": fname})
            names.append("your photo")
        else:
            raise ValueError("choose all 4 sides")
    return clean, names


@app.route("/api/lamp-checkout", methods=["POST"])
def lamp_checkout():
    data = request.get_json(force=True)
    pack = data.get("pack") or "single"
    if pack not in ("single", "set4"):
        return jsonify({"error": "unknown lamp option"}), 400
    try:
        sides, names = validate_sides(data.get("sides"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    amount = LAMP_SET4 if pack == "set4" else LAMP_SINGLE
    side_summary = " / ".join(names)
    label = (f"Custom memorial lamp ({'4 copies' if pack == 'set4' else 'single'})"
             f" - {side_summary[:120]}")
    oid = "lamp_" + uuid.uuid4().hex[:10]
    conn = db()
    conn.execute(
        "INSERT INTO lamp_orders (id, created, design, pack, amount, paid, sides) "
        "VALUES (?,?,?,?,?,0,?)",
        (oid, now_iso(), "custom", pack, amount, json.dumps(sides)))
    conn.commit()
    conn.close()
    if not STRIPE_SECRET:
        if DEMO_MODE:
            conn = db()
            conn.execute("UPDATE lamp_orders SET paid=1 WHERE id=?", (oid,))
            conn.commit()
            conn.close()
            return jsonify({"url": f"{SITE_URL}/thank-you.html?order={oid}", "demo": True})
        return jsonify({"error": "payments are not configured yet, please try again later"}), 503
    import stripe
    stripe.api_key = STRIPE_SECRET
    sess = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price_data": {
            "currency": "cad", "unit_amount": amount,
            "product_data": {"name": label}}, "quantity": 1}],
        mode="payment",
        shipping_address_collection={"allowed_countries": ["CA", "US"]},
        shipping_options=[{"shipping_rate_data": {
            "type": "fixed_amount",
            "fixed_amount": {"amount": LAMP_SHIPPING, "currency": "cad"},
            "display_name": "Flat-rate shipping (CA/US)"}}],
        success_url=f"{SITE_URL}/thank-you.html?order={oid}",
        cancel_url=f"{SITE_URL}/custom-lamp.html?cancelled=1",
        metadata={"order_id": oid, "kind": "lamp", "sides": side_summary[:400]},
    )
    conn = db()
    conn.execute("UPDATE lamp_orders SET stripe_session=? WHERE id=?", (sess.id, oid))
    conn.commit()
    conn.close()
    return jsonify({"url": sess.url})


# ---------- stripe webhook ----------
@app.route("/webhook/stripe", methods=["POST"])
def webhook():
    import stripe
    payload = request.data
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        return "bad signature", 400
    if event["type"] == "checkout.session.completed":
        obj = event["data"]["object"]
        meta = obj.get("metadata", {})
        email = (obj.get("customer_details") or {}).get("email", "")
        if meta.get("kind") == "shop" and meta.get("order_id"):
            mark_order_paid(meta["order_id"], email)
        elif meta.get("kind") == "lamp" and meta.get("order_id"):
            conn = db()
            conn.execute("UPDATE lamp_orders SET paid=1 WHERE id=?", (meta["order_id"],))
            conn.commit()
            conn.close()
    return "ok", 200


# ---------- admin ----------
def admin_ok():
    if not ADMIN_TOKEN:
        return False
    token = request.args.get("token", "") or request.headers.get("X-Admin-Token", "")
    return token == ADMIN_TOKEN


@app.route("/admin/")
def admin_page():
    if not admin_ok():
        abort(403)
    token = request.args.get("token", "")
    body = f"""
<div class="admin-wrap">
<p class="kicker">ADN Creations</p>
<h1>Store admin</h1>
<p class="muted">Manage products, preorders, announcements, work-in-progress updates, and orders. Changes go live immediately.</p>

<div class="admin-card">
<h2>Products</h2>
<div id="productList"></div>
<h3 style="margin-top:24px">Add / edit product</h3>
<form id="productForm">
<input type="hidden" id="pf-id">
<div class="field"><label>Name</label><input type="text" id="pf-name" required maxlength="120"></div>
<div class="two-col" style="gap:16px">
<div class="field"><label>Price (CAD)</label><input type="number" id="pf-price" step="0.01" min="0" required></div>
<div class="field"><label>Stock (blank = unlimited)</label><input type="number" id="pf-stock" min="0"></div>
</div>
<div class="field"><label>Photo</label><input type="file" id="pf-photo-file" accept="image/*">
<input type="text" id="pf-photo" placeholder="or paste an image URL, e.g. /img/products/x.jpg" style="margin-top:8px"></div>
<div class="field"><label>Departments</label><div class="checkbox-row" id="pf-depts"></div></div>
<div class="checkbox-row">
<label><input type="checkbox" id="pf-preorder"> Preorder</label>
<label><input type="checkbox" id="pf-engravable"> Engravable (text field at checkout)</label>
<label><input type="checkbox" id="pf-purchasable" checked> Available to buy</label>
<label><input type="checkbox" id="pf-active" checked> Visible in shop</label>
</div>
<div class="field" id="pf-shipdate-wrap" style="display:none"><label>Expected ship date (shown to buyer)</label><input type="text" id="pf-shipdate" placeholder="e.g. December 2026" maxlength="60"></div>
<div class="field"><label>Custom page link (optional, e.g. /custom-lamp.html)</label><input type="text" id="pf-customlink" maxlength="120"></div>
<div class="field"><label>Description</label><textarea id="pf-desc" maxlength="2000"></textarea></div>
<button class="btn btn-primary" type="submit">Save product</button>
<button class="btn btn-outline" type="button" id="pf-cancel" style="margin-left:8px">Clear</button>
</form>
</div>

<div class="admin-card">
<h2>Announcements</h2>
<div id="annList"></div>
<h3 style="margin-top:24px">New announcement</h3>
<form id="annForm">
<div class="field"><label>Title</label><input type="text" id="af-title" required maxlength="140"></div>
<div class="field"><label>Body</label><textarea id="af-body" required maxlength="2000"></textarea></div>
<button class="btn btn-primary" type="submit">Publish announcement</button>
</form>
</div>

<div class="admin-card">
<h2>Work in progress</h2>
<div id="wipList"></div>
<h3 style="margin-top:24px">New project</h3>
<form id="wipForm">
<div class="field"><label>Project name</label><input type="text" id="wf-project" required maxlength="120"></div>
<div class="field"><label>Status (e.g. In development, Complete)</label><input type="text" id="wf-status" maxlength="60"></div>
<button class="btn btn-primary" type="submit">Add project</button>
</form>
<h3 style="margin-top:24px">Add progress update</h3>
<form id="wipUpdateForm">
<div class="field"><label>Project</label><select id="wu-project"></select></div>
<div class="field"><label>Update</label><textarea id="wu-text" required maxlength="1000"></textarea></div>
<button class="btn btn-primary" type="submit">Add update</button>
</form>
</div>

<div class="admin-card">
<h2>Orders</h2>
<div id="orderList"><p class="muted">Loading...</p></div>
</div>

<div class="admin-card">
<h2>Engraving requests</h2>
<div id="engList"><p class="muted">Loading...</p></div>
</div>
</div>
<script>var ADMIN_TOKEN = {json.dumps(token)};</script>
<script src="/admin.js"></script>"""
    return shell("Store admin", "ADN Creations store administration.", body)


@app.route("/api/admin/products", methods=["GET", "POST"])
def admin_products():
    if not admin_ok():
        abort(403)
    conn = db()
    if request.method == "GET":
        rows = conn.execute("SELECT * FROM products ORDER BY sort, name").fetchall()
        conn.close()
        return jsonify({"products": [dict(r) for r in rows]})
    data = request.get_json(force=True)
    pid = (data.get("id") or "").strip() or ("p_" + uuid.uuid4().hex[:10])
    price = int(round(float(data.get("price") or 0) * 100))
    stock_raw = (data.get("stock") or "").strip() if isinstance(data.get("stock"), str) else data.get("stock")
    stock = int(stock_raw) if stock_raw not in ("", None) else None
    depts = [d for d in (data.get("depts") or []) if d in DEPTS]
    conn.execute(
        "INSERT INTO products (id, name, price_cents, photo, description, depts, stock, "
        "preorder, preorder_ship_date, engravable, purchasable, custom_link, active, sort, created) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, price_cents=excluded.price_cents, "
        "photo=excluded.photo, description=excluded.description, depts=excluded.depts, "
        "stock=excluded.stock, preorder=excluded.preorder, "
        "preorder_ship_date=excluded.preorder_ship_date, engravable=excluded.engravable, "
        "purchasable=excluded.purchasable, custom_link=excluded.custom_link, "
        "active=excluded.active",
        (pid, (data.get("name") or "").strip()[:120], price,
         (data.get("photo") or "").strip()[:300], (data.get("description") or "").strip()[:2000],
         json.dumps(depts), stock, 1 if data.get("preorder") else 0,
         (data.get("preorder_ship_date") or "").strip()[:60],
         1 if data.get("engravable") else 0, 1 if data.get("purchasable", True) else 0,
         (data.get("custom_link") or "").strip()[:120],
         1 if data.get("active", True) else 0,
         int(data.get("sort") or 0), now_iso()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": pid})


@app.route("/api/admin/products/<pid>", methods=["DELETE"])
def admin_product_delete(pid):
    if not admin_ok():
        abort(403)
    conn = db()
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/upload", methods=["POST"])
def admin_upload():
    if not admin_ok():
        abort(403)
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400
    name = "prod_" + uuid.uuid4().hex[:10] + ".jpg"
    try:
        img = ImageOps.exif_transpose(Image.open(f.stream)).convert("RGB")
        if img.width > 1400:
            img = img.resize((1400, int(img.height * 1400 / img.width)), Image.LANCZOS)
        img.save(os.path.join(PRODUCT_IMG_DIR, name), "JPEG", quality=80, optimize=True)
    except Exception:
        return jsonify({"error": "could not read that image"}), 400
    return jsonify({"url": "/img/products/" + name})


@app.route("/api/admin/announcements", methods=["GET", "POST"])
def admin_announcements():
    if not admin_ok():
        abort(403)
    conn = db()
    if request.method == "GET":
        rows = conn.execute("SELECT * FROM announcements ORDER BY created DESC").fetchall()
        conn.close()
        return jsonify({"announcements": [dict(r) for r in rows]})
    data = request.get_json(force=True)
    aid = "a_" + uuid.uuid4().hex[:10]
    conn.execute("INSERT INTO announcements (id, created, title, body) VALUES (?,?,?,?)",
                 (aid, now_iso(), (data.get("title") or "").strip()[:140],
                  (data.get("body") or "").strip()[:2000]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": aid})


@app.route("/api/admin/announcements/<aid>", methods=["DELETE"])
def admin_announcement_delete(aid):
    if not admin_ok():
        abort(403)
    conn = db()
    conn.execute("DELETE FROM announcements WHERE id=?", (aid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/wip", methods=["GET", "POST"])
def admin_wip():
    if not admin_ok():
        abort(403)
    conn = db()
    if request.method == "GET":
        projects = conn.execute("SELECT * FROM wip_projects ORDER BY sort, created").fetchall()
        out = []
        for pr in projects:
            d = dict(pr)
            d["updates"] = [dict(u) for u in conn.execute(
                "SELECT * FROM wip_updates WHERE project_id=? ORDER BY created DESC",
                (pr["id"],)).fetchall()]
            out.append(d)
        conn.close()
        return jsonify({"projects": out})
    data = request.get_json(force=True)
    wid = "w_" + uuid.uuid4().hex[:10]
    conn.execute("INSERT INTO wip_projects (id, project, status, photo, sort, created) "
                 "VALUES (?,?,?,?,?,?)",
                 (wid, (data.get("project") or "").strip()[:120],
                  (data.get("status") or "").strip()[:60], "", 99, now_iso()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": wid})


@app.route("/api/admin/wip-update", methods=["POST"])
def admin_wip_update():
    if not admin_ok():
        abort(403)
    data = request.get_json(force=True)
    conn = db()
    conn.execute("INSERT INTO wip_updates (id, project_id, created, text) VALUES (?,?,?,?)",
                 ("wu_" + uuid.uuid4().hex[:10], data.get("project_id"),
                  now_iso(), (data.get("text") or "").strip()[:1000]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/wip/<wid>", methods=["DELETE"])
def admin_wip_delete(wid):
    if not admin_ok():
        abort(403)
    conn = db()
    conn.execute("DELETE FROM wip_updates WHERE project_id=?", (wid,))
    conn.execute("DELETE FROM wip_projects WHERE id=?", (wid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/orders")
def admin_orders():
    if not admin_ok():
        abort(403)
    conn = db()
    rows = conn.execute("SELECT * FROM orders ORDER BY created DESC LIMIT 200").fetchall()
    lamps = conn.execute("SELECT * FROM lamp_orders ORDER BY created DESC LIMIT 200").fetchall()
    conn.close()
    return jsonify({"orders": [dict(r) for r in rows],
                    "lamp_orders": [dict(r) for r in lamps]})


@app.route("/api/admin/engraving-requests")
def admin_engraving_requests():
    if not admin_ok():
        abort(403)
    conn = db()
    rows = conn.execute("SELECT * FROM engraving_requests ORDER BY created DESC LIMIT 200").fetchall()
    conn.close()
    return jsonify({"requests": [dict(r) for r in rows]})


def compose_share_text(kind, item):
    if kind == "product":
        url = f"{SITE_URL}/product/{item['id']}"
        photo = abs_url(item.get("photo") or "/img/products/carlo-lamp.jpg")
        pre = "Preorder now open" if item.get("preorder") else "Now available"
        text = (f"{pre}: {item['name']} ({money(item['price_cents'])} CAD)\n\n"
                f"Designed and hand crafted in Montreal.\n\nOrder here: {url}")
    else:
        url = f"{SITE_URL}/announcement/{item['id']}"
        photo = abs_url("/img/products/carlo-lamp.jpg")
        text = (f"News from the workshop: {item['title']}\n\n{item['body'][:220]}\n\n"
                f"Read more: {url}")
    return {"text": text, "url": url, "photo": photo}


@app.route("/api/admin/share-draft")
def admin_share_draft():
    if not admin_ok():
        abort(403)
    kind = request.args.get("kind", "product")
    iid = request.args.get("id", "")
    conn = db()
    if kind == "product":
        item = conn.execute("SELECT * FROM products WHERE id=?", (iid,)).fetchone()
    else:
        item = conn.execute("SELECT * FROM announcements WHERE id=?", (iid,)).fetchone()
    conn.close()
    if not item:
        return jsonify({"error": "unknown item"}), 404
    return jsonify(compose_share_text(kind, dict(item)))


def try_facebook_publish(text, link):
    """One-tap publish to the Making Stuff Page via the Graph API.
    Requires FB_PAGE_TOKEN env var (a Page access token). Returns (ok, detail)."""
    if not FB_PAGE_TOKEN:
        return False, "FB_PAGE_TOKEN is not configured"
    try:
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/feed",
            data={"message": text, "link": link, "access_token": FB_PAGE_TOKEN},
            timeout=30)
        data = r.json()
        if "id" in data:
            return True, f"published as post {data['id']}"
        return False, data.get("error", {}).get("message", "unknown error")
    except Exception as e:  # noqa: BLE001
        return False, str(e)


@app.route("/api/admin/share-publish", methods=["POST"])
def admin_share_publish():
    if not admin_ok():
        abort(403)
    data = request.get_json(force=True)
    kind = data.get("kind", "product")
    iid = data.get("id", "")
    conn = db()
    if kind == "product":
        item = conn.execute("SELECT * FROM products WHERE id=?", (iid,)).fetchone()
    else:
        item = conn.execute("SELECT * FROM announcements WHERE id=?", (iid,)).fetchone()
    conn.close()
    if not item:
        return jsonify({"error": "unknown item"}), 404
    draft = compose_share_text(kind, dict(item))
    ok, detail = try_facebook_publish(draft["text"], draft["url"])
    return jsonify({"published": ok, "detail": detail, "draft": draft})


# ---------- private visit stats ----------
@app.route("/admin/visits")
def admin_visits():
    token = ADMIN_TOKEN
    if not token or request.args.get("token") != token:
        abort(403)
    conn = db()
    rows = conn.execute(
        "SELECT day, path, count FROM visits ORDER BY day DESC, path LIMIT 500"
    ).fetchall()
    conn.close()
    total = sum(r[2] for r in rows)
    tr = "".join(
        f"<tr><td>{h(r[0])}</td><td>{h(r[1])}</td><td>{r[2]}</td></tr>" for r in rows
    ) or '<tr><td colspan="3">No visits recorded yet.</td></tr>'
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>ADN Creations visits</title>"
        "<style>body{font-family:sans-serif;background:#FAF8F3;color:#181309;"
        "max-width:640px;margin:2em auto;padding:0 1em}"
        "table{border-collapse:collapse;width:100%;background:#fff}"
        "td,th{border:1px solid #E8E0D0;padding:.4em .6em;text-align:left}"
        "th{background:#F1EBDD}</style></head><body>"
        f"<h1>ADN Creations visits</h1><p>Total recorded: <b>{total}</b></p>"
        "<table><tr><th>Day (UTC)</th><th>Page</th><th>Visits</th></tr>"
        f"{tr}</table></body></html>"
    )


# ---------- privacy: auto-delete old lamp uploads ----------
def cleanup_loop():
    while True:
        time.sleep(3600)
        cutoff = time.time() - 24 * 3600
        try:
            for name in os.listdir(LAMP_UPLOAD_DIR):
                p = os.path.join(LAMP_UPLOAD_DIR, name)
                if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                    os.remove(p)
        except OSError:
            pass


threading.Thread(target=cleanup_loop, daemon=True).start()

seed()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
