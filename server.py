#!/usr/bin/env python3
"""
Ritratto — backend.

B2C:  upload -> watermarked preview -> $10/$25 one-time Stripe Checkout -> HD download
B2B:  funeral home signs up -> $69/mo Stripe subscription (30-day trial)
      -> staff dashboard -> unlimited portrait generation under their login

Env vars:
  GEMINI_API_KEY, GEMINI_MODEL, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
  STRIPE_PRICE_ID (created automatically if missing), SITE_URL,
  SECRET_KEY (flask sessions), DEMO_MODE=true (skip real payments)
"""
import os
import io
import uuid
import json
import base64
import sqlite3
import shutil
import threading
import time
from datetime import datetime, timedelta

import requests
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, request, jsonify, send_file, abort, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE)  # /var/data on Render (persistent disk)
UPLOADS = os.path.join(DATA_DIR, "uploads")
OUTPUTS = os.path.join(DATA_DIR, "outputs")
DB = os.path.join(DATA_DIR, "jobs.db")
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(OUTPUTS, exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-image")
STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000").rstrip("/")
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"

PRICES = {
    "digital": {"amount": 1000, "label": "Memorial portrait — HD digital download"},
    "painted": {"amount": 2500, "label": "Memorial portrait — painted style HD download"},
    "refined": {"amount": 499, "label": "Photo refinement — restored HD download"},
}
B2B_PRICE_CAD = 6900  # $69/month

SUITS = {
    "black": "a classic black suit, white dress shirt, and dark tie",
    "navy": "a navy blue suit, white dress shirt, and dark tie",
    "charcoal": "a charcoal grey suit, white dress shirt, and dark tie",
    "dress": "an elegant modest black formal dress",
    "blouse": "a dignified dark blazer over a blouse",
    "clerical": "a black clerical suit with a white clerical collar",
}

app = Flask(__name__, static_folder="static", static_url_path="")
_secret = os.environ.get("SECRET_KEY")
if not _secret and not DEMO_MODE:
    raise RuntimeError("SECRET_KEY env var is required in production")
app.secret_key = _secret or "dev-secret-change-me"


# ---------- db ----------
def db():
    conn = sqlite3.connect(DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS jobs "
        "(id TEXT PRIMARY KEY, created TEXT, product TEXT, paid INTEGER DEFAULT 0, "
        " user_id TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users "
        "(id TEXT PRIMARY KEY, created TEXT, business TEXT, email TEXT UNIQUE, "
        " pw_hash TEXT, stripe_customer TEXT, stripe_sub TEXT, sub_status TEXT DEFAULT 'none', "
        " newsletter INTEGER DEFAULT 0)"
    )
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN user_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN newsletter INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    return conn


def new_job(product, user_id=None):
    jid = uuid.uuid4().hex[:12]
    conn = db()
    conn.execute(
        "INSERT INTO jobs (id, created, product, paid, user_id) VALUES (?,?,?,?,?)",
        (jid, datetime.utcnow().isoformat(), product, 0, user_id),
    )
    conn.commit()
    conn.close()
    os.makedirs(os.path.join(OUTPUTS, jid), exist_ok=True)
    return jid


def mark_paid(jid):
    conn = db()
    conn.execute("UPDATE jobs SET paid=1 WHERE id=?", (jid,))
    conn.commit()
    conn.close()


def job_owner(jid):
    conn = db()
    row = conn.execute("SELECT user_id, paid FROM jobs WHERE id=?", (jid,)).fetchone()
    conn.close()
    return (row[0], bool(row[1])) if row else (None, False)


def get_user(uid):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    cols = [d[0] for d in conn.execute("SELECT * FROM users LIMIT 0").description]
    conn.close()
    return dict(zip(cols, row)) if row else None


def sub_active(user):
    return user and user.get("sub_status") in ("active", "trialing")


def current_user():
    uid = session.get("uid")
    return get_user(uid) if uid else None


# ---------- image generation (shared) ----------
def gemini_edit(image_paths, prompt):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    parts = [{"text": prompt}]
    for p in image_paths:
        with open(p, "rb") as f:
            raw = f.read()
        mime = "image/png" if p.lower().endswith(".png") else "image/jpeg"
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode()}})
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
    resp = requests.post(
        url,
        json={"contents": [{"parts": parts}],
              "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}},
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return Image.open(io.BytesIO(base64.b64decode(inline["data"]))).convert("RGB")
    raise RuntimeError("Model returned no image.")


def portrait_prompt(attire_desc):
    return (
        "You are creating a dignified memorial portrait for a funeral display. "
        "CRITICAL: keep this person's face exactly identical to the photo — same facial "
        "features, same expression, same apparent age, same skin tone, same identity. "
        "Do NOT beautify, de-age, slim, or alter the face in any way. "
        "Change ONLY the clothing: dress the person in " + attire_desc + ". "
        "Formal shoulders-up studio portrait, soft respectful lighting, "
        "plain dark neutral background. Must look like a real photograph, not an illustration."
    )


def painted_prompt(attire_desc):
    return (
        "You are creating a dignified memorial portrait for a funeral display, rendered as "
        "a classical oil painting with visible brushstrokes and a timeless feel. "
        "CRITICAL: keep this person's face exactly identical to the photo — same facial "
        "features, same expression, same apparent age, same skin tone, same identity. "
        "Do NOT beautify, de-age, slim, or alter the face in any way. "
        "Change ONLY the clothing: dress the person in " + attire_desc + ". "
        "Formal shoulders-up composition, soft respectful lighting, dark neutral background."
    )


def refine_prompt():
    return (
        "You are restoring an old or damaged photograph for a memorial display. "
        "CRITICAL: keep this person's face exactly identical — same facial features, "
        "same expression, same apparent age, same skin tone, same identity, same clothing, "
        "same pose and framing. Do NOT beautify, de-age, slim, or alter the person in any way. "
        "Only repair the photograph itself: remove scratches, dust, and creases; fix fading "
        "and discoloration; correct exposure and white balance; gently sharpen blurry areas; "
        "reduce noise and grain. The result must look like a clean, high-quality scan of the "
        "same photograph — a real photograph, not an illustration."
    )


def add_watermark(img):
    w, h = img.size
    scale = 900 / max(w, h)
    prev = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS).convert("RGB")
    overlay = Image.new("RGBA", prev.size, (0, 0, 0, 0))
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
    except OSError:
        font = ImageFont.load_default()
    for x in range(-200, prev.size[0] + 200, 320):
        t = Image.new("RGBA", (320, 80), (0, 0, 0, 0))
        ImageDraw.Draw(t).text((10, 10), "PREVIEW", font=font, fill=(255, 255, 255, 90))
        overlay = Image.alpha_composite(overlay, t.rotate(30, expand=True))
    return Image.alpha_composite(prev.convert("RGBA"), overlay).convert("RGB")


def run_generation(jobdir, photo_file, attire_id, style, suit_file=None):
    """Shared generation pipeline. Returns PIL image. Raises on failure."""
    src = os.path.join(jobdir, "source.jpg")
    Image.open(photo_file.stream).convert("RGB").save(src, "JPEG", quality=92)
    if style == "refine":
        # photo restoration only: no attire change
        return gemini_edit([src], refine_prompt())
    images = [src]
    if attire_id == "custom":
        if not suit_file:
            raise ValueError("custom attire needs a suit reference photo")
        ref_path = os.path.join(jobdir, "suit_ref.jpg")
        Image.open(suit_file.stream).convert("RGB").save(ref_path, "JPEG", quality=92)
        images.append(ref_path)
        attire_desc = "the suit/outfit shown in the second reference image"
    else:
        attire_desc = SUITS.get(attire_id, SUITS["black"])
    prompt = painted_prompt(attire_desc) if style == "painting" else portrait_prompt(attire_desc)
    return gemini_edit(images, prompt)


# ---------- B2C routes ----------
@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/generate", methods=["POST"])
def generate():
    photo = request.files.get("photo")
    if not photo:
        return jsonify({"error": "no photo uploaded"}), 400
    attire_id = request.form.get("attire", "black")
    style = request.form.get("style", "photo")
    product = "painted" if style == "painting" else "refined" if style == "refine" else "digital"
    jid = new_job(product)
    jobdir = os.path.join(OUTPUTS, jid)
    try:
        result = run_generation(jobdir, photo, attire_id, style, request.files.get("suit_photo"))
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"generation failed: {e}"}), 502
    result.save(os.path.join(jobdir, "result.png"))
    add_watermark(result).save(os.path.join(jobdir, "preview.jpg"), "JPEG", quality=80)
    return jsonify({"job_id": jid, "preview_url": f"/preview/{jid}", "product": product})


@app.route("/preview/<jid>")
def preview(jid):
    p = os.path.join(OUTPUTS, jid, "preview.jpg")
    if not os.path.exists(p):
        # staff jobs have no watermarked preview; serve full result as preview
        p = os.path.join(OUTPUTS, jid, "result.png")
    if not os.path.exists(p):
        abort(404)
    return send_file(p)


@app.route("/download/<jid>")
def download(jid):
    owner, paid = job_owner(jid)
    user = current_user()
    allowed = paid or (owner and user and owner == user["id"] and sub_active(user))
    if not allowed:
        abort(402, "payment required")
    p = os.path.join(OUTPUTS, jid, "result.png")
    if not os.path.exists(p):
        abort(404)
    return send_file(p, mimetype="image/png", as_attachment=True,
                     download_name="ritratto-portrait.png")


@app.route("/api/status/<jid>")
def status(jid):
    owner, paid = job_owner(jid)
    user = current_user()
    ok = paid or (owner and user and owner == user["id"] and sub_active(user))
    return jsonify({"paid": ok})


@app.route("/api/checkout", methods=["POST"])
def checkout():
    data = request.get_json(force=True)
    jid = data.get("job_id")
    product = data.get("product", "digital")
    if product not in PRICES:
        return jsonify({"error": "unknown product"}), 400
    if DEMO_MODE or not STRIPE_SECRET:
        mark_paid(jid)
        return jsonify({"url": f"{SITE_URL}/?paid=1&job={jid}", "demo": True})
    import stripe
    stripe.api_key = STRIPE_SECRET
    sess = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price_data": {
            "currency": "cad", "unit_amount": PRICES[product]["amount"],
            "product_data": {"name": PRICES[product]["label"]}}, "quantity": 1}],
        mode="payment",
        success_url=f"{SITE_URL}/?paid=1&job={jid}",
        cancel_url=f"{SITE_URL}/?cancelled=1&job={jid}",
        metadata={"job_id": jid, "kind": "b2c"},
    )
    return jsonify({"url": sess.url})


# ---------- B2B: accounts + subscriptions ----------
def get_or_create_price():
    global STRIPE_PRICE_ID
    if STRIPE_PRICE_ID:
        return STRIPE_PRICE_ID
    import stripe
    stripe.api_key = STRIPE_SECRET
    price = stripe.Price.create(
        unit_amount=B2B_PRICE_CAD, currency="cad",
        recurring={"interval": "month"},
        product_data={"name": "Funeral Home Plan — unlimited memorial portraits"},
    )
    STRIPE_PRICE_ID = price.id
    print(f"*** SAVE THIS: STRIPE_PRICE_ID={price.id} ***")
    return price.id


@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    business = (data.get("business") or "").strip()
    newsletter = 1 if data.get("newsletter") else 0
    if not email or len(pw) < 8 or not business:
        return jsonify({"error": "business name, email, and a password (8+ chars) are required"}), 400
    uid = uuid.uuid4().hex[:12]
    conn = db()
    try:
        conn.execute(
            "INSERT INTO users (id, created, business, email, pw_hash, newsletter) VALUES (?,?,?,?,?,?)",
            (uid, datetime.utcnow().isoformat(), business, email, generate_password_hash(pw), newsletter),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "that email is already registered"}), 400
    conn.close()

    if DEMO_MODE or not STRIPE_SECRET:
        conn = db()  # testing shortcut: active sub, no Stripe
        conn.execute("UPDATE users SET sub_status='active' WHERE id=?", (uid,))
        conn.commit()
        conn.close()
        session["uid"] = uid
        return jsonify({"url": "/dashboard.html", "demo": True})

    import stripe
    stripe.api_key = STRIPE_SECRET
    customer = stripe.Customer.create(email=email, name=business,
                                      metadata={"user_id": uid})
    sess = stripe.checkout.Session.create(
        customer=customer.id,
        payment_method_types=["card"],
        line_items=[{"price": get_or_create_price(), "quantity": 1}],
        mode="subscription",
        subscription_data={"trial_period_days": 30,
                           "metadata": {"user_id": uid}},
        success_url=f"{SITE_URL}/dashboard.html?welcome=1",
        cancel_url=f"{SITE_URL}/funeral-homes.html?cancelled=1",
        metadata={"user_id": uid, "kind": "b2b"},
    )
    conn = db()
    conn.execute("UPDATE users SET stripe_customer=? WHERE id=?", (customer.id, uid))
    conn.commit()
    conn.close()
    return jsonify({"url": sess.url})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    conn = db()
    row = conn.execute("SELECT id, pw_hash FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    if not row or not check_password_hash(row[1], data.get("password") or ""):
        return jsonify({"error": "invalid email or password"}), 401
    session["uid"] = row[0]
    return jsonify({"ok": True})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("uid", None)
    return jsonify({"ok": True})


@app.route("/api/me")
def me():
    user = current_user()
    if not user:
        return jsonify({"user": None})
    return jsonify({"user": {
        "business": user["business"], "email": user["email"],
        "sub_status": user["sub_status"], "active": sub_active(user),
    }})


@app.route("/api/portal", methods=["POST"])
def portal():
    user = current_user()
    if not user:
        return jsonify({"error": "not logged in"}), 401
    if DEMO_MODE or not STRIPE_SECRET or not user.get("stripe_customer"):
        return jsonify({"url": "/dashboard.html", "demo": True})
    import stripe
    stripe.api_key = STRIPE_SECRET
    ps = stripe.billing_portal.Session.create(
        customer=user["stripe_customer"], return_url=f"{SITE_URL}/dashboard.html")
    return jsonify({"url": ps.url})


@app.route("/api/staff/generate", methods=["POST"])
def staff_generate():
    user = current_user()
    if not user:
        return jsonify({"error": "not logged in"}), 401
    if not sub_active(user):
        return jsonify({"error": "subscription not active"}), 403
    photo = request.files.get("photo")
    if not photo:
        return jsonify({"error": "no photo uploaded"}), 400
    attire_id = request.form.get("attire", "black")
    style = request.form.get("style", "photo")
    jid = new_job("painted" if style == "painting" else "refined" if style == "refine" else "digital", user_id=user["id"])
    jobdir = os.path.join(OUTPUTS, jid)
    try:
        result = run_generation(jobdir, photo, attire_id, style, request.files.get("suit_photo"))
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"generation failed: {e}"}), 502
    result.save(os.path.join(jobdir, "result.png"))
    return jsonify({"job_id": jid, "image_url": f"/preview/{jid}"})


@app.route("/api/staff/jobs")
def staff_jobs():
    user = current_user()
    if not user:
        return jsonify({"error": "not logged in"}), 401
    conn = db()
    rows = conn.execute(
        "SELECT id, created, product FROM jobs WHERE user_id=? ORDER BY created DESC LIMIT 50",
        (user["id"],)).fetchall()
    conn.close()
    return jsonify([{"id": r[0], "created": r[1], "product": r[2],
                     "image_url": f"/preview/{r[0]}",
                     "download_url": f"/download/{r[0]}"} for r in rows])


@app.route("/webhook/stripe", methods=["POST"])
def webhook():
    import stripe
    payload = request.data
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        return "bad signature", 400
    stripe.api_key = STRIPE_SECRET
    etype = event["type"]
    if etype == "checkout.session.completed":
        obj = event["data"]["object"]
        meta = obj.get("metadata", {})
        if meta.get("kind") == "b2c" and meta.get("job_id"):
            mark_paid(meta["job_id"])
        elif meta.get("kind") == "b2b" and meta.get("user_id"):
            sub = stripe.Subscription.retrieve(obj["subscription"])
            conn = db()
            conn.execute(
                "UPDATE users SET stripe_sub=?, sub_status=? WHERE id=?",
                (sub.id, sub.status, meta["user_id"]))
            conn.commit()
            conn.close()
    elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub = event["data"]["object"]
        uid = (sub.get("metadata") or {}).get("user_id")
        if uid:
            conn = db()
            conn.execute("UPDATE users SET sub_status=? WHERE id=?", (sub["status"], uid))
            conn.commit()
            conn.close()
    return "ok", 200


# ---------- privacy: auto-delete old jobs ----------
def cleanup_loop():
    while True:
        time.sleep(3600)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        try:
            conn = db()
            rows = conn.execute("SELECT id, created FROM jobs").fetchall()
            for jid, created in rows:
                if datetime.fromisoformat(created) < cutoff:
                    shutil.rmtree(os.path.join(OUTPUTS, jid), ignore_errors=True)
                    conn.execute("DELETE FROM jobs WHERE id=?", (jid,))
            conn.commit()
            conn.close()
        except Exception:  # noqa: BLE001
            pass


threading.Thread(target=cleanup_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
