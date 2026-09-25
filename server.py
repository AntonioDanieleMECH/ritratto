#!/usr/bin/env python3
"""
Ritratto — backend.

Flow: upload -> small watermarked preview -> regenerate up to 15x with notes
      -> $9.99 / $4.99 one-time Stripe Checkout -> HD download of the chosen version.

Env vars:
  GEMINI_API_KEY, GEMINI_MODEL, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
  SITE_URL, SECRET_KEY (flask sessions), DEMO_MODE=true (skip real payments)
"""
import os
import io
import re
import json
import uuid
import base64
import sqlite3
import shutil
import threading
import time
from datetime import datetime, timedelta

import requests
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, request, jsonify, send_file, abort

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE, "static")
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
SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000").rstrip("/")
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"

PRICES = {
    "digital": {"amount": 999, "label": "Memorial portrait — HD digital download"},
    "refined": {"amount": 499, "label": "Photo refinement — restored HD download"},
}
MAX_ATTEMPTS = 15  # first generation + up to 14 regenerations
SUPPORT_EMAIL = "antonio.learningisfun@gmail.com"

# 4-faced custom memorial lamps (physical product, shipped)
# Customers design the 4 sides: pick saint illustrations or upload their own photos.
GALLERY = {
    "solanus-casey": {"name": "Blessed Solanus Casey", "image": "/lamps/gallery/solanus-casey.jpg"},
    "padrepio-face": {"name": "Padre Pio", "image": "/lamps/gallery/padrepio-face.jpg"},
    "padrepio-mass": {"name": "Padre Pio — Mass", "image": "/lamps/gallery/padrepio-mass.jpg"},
    "ourlady-child": {"name": "Our Lady with Child", "image": "/lamps/gallery/ourlady-child.jpg"},
    "carlo-standing": {"name": "Carlo Acutis — Standing", "image": "/lamps/carlo-standing.jpg"},
    "carlo-monstrance": {"name": "Carlo Acutis — Monstrance", "image": "/lamps/carlo-monstrance.jpg"},
    "our-lady": {"name": "Our Lady of the Rosary", "image": "/lamps/our-lady.jpg"},
    "basilica-padrepio": {"name": "Basilica & Padre Pio", "image": "/lamps/basilica-padrepio.jpg"},
}
LAMP_SINGLE = 2500   # $25 each
LAMP_SET4 = 8000     # $80 for 4 copies of the same custom design
LAMP_SHIPPING = 1000  # $10 flat-rate Canada & US shipping
LAMP_UPLOAD_DIR = os.path.join(STATIC_DIR, "lamp_uploads")

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
        " attire TEXT, style TEXT, attempts INTEGER DEFAULT 1)"
    )
    for col, ddl in (("attire", "ALTER TABLE jobs ADD COLUMN attire TEXT"),
                     ("style", "ALTER TABLE jobs ADD COLUMN style TEXT"),
                     ("attempts", "ALTER TABLE jobs ADD COLUMN attempts INTEGER DEFAULT 1")):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lamp_orders "
        "(id TEXT PRIMARY KEY, created TEXT, design TEXT, pack TEXT, "
        " amount INTEGER, paid INTEGER DEFAULT 0, stripe_session TEXT)"
    )
    try:
        conn.execute("ALTER TABLE lamp_orders ADD COLUMN sides TEXT")
    except sqlite3.OperationalError:
        pass
    return conn


def new_job(product, attire, style):
    jid = uuid.uuid4().hex[:12]
    conn = db()
    conn.execute(
        "INSERT INTO jobs (id, created, product, paid, attire, style, attempts)"
        " VALUES (?,?,?,?,?,?,1)",
        (jid, datetime.utcnow().isoformat(), product, 0, attire, style),
    )
    conn.commit()
    conn.close()
    os.makedirs(os.path.join(OUTPUTS, jid), exist_ok=True)
    return jid


def get_job(jid):
    conn = db()
    row = conn.execute(
        "SELECT product, paid, attire, style, attempts FROM jobs WHERE id=?", (jid,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"product": row[0], "paid": bool(row[1]), "attire": row[2],
            "style": row[3], "attempts": row[4] or 1}


def bump_attempts(jid, attempts):
    conn = db()
    conn.execute("UPDATE jobs SET attempts=? WHERE id=?", (attempts, jid))
    conn.commit()
    conn.close()


def mark_paid(jid):
    conn = db()
    conn.execute("UPDATE jobs SET paid=1 WHERE id=?", (jid,))
    conn.commit()
    conn.close()


def new_lamp_order(sides, pack, amount):
    oid = "lamp_" + uuid.uuid4().hex[:10]
    conn = db()
    conn.execute(
        "INSERT INTO lamp_orders (id, created, design, pack, amount, paid, sides)"
        " VALUES (?,?,?,?,?,0,?)",
        (oid, datetime.utcnow().isoformat(), "custom", pack, amount,
         json.dumps(sides)),
    )
    conn.commit()
    conn.close()
    return oid


def mark_lamp_paid(oid):
    conn = db()
    conn.execute("UPDATE lamp_orders SET paid=1 WHERE id=?", (oid,))
    conn.commit()
    conn.close()


# ---------- image generation ----------
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


def portrait_prompt(attire_desc, note=None):
    p = (
        "You are creating a dignified memorial portrait for a funeral display. "
        "CRITICAL: keep this person's face exactly identical to the photo — same facial "
        "features, same expression, same apparent age, same skin tone, same identity. "
        "Do NOT beautify, de-age, slim, or alter the face in any way. "
        "Change ONLY the clothing: dress the person in " + attire_desc + ". "
        "Formal shoulders-up studio portrait, soft respectful lighting, "
        "plain dark neutral background. Must look like a real photograph, not an illustration."
    )
    if note:
        p += f" Additional revision request from the customer — apply it while keeping everything else the same: {note}"
    return p


def refine_prompt(note=None):
    p = (
        "You are restoring an old or damaged photograph for a memorial display. "
        "CRITICAL: keep this person's face exactly identical — same facial features, "
        "same expression, same apparent age, same skin tone, same identity, same clothing, "
        "same pose and framing. Do NOT beautify, de-age, slim, or alter the person in any way. "
        "Only repair the photograph itself: remove scratches, dust, and creases; fix fading "
        "and discoloration; correct exposure and white balance; gently sharpen blurry areas; "
        "reduce noise and grain. The result must look like a clean, high-quality scan of the "
        "same photograph — a real photograph, not an illustration."
    )
    if note:
        p += f" Additional revision request from the customer — apply it while keeping everything else the same: {note}"
    return p


def add_watermark(img):
    """Small watermarked preview (max 640px) so screenshots stay low-value."""
    w, h = img.size
    scale = 640 / max(w, h)
    prev = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS).convert("RGB")
    overlay = Image.new("RGBA", prev.size, (0, 0, 0, 0))
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
    except OSError:
        font = ImageFont.load_default()
    for x in range(-160, prev.size[0] + 160, 240):
        t = Image.new("RGBA", (240, 60), (0, 0, 0, 0))
        ImageDraw.Draw(t).text((10, 8), "PREVIEW", font=font, fill=(255, 255, 255, 90))
        overlay = Image.alpha_composite(overlay, t.rotate(30, expand=True))
    return Image.alpha_composite(prev.convert("RGBA"), overlay).convert("RGB")


def save_version(jobdir, img, version):
    img.save(os.path.join(jobdir, f"v{version}.png"))
    add_watermark(img).save(os.path.join(jobdir, f"v{version}_preview.jpg"),
                            "JPEG", quality=80)


def run_generation(jobdir, photo_file, attire_id, style, suit_file=None, note=None):
    """Shared generation pipeline. Returns PIL image. Raises on failure.
    Pass photo_file=None to reuse the already-saved source photo (regeneration)."""
    src = os.path.join(jobdir, "source.jpg")
    if photo_file is not None:
        Image.open(photo_file.stream).convert("RGB").save(src, "JPEG", quality=92)
    if style == "refine":
        return gemini_edit([src], refine_prompt(note))
    images = [src]
    if attire_id == "custom":
        ref_path = os.path.join(jobdir, "suit_ref.jpg")
        if suit_file is not None:
            Image.open(suit_file.stream).convert("RGB").save(ref_path, "JPEG", quality=92)
        if not os.path.exists(ref_path):
            raise ValueError("custom attire needs a suit reference photo")
        images.append(ref_path)
        attire_desc = "the suit/outfit shown in the second reference image"
    else:
        attire_desc = SUITS.get(attire_id, SUITS["black"])
    return gemini_edit(images, portrait_prompt(attire_desc, note))


def valid_version(v):
    return v.isdigit() and int(v) >= 1


# ---------- routes ----------
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
    if style not in ("photo", "refine"):
        return jsonify({"error": "unknown style"}), 400
    product = "refined" if style == "refine" else "digital"
    jid = new_job(product, attire_id, style)
    jobdir = os.path.join(OUTPUTS, jid)
    try:
        result = run_generation(jobdir, photo, attire_id, style, request.files.get("suit_photo"))
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"generation failed: {e}"}), 502
    save_version(jobdir, result, 1)
    return jsonify({"job_id": jid, "version": 1,
                    "preview_url": f"/preview/{jid}?v=1",
                    "attempts_left": MAX_ATTEMPTS - 1, "product": product})


@app.route("/api/regenerate", methods=["POST"])
def regenerate():
    data = request.get_json(force=True)
    jid = data.get("job_id") or ""
    note = (data.get("note") or "").strip()[:500]
    job = get_job(jid)
    if not job:
        return jsonify({"error": "unknown job"}), 404
    if job["attempts"] >= MAX_ATTEMPTS:
        return jsonify({"error": "no attempts left"}), 400
    jobdir = os.path.join(OUTPUTS, jid)
    try:
        result = run_generation(jobdir, None, job["attire"] or "black",
                                job["style"] or "photo", None, note or None)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"generation failed: {e}"}), 502
    version = job["attempts"] + 1
    save_version(jobdir, result, version)
    bump_attempts(jid, version)
    return jsonify({"job_id": jid, "version": version,
                    "preview_url": f"/preview/{jid}?v={version}",
                    "attempts_left": MAX_ATTEMPTS - version})


@app.route("/preview/<jid>")
def preview(jid):
    v = request.args.get("v", "1")
    if not valid_version(v):
        abort(404)
    p = os.path.join(OUTPUTS, jid, f"v{v}_preview.jpg")
    if not os.path.exists(p):
        abort(404)
    return send_file(p)


@app.route("/download/<jid>")
def download(jid):
    v = request.args.get("v", "1")
    if not valid_version(v):
        abort(404)
    job = get_job(jid)
    if not job or not job["paid"]:
        abort(402, "payment required")
    p = os.path.join(OUTPUTS, jid, f"v{v}.png")
    if not os.path.exists(p):
        abort(404)
    return send_file(p, mimetype="image/png", as_attachment=True,
                     download_name="ritratto-portrait.png")


@app.route("/api/status/<jid>")
def status(jid):
    job = get_job(jid)
    if not job:
        return jsonify({"paid": False, "versions": 0, "attempts_left": 0})
    return jsonify({"paid": job["paid"], "versions": job["attempts"],
                    "attempts_left": MAX_ATTEMPTS - job["attempts"]})


@app.route("/api/checkout", methods=["POST"])
def checkout():
    data = request.get_json(force=True)
    jid = data.get("job_id") or ""
    product = data.get("product", "digital")
    version = str(data.get("version", 1))
    if product not in PRICES:
        return jsonify({"error": "unknown product"}), 400
    if not valid_version(version):
        return jsonify({"error": "unknown version"}), 400
    job = get_job(jid)
    if not job or int(version) > job["attempts"]:
        return jsonify({"error": "unknown job"}), 404
    if not STRIPE_SECRET:
        if DEMO_MODE:
            mark_paid(jid)
            return jsonify({"url": f"{SITE_URL}/?paid=1&job={jid}&v={version}", "demo": True})
        # Fail closed: never hand out portraits without a working payment setup.
        return jsonify({"error": "payments are not configured yet — please try again later"}), 503
    import stripe
    stripe.api_key = STRIPE_SECRET
    sess = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price_data": {
            "currency": "cad", "unit_amount": PRICES[product]["amount"],
            "product_data": {"name": PRICES[product]["label"]}}, "quantity": 1}],
        mode="payment",
        success_url=f"{SITE_URL}/?paid=1&job={jid}&v={version}",
        cancel_url=f"{SITE_URL}/?cancelled=1&job={jid}",
        metadata={"job_id": jid, "kind": "b2c", "version": version},
    )
    return jsonify({"url": sess.url})


@app.route("/api/lamp-upload", methods=["POST"])
def lamp_upload():
    """Customer uploads their own photo for one lamp side. Kept to make the lamp."""
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400
    os.makedirs(LAMP_UPLOAD_DIR, exist_ok=True)
    name = "side_" + uuid.uuid4().hex[:10] + ".jpg"
    path = os.path.join(LAMP_UPLOAD_DIR, name)
    try:
        img = Image.open(f.stream).convert("RGB")
        img.thumbnail((1200, 1200), Image.LANCZOS)
        img.save(path, "JPEG", quality=88)
    except Exception:
        return jsonify({"error": "could not read that image"}), 400
    return jsonify({"file": name, "url": "/lamp_uploads/" + name})


def validate_sides(sides):
    """Returns (clean_sides, summary) or raises ValueError."""
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
    label = (f"Custom 4-faced lamp ({'4 copies' if pack == 'set4' else 'single'})"
             f" — {side_summary[:120]}")
    if not STRIPE_SECRET:
        if DEMO_MODE:
            new_lamp_order(sides, pack, amount)
            return jsonify({"url": f"{SITE_URL}/?lamp_paid=1", "demo": True})
        # Fail closed: never take orders without a working payment setup.
        return jsonify({"error": "payments are not configured yet — please try again later"}), 503
    import stripe
    stripe.api_key = STRIPE_SECRET
    oid = new_lamp_order(sides, pack, amount)
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
            "display_name": "Flat-rate shipping"}}],
        success_url=f"{SITE_URL}/?lamp_paid=1",
        cancel_url=f"{SITE_URL}/?cancelled=1",
        metadata={"order_id": oid, "kind": "lamp",
                  "sides": side_summary[:400]},
    )
    conn = db()
    conn.execute("UPDATE lamp_orders SET stripe_session=? WHERE id=?", (sess.id, oid))
    conn.commit()
    conn.close()
    return jsonify({"url": sess.url})


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
    if event["type"] == "checkout.session.completed":
        obj = event["data"]["object"]
        meta = obj.get("metadata", {})
        if meta.get("kind") == "b2c" and meta.get("job_id"):
            mark_paid(meta["job_id"])
        elif meta.get("kind") == "lamp" and meta.get("order_id"):
            mark_lamp_paid(meta["order_id"])
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
