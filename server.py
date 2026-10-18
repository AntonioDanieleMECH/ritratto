#!/usr/bin/env python3
"""
ADN Creations: engineering design company site + store.

Bilingual (FR default, EN toggle) to comply with Quebec's Charter of the
French Language: every public page and string is available in French, at
least as complete as the English version. Static pages carry French copy
inline with data-i18n keys; static/i18n.js swaps in English client-side.
Server-rendered pages read ?lang= / the adn_lang cookie.

Pages (static in /static): index, work, shop, engraving, portraits,
progress, about, contact, thank-you, custom-lamp (4-sided lamp designer).
Server-rendered: /product/<id>, /announcement/<id>, /admin/ (token-gated).

Store: products live in SQLite (admin-manageable), Stripe Checkout in CAD.
Departments are tag-based: religious / electronic / gag.
Preorders: flagged per product with an expected ship date, recorded on orders.
Product photo galleries: product_photos table, ordered, scale shot last.
Custom memorial lamps: $39.99 first of a design, $29.99 each additional copy,
4-pack bundle $99.99 (designer flow).

Env vars:
  STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, SITE_URL, SECRET_KEY,
  ADMIN_TOKEN (protects /admin/ and /api/admin/*),
  DEMO_MODE=true (skip real payments),
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM (optional: email
    notifications for engraving/portrait requests; stored in DB regardless),
  FB_PAGE_TOKEN (optional: enables one-tap publish to the Making Stuff
    Facebook Page via the Graph API; without it the admin composes a
    ready-to-copy draft instead).
"""
import os
import re
import json
import hmac
import hashlib
import subprocess
import uuid
import sqlite3
import shutil
import threading
import time
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from html import escape as h

import requests
from PIL import Image, ImageOps
from flask import Flask, request, jsonify, send_file, abort, redirect, send_from_directory, session

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE, "static")
DATA_DIR = os.environ.get("DATA_DIR", BASE)  # /var/data on Render (persistent disk)
UPLOADS = os.path.join(DATA_DIR, "uploads")
LAMP_UPLOAD_DIR = os.path.join(STATIC_DIR, "lamp_uploads")
DESIGN_UPLOAD_DIR = os.path.join(STATIC_DIR, "design_uploads")
PRODUCT_IMG_DIR = os.path.join(STATIC_DIR, "img", "products")
DB = os.path.join(DATA_DIR, "jobs.db")
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(LAMP_UPLOAD_DIR, exist_ok=True)
os.makedirs(DESIGN_UPLOAD_DIR, exist_ok=True)
os.makedirs(PRODUCT_IMG_DIR, exist_ok=True)
VIDEO_DIR = os.path.join(DATA_DIR, "uploads", "videos")
os.makedirs(VIDEO_DIR, exist_ok=True)
VIDEO_MAX_BYTES = 50 * 1024 * 1024  # 50 MB per video

STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000").rstrip("/")
# Canonical public domain (2026-10-18: adncreations.ca is the brand domain;
# ritratto.ca and ritratto.onrender.com 301 here). Used for canonical tags and
# share-preview URLs regardless of what SITE_URL is still set to.
CANONICAL_URL = "https://adncreations.ca"
OLD_HOSTS_URLS = ("https://ritratto.onrender.com", "http://ritratto.onrender.com",
                  "https://ritratto.ca", "http://ritratto.ca",
                  "https://www.ritratto.ca", "http://www.ritratto.ca")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"
ADMIN_USER = os.environ.get("ADMIN_USER", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SUPPORT_EMAIL = "antonio.learningisfun@gmail.com"
FB_PAGE_ID = "1274653932393890"
FB_PAGE_URL = "https://www.facebook.com/61592937237761"
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")

DEPTS = ["religious", "electronic", "gag"]
DEPT_LABELS = {"religious": "Religious", "electronic": "Electronic", "gag": "Gag"}
DEPT_LABELS_FR = {"religious": "Religieux", "electronic": "Électronique", "gag": "Humour"}

OFFICE_EN = "Downtown office: 204 rue du Saint-Sacrement, Espace 300, H2Y 1W8 Montréal QC"
OFFICE_FR = "Bureau du centre-ville : 204, rue du Saint-Sacrement, bureau 300, H2Y 1W8 Montréal (QC)"


def get_lang():
    """Resolve the display language: ?lang= param, then adn_lang cookie, else French."""
    q = (request.args.get("lang") or "").strip().lower()
    if q in ("fr", "en"):
        return q
    c = (request.cookies.get("adn_lang") or "").strip().lower()
    if c in ("fr", "en"):
        return c
    return "fr"


# Bilingual strings for server-rendered chrome and flows.
# French is the default and must stay at least as complete as the English.
STR = {
    "fr": {
        "nav_work": "Réalisations", "nav_shop": "Boutique", "nav_engraving": "Gravure",
        "nav_portraits": "Portraits", "nav_progress": "En cours", "nav_about": "À propos",
        "nav_contact": "Contact", "nav_suggest": "Idées", "nav_reviews": "Avis", "nav_cta": "Magasiner", "menu": "Menu",
        "follow_ms": "Suivez nos créations sur Making Stuff",
        "footer_tag": "Entreprise de design en ingénierie. Fabrication additive faite à la main à Montréal, avec des matériaux d'origine végétale.",
        "footer_explore": "Explorer", "footer_contact": "Contact",
        "footer_rights": "Tous droits réservés.",
        "footer_made": "Conçu et fabriqué à Montréal.",
        "qty": "Quantité", "buy_now": "Acheter", "preorder_now": "Précommander",
        "sold_out": "Épuisé.", "coming_soon": "Bientôt disponible. Pas encore en vente.",
        "secure_checkout": "Paiement sécurisé avec Stripe. Frais d'expédition fixes pour le Canada et les États-Unis, calculés à la caisse.",
        "engraving_label": "Texte à graver (facultatif)",
        "engraving_ph": "p. ex. Aku, depuis 2026",
        "design_title": "Choisissez votre motif",
        "design_gallery": "Choisir parmi nos 12 motifs",
        "design_upload": "Téléverser mon propre dessin",
        "saint_title": "Choisissez votre saint",
        "preorder_note": "Ceci est une précommande. Expédition prévue : {date}. Vous serez facturé aujourd'hui.",
        "design_yours": "Créez le vôtre",
        "photo_soon": "Photo à venir",
        "scale_caption": "Présentée en main pour montrer l'échelle.",
        "tier_note": "Première lampe : {first}. Chaque lampe supplémentaire du même modèle : {extra}.",
        "reviews_title": "Avis",
        "reviews_empty": "Aucun avis pour le moment.",
        "review_write": "Écrire un avis",
        "review_name": "Votre nom", "review_rating": "Note", "review_text": "Votre avis",
        "review_submit": "Publier mon avis",
        "review_thanks": "Merci! Votre avis sera publié après vérification.",
        "review_err": "Veuillez indiquer votre nom, une note et votre avis.",
        "reviews_page_sub": "Ce que nos clients disent de nos pièces.",
        "reviews_all": "Tous les avis",
        "reviews_see_all": "Voir tous les avis",
        "coupon_label": "Code promo (facultatif)", "coupon_ph": "p. ex. KRISTIE15",
        "coupon_ok": "Code appliqué : -{pct} %", "coupon_bad": "Code invalide.",
        "preparing": "Préparation du paiement...",
        "checkout_failed": "Le paiement a échoué. Veuillez réessayer.",
        "checkout_failed_try": "Le paiement n'a pas pu démarrer. Veuillez réessayer.",
        "order_confirmed": "Commande confirmée",
        "err_unknown_product": "Produit inconnu.",
        "err_stock": "Stock insuffisant.",
        "err_payment": "Les paiements ne sont pas encore configurés, veuillez réessayer plus tard.",
        "err_sides": "Choisissez les 4 faces.",
        "err_request": "Veuillez indiquer votre nom, un courriel valide et votre idée.",
        "login_title": "Connexion vendeur", "login_h": "Connexion vendeur",
        "login_user": "Nom d'utilisateur", "login_pass": "Mot de passe",
        "login_submit": "Se connecter", "login_back": "Retour au site",
        "login_bad": "Nom d'utilisateur ou mot de passe incorrect.",
        "login_disabled": "La connexion par mot de passe n'est pas configurée. Utilisez votre lien d'administration.",
        "logout": "Se déconnecter",
        "idea_ok": "Idée reçue. Merci, nous vous répondrons bientôt.",
        "idea_fail": "L'envoi a échoué. Veuillez réessayer.",
        "only_left": "Plus que {n} en stock",
        "preorder_badge": "Précommande",
        "announce_back": "Annonces",
        "lamp_single_label": "Lampe commémorative personnalisée (une seule)",
        "lamp_pack4_label": "Lampe commémorative personnalisée (paquet de 4)",
        "in_works_badge": "En préparation",
        "follow_build": "Suivre le chantier",
        "notify_me_label": "Prévenez-moi quand ce sera prêt",
        "notify_me_ph": "votre@courriel.com",
        "notify_me_btn": "Me prévenir",
        "notify_ok": "C'est noté, nous vous écrirons dès que ce sera prêt.",
        "email_invalid": "Veuillez entrer un courriel valide.",
        "story_title": "L'histoire de la pièce",
    },
    "en": {
        "nav_work": "Work", "nav_shop": "Shop", "nav_engraving": "Engraving",
        "nav_portraits": "Portraits", "nav_progress": "Progress", "nav_about": "About",
        "nav_contact": "Contact", "nav_suggest": "Ideas", "nav_reviews": "Reviews", "nav_cta": "Shop now", "menu": "Menu",
        "follow_ms": "Follow our builds on Making Stuff",
        "footer_tag": "Engineering design company. Hand crafted additive manufacturing in Montreal, from plant-based materials.",
        "footer_explore": "Explore", "footer_contact": "Contact",
        "footer_rights": "All rights reserved.",
        "footer_made": "Designed and built in Montreal.",
        "qty": "Quantity", "buy_now": "Buy now", "preorder_now": "Preorder now",
        "sold_out": "Sold out.", "coming_soon": "Coming soon. Not available for order yet.",
        "secure_checkout": "Secure checkout with Stripe. Flat-rate shipping for Canada and the US calculated at checkout.",
        "engraving_label": "Custom engraving text (optional)",
        "engraving_ph": "e.g. Aku, Est. 2026",
        "design_title": "Choose your design",
        "design_gallery": "Pick from our 12 designs",
        "design_upload": "Upload my own artwork",
        "saint_title": "Choose your saint",
        "preorder_note": "This is a preorder. Expected to ship {date}. You will be charged today.",
        "design_yours": "Design yours",
        "photo_soon": "Photo coming soon",
        "scale_caption": "Shown in hand for scale.",
        "tier_note": "First lamp: {first}. Each additional lamp of the same design: {extra}.",
        "reviews_title": "Reviews",
        "reviews_empty": "No reviews yet.",
        "review_write": "Write a review",
        "review_name": "Your name", "review_rating": "Rating", "review_text": "Your review",
        "review_submit": "Submit my review",
        "review_thanks": "Thanks! Your review will appear after moderation.",
        "review_err": "Please give your name, a rating and your review.",
        "reviews_page_sub": "What our customers say about our pieces.",
        "reviews_all": "All reviews",
        "reviews_see_all": "See all reviews",
        "coupon_label": "Promo code (optional)", "coupon_ph": "e.g. KRISTIE15",
        "coupon_ok": "Code applied: -{pct}%", "coupon_bad": "Invalid code.",
        "preparing": "Preparing checkout...",
        "checkout_failed": "Checkout failed. Please try again.",
        "checkout_failed_try": "Sorry, checkout could not start. Please try again.",
        "order_confirmed": "Order confirmed",
        "err_unknown_product": "unknown product",
        "err_stock": "not enough stock",
        "err_payment": "payments are not configured yet, please try again later",
        "err_sides": "choose all 4 sides",
        "err_request": "please include your name, a valid email, and your idea",
        "login_title": "Seller login", "login_h": "Seller login",
        "login_user": "Username", "login_pass": "Password",
        "login_submit": "Log in", "login_back": "Back to the site",
        "login_bad": "Wrong username or password.",
        "login_disabled": "Password login is not configured. Use your admin link.",
        "logout": "Log out",
        "idea_ok": "Idea received. Thank you, we will reply soon.",
        "idea_fail": "Could not send your idea. Please try again.",
        "only_left": "Only {n} left",
        "preorder_badge": "Preorder",
        "announce_back": "Announcements",
        "lamp_single_label": "Custom memorial lamp (single)",
        "lamp_pack4_label": "Custom memorial lamp (4-pack)",
        "in_works_badge": "In the works",
        "follow_build": "Follow the build",
        "notify_me_label": "Notify me when it's ready",
        "notify_me_ph": "your@email.com",
        "notify_me_btn": "Notify me",
        "notify_ok": "Noted, we'll email you as soon as it's ready.",
        "email_invalid": "Please enter a valid email.",
        "story_title": "The story of the piece",
    },
}

app = Flask(__name__, static_folder="static", static_url_path="")
_secret = os.environ.get("SECRET_KEY")
if not _secret and not DEMO_MODE:
    raise RuntimeError("SECRET_KEY env var is required in production")
app.secret_key = _secret or "dev-secret-change-me"
app.permanent_session_lifetime = timedelta(days=30)


@app.before_request
def canonical_domain():
    """301 old hosts (ritratto.onrender.com, ritratto.ca) to adncreations.ca.
    API/admin paths are excluded so webhooks, AJAX and tooling keep working."""
    host = request.host.split(":")[0].lower()
    if host in ("ritratto.onrender.com", "ritratto.ca", "www.ritratto.ca") \
            and not request.path.startswith(("/api/", "/admin")):
        q = ("?" + request.query_string.decode()) if request.query_string else ""
        return redirect(CANONICAL_URL + request.path + q, 301)


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
    # bilingual content + tiered pricing + photo galleries (added 2026-10-18)
    for ddl in (
        "ALTER TABLE products ADD COLUMN name_fr TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN description_fr TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN story TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN story_fr TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN additional_price_cents INTEGER",
        "ALTER TABLE products ADD COLUMN in_works INTEGER DEFAULT 0",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
    conn.execute(
        "CREATE TABLE IF NOT EXISTS product_photos "
        "(id TEXT PRIMARY KEY, product_id TEXT, photo TEXT DEFAULT '', "
        " sort INTEGER DEFAULT 0, is_scale INTEGER DEFAULT 0, created TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS portrait_ideas "
        "(id TEXT PRIMARY KEY, created TEXT, name TEXT, email TEXT, idea TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notify_me "
        "(id TEXT PRIMARY KEY, created TEXT, product_id TEXT, email TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS project_suggestions "
        "(id TEXT PRIMARY KEY, created TEXT, name TEXT, email TEXT, "
        " title TEXT, description TEXT, category TEXT DEFAULT 'other')"
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
    # Product views: one row per (product, day, visitor) so refreshes don't inflate counts
    conn.execute(
        "CREATE TABLE IF NOT EXISTS product_views "
        "(product_id TEXT, day TEXT, ip_hash TEXT, "
        "PRIMARY KEY (product_id, day, ip_hash))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reviews "
        "(id TEXT PRIMARY KEY, product_id TEXT, name TEXT DEFAULT '', "
        " rating INTEGER DEFAULT 5, text TEXT DEFAULT '', "
        " approved INTEGER DEFAULT 0, created TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS coupons "
        "(code TEXT PRIMARY KEY, percent_off INTEGER DEFAULT 0, "
        " active INTEGER DEFAULT 1, note TEXT DEFAULT '', created TEXT)"
    )
    for ddl in (
        "ALTER TABLE orders ADD COLUMN coupon TEXT DEFAULT ''",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
    # column migrations run AFTER all tables exist (fresh DBs included)
    for ddl in (
        "ALTER TABLE announcements ADD COLUMN title_fr TEXT DEFAULT ''",
        "ALTER TABLE announcements ADD COLUMN body_fr TEXT DEFAULT ''",
        "ALTER TABLE wip_projects ADD COLUMN project_fr TEXT DEFAULT ''",
        "ALTER TABLE wip_projects ADD COLUMN status_fr TEXT DEFAULT ''",
        "ALTER TABLE wip_updates ADD COLUMN text_fr TEXT DEFAULT ''",
        "ALTER TABLE product_photos ADD COLUMN kind TEXT DEFAULT 'photo'",
        # order dispatch (added 2026-10-18)
        "ALTER TABLE orders ADD COLUMN customer_name TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN ship_name TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN ship_address TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN shipped INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN tracking_number TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN carrier TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN shipped_date TEXT DEFAULT ''",
        "ALTER TABLE lamp_orders ADD COLUMN email TEXT DEFAULT ''",
        "ALTER TABLE lamp_orders ADD COLUMN customer_name TEXT DEFAULT ''",
        "ALTER TABLE lamp_orders ADD COLUMN ship_name TEXT DEFAULT ''",
        "ALTER TABLE lamp_orders ADD COLUMN ship_address TEXT DEFAULT ''",
        "ALTER TABLE lamp_orders ADD COLUMN shipped INTEGER DEFAULT 0",
        "ALTER TABLE lamp_orders ADD COLUMN tracking_number TEXT DEFAULT ''",
        "ALTER TABLE lamp_orders ADD COLUMN carrier TEXT DEFAULT ''",
        "ALTER TABLE lamp_orders ADD COLUMN shipped_date TEXT DEFAULT ''",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
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


def track_product_view(pid):
    """Count one view per visitor IP per product per day (refreshes don't inflate)."""
    try:
        fwd = request.headers.get("X-Forwarded-For", "")
        ip = (fwd.split(",")[0].strip() if fwd else "") or (request.remote_addr or "")
        if not ip:
            return
        salt = app.secret_key or "adn-creations"
        ip_hash = hashlib.sha256(f"{salt}|{ip}".encode()).hexdigest()[:24]
        day = datetime.utcnow().strftime("%Y-%m-%d")
        conn = db()
        conn.execute(
            "INSERT OR IGNORE INTO product_views (product_id, day, ip_hash) VALUES (?,?,?)",
            (pid, day, ip_hash))
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
     "description": "Four lithophane faces of Carlo Acutis glow from within: portrait, with the Eucharist, his Assisi sanctuary, and the Virgin Mary. Warm LED light, 10 x 7 x 7 cm. Hand crafted in Montreal from plant-based bioplastic.",
     "name_fr": "Lampe de prière Carlo Acutis à 4 faces",
     "description_fr": "Quatre faces lithophanes de Carlo Acutis qui s'illuminent de l'intérieur : son portrait, avec l'Eucharistie, son sanctuaire d'Assise et la Vierge Marie. Lumière DEL chaude, 10 x 7 x 7 cm. Fait à la main à Montréal en bioplastique d'origine végétale.",
     "story": "Carlo Acutis called the Eucharist his highway to heaven. This lamp gathers four moments of his short life around a warm light: his portrait, the Eucharist he loved, his sanctuary in Assisi, and the Virgin Mary. Each face is a lithophane, printed thin enough that light draws the image out of the plastic itself.",
     "story_fr": "Carlo Acutis appelait l'Eucharistie son autoroute vers le ciel. Cette lampe réunit quatre moments de sa courte vie autour d'une lumière chaude : son portrait, l'Eucharistie qu'il aimait, son sanctuaire d'Assise et la Vierge Marie. Chaque face est un lithophane, imprimé assez fin pour que la lumière dessine l'image à même le plastique.",
     "depts": ["religious", "electronic"], "stock": None, "sort": 1},
    {"id": "padre-pio-lamp", "name": "Padre Pio 4-Face Prayer Lamp", "price_cents": 2499,
     "photo": "/img/products/padre-pio-lamp-1.jpg",
     "description": "Four lithophane faces of Padre Pio glow from within: his portrait, celebrating Mass, his church, and Our Lady with Child. Warm LED light, 10 x 7 x 7 cm. Hand crafted in Montreal from plant-based bioplastic.",
     "name_fr": "Lampe de prière Padre Pio à 4 faces",
     "description_fr": "Quatre faces lithophanes de Padre Pio qui s'illuminent de l'intérieur : son portrait, célébrant la messe, son église et Notre-Dame avec l'Enfant. Lumière DEL chaude, 10 x 7 x 7 cm. Fait à la main à Montréal en bioplastique d'origine végétale.",
     "story": "Padre Pio bore the stigmata for fifty years and called the Mass his strength. This lamp gathers four moments around a warm light: his portrait, Padre Pio raising the host at Mass, his church, and Our Lady with the Child he loved. Each face is a lithophane, printed thin enough that light draws the image out of the plastic itself.",
     "story_fr": "Padre Pio a porté les stigmates pendant cinquante ans et appelait la messe sa force. Cette lampe réunit quatre moments autour d'une lumière chaude : son portrait, Padre Pio élevant l'hostie à la messe, son église et Notre-Dame avec l'Enfant qu'il aimait. Chaque face est un lithophane, imprimé assez fin pour que la lumière dessine l'image à même le plastique.",
     "depts": ["religious", "electronic"], "stock": None, "sort": 2},
    {"id": "sheen-lamp", "name": "Fulton Sheen 4-Face Prayer Lamp", "price_cents": 1999,
     "photo": "/img/products/sheen-lamp.jpg",
     "description": "Four lithophane faces of Blessed Fulton Sheen in warm LED light. Hand crafted in Montreal from plant-based bioplastic.",
     "name_fr": "Lampe de prière Fulton Sheen à 4 faces",
     "description_fr": "Quatre faces lithophanes du bienheureux Fulton Sheen sous une chaude lumière DEL. Fait à la main à Montréal en bioplastique d'origine végétale.",
     "story": "Blessed Fulton Sheen carried the faith onto television. Four of his faces glow from within this lamp, printed as lithophanes in warm LED light.",
     "story_fr": "Le bienheureux Fulton Sheen a porté la foi à la télévision. Quatre de ses visages s'illuminent de l'intérieur de cette lampe, imprimés en lithophanes sous une chaude lumière DEL.",
     "depts": ["religious", "electronic"], "stock": None, "sort": 2},
    {"id": "memorial-lamp", "name": "Custom Memorial Lamp", "price_cents": 3999,
     "additional_price_cents": 2499,
     "photo": "/img/products/memorial-lamp.jpg",
     "description": "Your photos or our saint illustrations on four glowing faces. $39.99 for the first lamp of a design, $24.99 for each additional copy of the same design, or a 4-pack for $99.99. Use the lamp designer to compose your four sides.",
     "name_fr": "Lampe commémorative personnalisée",
     "description_fr": "Vos photos ou nos illustrations de saints sur quatre faces lumineuses. 39,99 $ pour la première lampe d'un modèle, 24,99 $ pour chaque exemplaire supplémentaire du même modèle, ou un paquet de 4 pour 99,99 $. Utilisez l'outil de création pour composer vos quatre faces.",
     "story": "A lamp that keeps someone present. Four glowing faces carry your photos or our saint illustrations, printed as lithophanes that come alive in warm light. Each one is made to order in the workshop.",
     "story_fr": "Une lampe qui garde une présence vivante. Quatre faces lumineuses portent vos photos ou nos illustrations de saints, imprimées en lithophanes qui s'animent dans une lumière chaude. Chaque lampe est fabriquée sur commande à l'atelier.",
     "depts": ["religious", "electronic"], "stock": None, "custom_link": "/custom-lamp.html", "sort": 3},
    {"id": "bust-collector", "name": "Saint Frere Andre Bust, Collector's Edition", "price_cents": 224999,
     "photo": "/img/products/bust-real-front.jpg",
     "description": "One of one. 39 cm hand finished bust on a dark stained wood base with a brass Fr. Andre name plate. Heavy, highly detailed, made with additive manufacturing and plant-based materials with very little waste. Free shipping.",
     "name_fr": "Buste de saint Frère André, édition collectionneur",
     "description_fr": "Pièce unique. Buste de 39 cm fini à la main sur un socle en bois teinté foncé avec une plaque de laiton au nom du Fr. André. Lourd, très détaillé, fabriqué par fabrication additive avec des matériaux d'origine végétale et très peu de déchets. Expédition gratuite.",
     "story": "A collector's piece for the era of Saint Frère André. The 39 cm bust is printed in large-format additive manufacturing, then finished by hand, and mounted on a dark stained wood base with a brass Fr. Andre name plate. Heavy, highly detailed, one of one.",
     "story_fr": "Une pièce de collection pour l'époque de saint Frère André. Le buste de 39 cm est imprimé en fabrication additive grand format, puis fini à la main, et monté sur un socle en bois teinté foncé avec une plaque de laiton au nom du Fr. André. Lourd, très détaillé, pièce unique.",
     "depts": ["religious"], "stock": 1, "sort": 4},
    {"id": "nativity", "name": "Nativity Scene Lamp", "price_cents": 3999,
     "photo": "/img/products/nativity.jpg",
     "description": "The Nativity rendered as a glowing lithophane lamp. Warm LED light. Hand crafted in Montreal from plant-based bioplastic.",
     "name_fr": "Lampe scène de la Nativité",
     "description_fr": "La Nativité en lampe lithophane lumineuse. Lumière DEL chaude. Fait à la main à Montréal en bioplastique d'origine végétale.",
     "story": "The Nativity as a light in the dark. The Holy Family rendered as a glowing lithophane, a steady favourite at the Oratory boutique every Christmas season.",
     "story_fr": "La Nativité comme une lumière dans la nuit. La Sainte Famille en lithophane lumineux, un succès constant à la boutique de l'Oratoire à chaque temps des fêtes.",
     "depts": ["religious", "electronic"], "stock": None, "sort": 5},
    {"id": "lighter", "name": "Engraved Lighter", "price_cents": 2399,
     "photo": "/img/products/lighter.jpg",
     "description": "Zippo-style lighter with your text or artwork laser engraved. Add your engraving text at checkout and we will lay it out for you.",
     "name_fr": "Briquet gravé",
     "description_fr": "Briquet style Zippo avec votre texte ou votre dessin gravé au laser. Ajoutez votre texte de gravure à la caisse et nous nous occupons de la mise en page.",
     "story": "A Zippo-style lighter becomes a personal object. Your text or artwork, laser engraved with a fiber laser for a mark that will not fade.",
     "story_fr": "Un briquet style Zippo devient un objet personnel. Votre texte ou votre dessin, gravé au laser à fibre pour une marque qui ne s'effacera pas.",
     "depts": ["gag"], "stock": None, "engravable": 1, "sort": 6},
    {"id": "custom-lighter", "name": "Custom Engraved Lighter", "price_cents": 2999,
     "photo": "/img/products/custom-lighter.jpg",
     "description": "Your logo, monogram, or artwork, laid out by hand and laser engraved on a Zippo-style lighter in its gift case. Describe your design at checkout and I will lay it out for you.",
     "name_fr": "Briquet gravé sur mesure",
     "description_fr": "Votre logo, monogramme ou dessin, mis en page à la main et gravé au laser sur un briquet style Zippo dans son coffret cadeau. Décrivez votre motif à la caisse et je m'occupe de la mise en page.",
     "story": "The Aku lighter: a big serif A with the name set inside, engraved with the fiber laser. Send your own artwork or just an idea and it becomes a one-of-one object.",
     "story_fr": "Le briquet Aku : un grand A serif avec le nom à l'intérieur, gravé au laser à fibre. Envoyez votre propre dessin ou simplement une idée et il devient un objet unique.",
     "depts": ["gag"], "stock": None, "engravable": 1, "sort": 7},
    {"id": "mug", "name": "Engraved Contigo Travel Mug", "price_cents": 3399,
     "photo": "/img/products/mug.jpg",
     "description": "Contigo travel mug with your text laser engraved. Add your engraving text at checkout.",
     "name_fr": "Tasse de voyage Contigo gravée",
     "description_fr": "Tasse de voyage Contigo avec votre texte gravé au laser. Ajoutez votre texte de gravure à la caisse.",
     "story": "Your everyday mug, made yours. Text laser engraved on a Contigo travel mug that keeps drinks hot for hours.",
     "story_fr": "Votre tasse de tous les jours, personnalisée. Texte gravé au laser sur une tasse de voyage Contigo qui garde les boissons chaudes pendant des heures.",
     "depts": [], "stock": None, "engravable": 1, "sort": 7},
    {"id": "card-case", "name": "Italian Playing-Card Case", "price_cents": 2499,
     "photo": "",
     "description": "Fitted case for Italian playing cards, Scopa and Briscola sizes. Hand crafted from plant-based bioplastic.",
     "name_fr": "Étui pour cartes à jouer italiennes",
     "description_fr": "Étui ajusté pour jeux de cartes italiennes, formats Scopa et Briscola. Fait à la main en bioplastique d'origine végétale.",
     "story": "Italian card games deserve better than a torn box. A fitted case for Scopa and Briscola decks, printed to precise tolerances so the cards slide in just right.",
     "story_fr": "Les jeux de cartes italiens méritent mieux qu'une boîte déchirée. Un étui ajusté pour les jeux Scopa et Briscola, imprimé avec des tolérances précises pour que les cartes s'y glissent parfaitement.",
     "depts": [], "stock": None, "sort": 8},
    {"id": "giftcard-case", "name": "Gift-Card Case", "price_cents": 1499,
     "photo": "",
     "description": "A keepsake case that turns a gift card into a real gift. Hand crafted from plant-based bioplastic.",
     "name_fr": "Étui pour carte-cadeau",
     "description_fr": "Un écrin qui transforme une carte-cadeau en vrai cadeau. Fait à la main en bioplastique d'origine végétale.",
     "story": "A gift card in an envelope is an afterthought. In a keepsake case, it becomes a real gift.",
     "story_fr": "Une carte-cadeau dans une enveloppe, c'est un pis-aller. Dans un écrin souvenir, elle devient un vrai cadeau.",
     "depts": [], "stock": None, "sort": 9},
    {"id": "battery-door", "name": "Threaded Battery Door", "price_cents": 1199,
     "photo": "",
     "description": "Precision threaded battery door, printed to fit. Hand crafted from plant-based bioplastic.",
     "name_fr": "Couvercle de pile fileté",
     "description_fr": "Couvercle de pile fileté de précision, imprimé sur mesure. Fait à la main en bioplastique d'origine végétale.",
     "story": "A small part, engineered properly. A precision threaded battery door, printed to fit the first time.",
     "story_fr": "Une petite pièce, bien conçue. Un couvercle de pile fileté de précision, imprimé pour s'ajuster du premier coup.",
     "depts": [], "stock": None, "sort": 10},
    {"id": "gag-soon", "name": "Gag Department", "price_cents": 0,
     "photo": "",
     "description": "Novelty and funny items are on the way. Check back soon.",
     "name_fr": "Rayon humour",
     "description_fr": "Des articles de fantaisie et humoristiques sont en route. Revenez bientôt.",
     "depts": ["gag"], "purchasable": 0, "sort": 11},
]

# Extra gallery photos per product (seeded once): (product_id, photo, sort, is_scale)
SEED_PHOTOS = [
    ("carlo-lamp", "/img/products/carlo-lamp.jpg", 0, 0),
    ("carlo-lamp", "/img/work/carlo-lamp-lit.jpg", 1, 0),
    ("sheen-lamp", "/img/products/sheen-lamp.jpg", 0, 0),
    ("sheen-lamp", "/img/products/sheen-lamp-2.jpg", 1, 0),
    ("memorial-lamp", "/img/products/memorial-lamp.jpg", 0, 0),
    ("bust-collector", "/img/products/bust-real-front.jpg", 0, 0),
    ("bust-collector", "/img/products/bust-real-34.jpg", 1, 0),
    ("bust-collector", "/img/products/bust-real-front2.jpg", 2, 0),
    ("nativity", "/img/products/nativity.jpg", 0, 0),
    ("lighter", "/img/products/lighter.jpg", 0, 0),
    ("lighter", "/img/work/lighter-detail.jpg", 1, 0),
    ("mug", "/img/products/mug.jpg", 0, 0),
]

# Round-3 gallery photos (2026-10-18): real photos from Antonio's library,
# EXIF-oriented. (product_id, photo) — appended after existing gallery rows.
SEED_PHOTOS_EXTRA = [
    ("carlo-lamp", "/img/products/carlo-lamp-2.jpg"),
    ("carlo-lamp", "/img/products/carlo-lamp-3.jpg"),
    ("nativity", "/img/products/nativity-2.jpg"),
    ("nativity", "/img/products/nativity-3.png"),
    ("lighter", "/img/products/lighter-2.jpg"),
    ("lighter", "/img/products/lighter-3.jpg"),
    ("mug", "/img/products/mug-2.jpg"),
    ("giftcard-case", "/img/products/giftcard-case.jpg"),
    ("custom-lighter", "/img/products/custom-lighter-2.jpg"),
]


def seed():
    conn = db()
    n = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if n == 0:
        for p in SEED_PRODUCTS:
            conn.execute(
                "INSERT INTO products (id, name, name_fr, price_cents, additional_price_cents, "
                "photo, description, description_fr, story, story_fr, depts, "
                "stock, preorder, preorder_ship_date, engravable, purchasable, custom_link, "
                "active, sort, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p["id"], p["name"], p.get("name_fr", ""), p["price_cents"],
                 p.get("additional_price_cents"),
                 p.get("photo", ""), p.get("description", ""), p.get("description_fr", ""),
                 p.get("story", ""), p.get("story_fr", ""),
                 json.dumps(p.get("depts", [])),
                 p.get("stock"), 0, "", p.get("engravable", 0),
                 p.get("purchasable", 1), p.get("custom_link", ""), 1,
                 p.get("sort", 0), now_iso()))
    # New product 2026-10-18: custom lighter listing (only if missing).
    if not conn.execute("SELECT id FROM products WHERE id='custom-lighter'").fetchone():
        conn.execute(
            "INSERT INTO products (id, name, name_fr, price_cents, photo, "
            "description, description_fr, story, story_fr, depts, "
            "stock, preorder, preorder_ship_date, engravable, purchasable, custom_link, "
            "active, sort, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("custom-lighter", "Custom Engraved Lighter", "Briquet gravé sur mesure", 2999,
             "/img/products/custom-lighter.jpg",
             "Your logo, monogram, or artwork, laid out by hand and laser engraved on a "
             "Zippo-style lighter in its gift case. Describe your design at checkout and I "
             "will lay it out for you.",
             "Votre logo, monogramme ou dessin, mis en page à la main et gravé au laser sur un "
             "briquet style Zippo dans son coffret cadeau. Décrivez votre motif à la caisse et "
             "je m'occupe de la mise en page.",
             "The Aku lighter: a big serif A with the name set inside, engraved with the fiber laser. "
             "Send your own artwork or just an idea and it becomes a one-of-one object.",
             "Le briquet Aku : un grand A serif avec le nom à l'intérieur, gravé au laser à fibre. "
             "Envoyez votre propre dessin ou simplement une idée et il devient un objet unique.",
             json.dumps(["gag"]), None, 0, "", 1, 1, "", 1, 7, now_iso()))
    # New product 2026-10-18: Padre Pio 4-face prayer lamp (only if missing).
    if not conn.execute("SELECT id FROM products WHERE id='padre-pio-lamp'").fetchone():
        conn.execute(
            "INSERT INTO products (id, name, name_fr, price_cents, photo, "
            "description, description_fr, story, story_fr, depts, "
            "stock, preorder, preorder_ship_date, engravable, purchasable, custom_link, "
            "active, sort, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("padre-pio-lamp", "Padre Pio 4-Face Prayer Lamp", "Lampe de prière Padre Pio à 4 faces", 2499,
             "/img/products/padre-pio-lamp-1.jpg",
             "Four lithophane faces of Padre Pio glow from within: his portrait, celebrating Mass, "
             "his church, and Our Lady with Child. Warm LED light, 10 x 7 x 7 cm. Hand crafted in "
             "Montreal from plant-based bioplastic.",
             "Quatre faces lithophanes de Padre Pio qui s'illuminent de l'intérieur : son portrait, "
             "célébrant la messe, son église et Notre-Dame avec l'Enfant. Lumière DEL chaude, "
             "10 x 7 x 7 cm. Fait à la main à Montréal en bioplastique d'origine végétale.",
             "Padre Pio bore the stigmata for fifty years and called the Mass his strength. This lamp "
             "gathers four moments around a warm light: his portrait, Padre Pio raising the host at Mass, "
             "his church, and Our Lady with the Child he loved. Each face is a lithophane, printed thin "
             "enough that light draws the image out of the plastic itself.",
             "Padre Pio a porté les stigmates pendant cinquante ans et appelait la messe sa force. "
             "Cette lampe réunit quatre moments autour d'une lumière chaude : son portrait, Padre Pio "
             "élevant l'hostie à la messe, son église et Notre-Dame avec l'Enfant qu'il aimait. Chaque face "
             "est un lithophane, imprimé assez fin pour que la lumière dessine l'image à même le plastique.",
             json.dumps(["religious", "electronic"]), None, 0, "", 0, 1, "", 1, 2, now_iso()))
    # Gallery for padre-pio-lamp (idempotent, fills gaps).
    for _i in range(1, 9):
        _phpid = f"php_padrepio{_i}"
        _ph = f"/img/products/padre-pio-lamp-{_i}.jpg"
        if not conn.execute("SELECT id FROM product_photos WHERE id=?", (_phpid,)).fetchone():
            conn.execute(
                "INSERT INTO product_photos (id, product_id, photo, sort, is_scale, created) "
                "VALUES (?,?,?,?,?,?)",
                (_phpid, "padre-pio-lamp", _ph, _i - 1, 0, now_iso()))
    # Gallery for card-case: Briscola + Scopa real photos 2026-10-18 (idempotent).
    _card_photos = [f"/img/products/briscola-case-{_i}.webp" for _i in range(1, 7)] + \
                   [f"/img/products/scopa-case-{_i}.webp" for _i in range(1, 6)]
    for _s, _ph in enumerate(_card_photos):
        _phpid = "php_cardcase_" + _ph.split("/")[-1].replace(".", "_")
        if not conn.execute("SELECT id FROM product_photos WHERE id=?", (_phpid,)).fetchone():
            conn.execute(
                "INSERT INTO product_photos (id, product_id, photo, sort, is_scale, created) "
                "VALUES (?,?,?,?,?,?)",
                (_phpid, "card-case", _ph, _s, 0, now_iso()))
    conn.execute(
        "UPDATE products SET photo='/img/products/briscola-case-1.webp' "
        "WHERE id='card-case' AND (photo IS NULL OR photo='')")
    # 2026-10-18: mini saint busts WIP project from Antonio's progress photos
    # (Sheen & Carlo minis on the pedestal). Idempotent.
    if not conn.execute("SELECT id FROM wip_projects WHERE id='mini-busts'").fetchone():
        conn.execute(
            "INSERT INTO wip_projects (id, project, project_fr, status, status_fr, photo, sort, created) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("mini-busts", "Mini Saint Busts \u2014 Fr\u00e8re Andr\u00e9 & Carlo",
             "Mini-bustes de saints \u2014 Fr\u00e8re Andr\u00e9 et Carlo",
             "In development", "En d\u00e9veloppement",
             "/img/work/mini-bust-1.jpg", 3, now_iso()))
        conn.execute(
            "INSERT INTO wip_updates (id, project_id, created, text, text_fr) VALUES (?,?,?,?,?)",
            ("mb1", "mini-busts", now_iso(),
             "Detailed mini busts of Saint Fr\u00e8re Andr\u00e9 and Carlo Acutis, styled on the pedestal. "
             "Mini statues at $24.99 and $39.99.",
             "Mini-bustes d\u00e9taill\u00e9s de saint Fr\u00e8re Andr\u00e9 et Carlo Acutis, pr\u00e9sent\u00e9s sur le pi\u00e9destal. "
             "Mini-statues \u00e0 24,99 $ et 39,99 $."))
    # 2026-10-18: stone-finish statue WIP project (museum delivery) from Antonio's progress photos.
    # Idempotent.
    if not conn.execute("SELECT id FROM wip_projects WHERE id='stone-statues'").fetchone():
        conn.execute(
            "INSERT INTO wip_projects (id, project, project_fr, status, status_fr, photo, sort, created) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("stone-statues", "Stone statues \u2014 Fr\u00e8re Andr\u00e9 & Carlo Acutis",
             "Statues de pierre \u2014 Fr\u00e8re Andr\u00e9 et Carlo Acutis",
             "In finishing", "En finition",
             "/img/work/statue-frere-andre-grande-studio.jpg", 2, now_iso()))
        for _uid, _txt, _txt_fr in (
            ("ss1",
             "Big Fr\u00e8re Andr\u00e9 bust printed on the Bambu H2D, supports removed, sanded smooth \u2014 "
             "no visible layer lines.",
             "Grand buste du Fr\u00e8re Andr\u00e9 imprim\u00e9 sur la Bambu H2D, supports retir\u00e9s, pon\u00e7age lisse \u2014 "
             "aucune ligne de couche visible."),
            ("ss2",
             "Primer on, then gloss white paint and a non-yellowing clear coat for the real stone look.",
             "Appr\u00eat appliqu\u00e9, puis peinture blanc brillant et vernis transparent anti-jaunissement "
             "pour un vrai aspect pierre."),
            ("ss3",
             "Fitted on a solid wood base with the engraved name plate. The Oratory nativity scenes are "
             "now on the boutique shelf at $23.99.",
             "Mont\u00e9 sur un socle en bois massif avec plaque grav\u00e9e. Les cr\u00e8ches de l'Oratoire sont "
             "maintenant en boutique \u00e0 23,99 $.")):
            conn.execute(
                "INSERT INTO wip_updates (id, project_id, created, text, text_fr) VALUES (?,?,?,?,?)",
                (_uid, "stone-statues", now_iso(), _txt, _txt_fr))
    # 2026-10-18: nativity lamp WIP project (Oratory boutique) from Antonio's photos. Idempotent.
    if not conn.execute("SELECT id FROM wip_projects WHERE id='nativity-lamps'").fetchone():
        conn.execute(
            "INSERT INTO wip_projects (id, project, project_fr, status, status_fr, photo, sort, created) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("nativity-lamps", "Nativity lamps \u2014 Oratory boutique",
             "Cr\u00e8ches lumineuses \u2014 boutique de l'Oratoire",
             "In stores", "En boutique",
             "/img/work/nativity-lamp-lit.jpg", 1, now_iso()))
        for _uid, _txt, _txt_fr in (
            ("nl1",
             "The Holy Family nativity under the Oratory dome, printed thin so it glows like a "
             "lithophane with a battery light inside.",
             "La Sainte Famille sous le d\u00f4me de l'Oratoire, imprim\u00e9e en paroi fine pour diffuser "
             "la lumi\u00e8re comme un lithophane, avec pile incluse."),
            ("nl2",
             "Full box packed and delivered \u2014 now on the boutique shelf at $23.99.",
             "Bo\u00eete compl\u00e8te emball\u00e9e et livr\u00e9e \u2014 maintenant en boutique \u00e0 23,99 $.")):
            conn.execute(
                "INSERT INTO wip_updates (id, project_id, created, text, text_fr) VALUES (?,?,?,?,?)",
                (_uid, "nativity-lamps", now_iso(), _txt, _txt_fr))
    # 2026-10-18: custom engraved bottles WIP project from Antonio's photo. Idempotent.
    if not conn.execute("SELECT id FROM wip_projects WHERE id='engraved-bottles'").fetchone():
        conn.execute(
            "INSERT INTO wip_projects (id, project, project_fr, status, status_fr, photo, sort, created) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("engraved-bottles", "Custom engraved bottles",
             "Bouteilles grav\u00e9es sur mesure",
             "Now available", "Disponible",
             "/img/work/engraved-bottle-lydia.jpg", 4, now_iso()))
        conn.execute(
            "INSERT INTO wip_updates (id, project_id, created, text, text_fr) VALUES (?,?,?,?,?)",
            ("eb1", "engraved-bottles", now_iso(),
             "Name and artwork laser-engraved on a matte bottle with the xTool F2 \u2014 "
             "any name, any design.",
             "Nom et dessin grav\u00e9s au laser sur une bouteille mate avec la xTool F2 \u2014 "
             "n'importe quel nom, n'importe quel dessin."))
    # 2026-10-18: single lighter listing at $24.99 (Etsy parity). The older
    # "lighter" product is retired; "custom-lighter" becomes the one listing,
    # keeping its real Aku photo in the gallery and the Stogies mockup as card.
    conn.execute("UPDATE products SET price_cents=2499 WHERE id='custom-lighter' AND price_cents != 2499")
    conn.execute("UPDATE products SET active=0 WHERE id='lighter'")
    _cl_photos = ["/img/products/custom-lighter.jpg",
                  "/img/products/custom-lighter-stogies.jpg",
                  "/img/products/custom-lighter-mirelas-chrome.jpg",
                  "/img/products/custom-lighter-mirelas-chef.jpg",
                  "/img/products/lighter.jpg",
                  "/img/work/lighter-detail.jpg"]
    for _s, _ph in enumerate(_cl_photos):
        _phpid = "php_cl_" + _ph.split("/")[-1].replace(".", "_")
        if not conn.execute("SELECT id FROM product_photos WHERE id=?", (_phpid,)).fetchone():
            conn.execute(
                "INSERT INTO product_photos (id, product_id, photo, sort, is_scale, created) "
                "VALUES (?,?,?,?,?,?)",
                (_phpid, "custom-lighter", _ph, _s + 2, 0, now_iso()))
    conn.execute(
        "UPDATE products SET photo='/img/products/custom-lighter-stogies.jpg' "
        "WHERE id='custom-lighter' AND photo='/img/products/custom-lighter.jpg'")
    # 2026-10-18: mini saint busts, two sizes (Antonio: $24.99 small, $39.99 large).
    for _pid, _name, _name_fr, _cents, _photo in (
            ("mini-bust-small", "Mini Saint Bust \u2014 Small", "Mini-buste de saint \u2014 Petit",
             2499, "/img/work/mini-bust-1.jpg"),
            ("mini-bust-large", "Mini Saint Bust \u2014 Large", "Mini-buste de saint \u2014 Grand",
             3999, "/img/products/mini-bust-k1.jpg")):
        if not conn.execute("SELECT id FROM products WHERE id=?", (_pid,)).fetchone():
            conn.execute(
                "INSERT INTO products (id, name, name_fr, price_cents, photo, "
                "description, description_fr, story, story_fr, depts, "
                "stock, preorder, preorder_ship_date, engravable, purchasable, custom_link, "
                "active, sort, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_pid, _name, _name_fr, _cents, _photo,
                 "A detailed mini bust of Saint Fr\u00e8re Andr\u00e9 or Carlo Acutis, hand finished "
                 "in Montreal from plant-based bioplastic. Choose your saint at checkout.",
                 "Mini-buste d\u00e9taill\u00e9 de saint Fr\u00e8re Andr\u00e9 ou Carlo Acutis, fini \u00e0 la main "
                 "\u00e0 Montr\u00e9al en bioplastique d'origine v\u00e9g\u00e9tale. Choisissez votre saint \u00e0 la caisse.",
                 "The collector bust, scaled for a desk or shelf. Same hand-finished detail, "
                 "in a size that fits anywhere.",
                 "Le buste collectionneur, en format bureau ou \u00e9tag\u00e8re. Le m\u00eame fini main, "
                 "dans un format qui va partout.",
                 json.dumps(["religious"]), None, 0, "", 1, 1, "", 1,
                 8 if _pid == "mini-bust-small" else 9, now_iso()))
    _mb_photos = ["/img/work/mini-bust-1.jpg", "/img/work/mini-bust-4.jpg",
                  "/img/products/mini-bust-k1.jpg", "/img/products/mini-bust-k4.jpg",
                  "/img/products/mini-bust-k6.jpg"]
    for _pid in ("mini-bust-small", "mini-bust-large"):
        for _s, _ph in enumerate(_mb_photos):
            _phpid = f"php_{_pid}_" + _ph.split("/")[-1].replace(".", "_")
            if not conn.execute("SELECT id FROM product_photos WHERE id=?", (_phpid,)).fetchone():
                conn.execute(
                    "INSERT INTO product_photos (id, product_id, photo, sort, is_scale, created) "
                    "VALUES (?,?,?,?,?,?)",
                    (_phpid, _pid, _ph, _s, 0, now_iso()))
    # pro-background hand-held photo (mug-10), 2026-10-18 (idempotent).
    _mug_photos = [f"/img/products/mug-{_i}.jpg" for _i in range(3, 11)]
    for _s, _ph in enumerate(_mug_photos):
        _phpid = "php_mug_" + _ph.split("/")[-1].replace(".", "_")
        if not conn.execute("SELECT id FROM product_photos WHERE id=?", (_phpid,)).fetchone():
            conn.execute(
                "INSERT INTO product_photos (id, product_id, photo, sort, is_scale, created) "
                "VALUES (?,?,?,?,?,?)",
                (_phpid, "mug", _ph, _s + 2, 0, now_iso()))
    # Pro-background hand-held shot becomes the mug card photo (only if Antonio
    # hasn't already changed it from the original workshop photo).
    conn.execute(
        "UPDATE products SET photo='/img/products/mug-10.jpg' "
        "WHERE id='mug' AND photo='/img/products/mug.jpg'")
    # Pricing 2026-10-18: custom memorial lamps are $39.99 for the first of a
    # design, $29.99 for each additional copy, 4-pack $99.99. Charm pricing
    # (.99) across the shop. Only touches rows still on the old pricing,
    # never Antonio's later edits.
    conn.execute(
        "UPDATE products SET price_cents=3999, additional_price_cents=2999, "
        "description=?, description_fr=? "
        "WHERE id='memorial-lamp' AND price_cents IN (2000, 2500, 4000)",
        ("Your photos or our saint illustrations on four glowing faces. "
         "$39.99 for the first lamp of a design, $29.99 for each additional copy of the same design, "
         "or a 4-pack for $99.99. Use the lamp designer to compose your four sides.",
         "Vos photos ou nos illustrations de saints sur quatre faces lumineuses. "
         "39,99 $ pour la première lampe d'un modèle, 29,99 $ pour chaque exemplaire "
         "supplémentaire du même modèle, ou un paquet de 4 pour 99,99 $. "
         "Utilisez l'outil de création pour composer vos quatre faces."))
    # Pricing 2026-10-18 (Antonio): additional memorial-lamp copies are $24.99
    # (was $29.99). Only touches rows still on the $29.99 additional price,
    # never Antonio's later edits.
    conn.execute(
        "UPDATE products SET additional_price_cents=2499, description=?, description_fr=? "
        "WHERE id='memorial-lamp' AND additional_price_cents=2999",
        ("Your photos or our saint illustrations on four glowing faces. "
         "$39.99 for the first lamp of a design, $24.99 for each additional copy of the same design, "
         "or a 4-pack for $99.99. Use the lamp designer to compose your four sides.",
         "Vos photos ou nos illustrations de saints sur quatre faces lumineuses. "
         "39,99 $ pour la première lampe d'un modèle, 24,99 $ pour chaque exemplaire "
         "supplémentaire du même modèle, ou un paquet de 4 pour 99,99 $. "
         "Utilisez l'outil de création pour composer vos quatre faces."))
    for _pid, _old, _new in (("lighter", 2400, 2399), ("mug", 3400, 3399),
                             ("card-case", 2500, 2499), ("giftcard-case", 1500, 1499),
                             ("battery-door", 1200, 1199), ("bust-collector", 225000, 224999)):
        conn.execute("UPDATE products SET price_cents=? WHERE id=? AND price_cents=?",
                     (_new, _pid, _old))
    # French content for rows seeded before the bilingual update
    fr_updates = {
        "carlo-lamp": ("Lampe de pri\u00e8re Carlo Acutis \u00e0 4 faces",
            "Quatre faces lithophanes de Carlo Acutis qui s'illuminent de l'int\u00e9rieur : son portrait, avec l'Eucharistie, son sanctuaire d'Assise et la Vierge Marie. Lumi\u00e8re DEL chaude, 10 x 7 x 7 cm. Fait \u00e0 la main \u00e0 Montr\u00e9al en bioplastique d'origine v\u00e9g\u00e9tale."),
        "sheen-lamp": ("Lampe de pri\u00e8re Fulton Sheen \u00e0 4 faces",
            "Quatre faces lithophanes du bienheureux Fulton Sheen sous une chaude lumi\u00e8re DEL. Fait \u00e0 la main \u00e0 Montr\u00e9al en bioplastique d'origine v\u00e9g\u00e9tale."),
        "bust-collector": ("Buste de saint Fr\u00e8re Andr\u00e9, \u00e9dition collectionneur",
            "Pi\u00e8ce unique. Buste de 39 cm fini \u00e0 la main sur un socle en bois teint\u00e9 fonc\u00e9 avec une plaque de laiton au nom du Fr. Andr\u00e9. Lourd, tr\u00e8s d\u00e9taill\u00e9, fabriqu\u00e9 par fabrication additive avec des mat\u00e9riaux d'origine v\u00e9g\u00e9tale et tr\u00e8s peu de d\u00e9chets. Exp\u00e9dition gratuite."),
        "nativity": ("Lampe sc\u00e8ne de la Nativit\u00e9",
            "La Nativit\u00e9 en lampe lithophane lumineuse. Lumi\u00e8re DEL chaude. Fait \u00e0 la main \u00e0 Montr\u00e9al en bioplastique d'origine v\u00e9g\u00e9tale."),
        "lighter": ("Briquet grav\u00e9",
            "Briquet style Zippo avec votre texte ou votre dessin grav\u00e9 au laser. Ajoutez votre texte de gravure \u00e0 la caisse et nous nous occupons de la mise en page."),
        "mug": ("Tasse de voyage Contigo grav\u00e9e",
            "Tasse de voyage Contigo avec votre texte grav\u00e9 au laser. Ajoutez votre texte de gravure \u00e0 la caisse."),
        "card-case": ("\u00c9tui pour cartes \u00e0 jouer italiennes",
            "\u00c9tui ajust\u00e9 pour jeux de cartes italiennes, formats Scopa et Briscola. Fait \u00e0 la main en bioplastique d'origine v\u00e9g\u00e9tale."),
        "giftcard-case": ("\u00c9tui pour carte-cadeau",
            "Un \u00e9crin qui transforme une carte-cadeau en vrai cadeau. Fait \u00e0 la main en bioplastique d'origine v\u00e9g\u00e9tale."),
        "battery-door": ("Couvercle de pile filet\u00e9",
            "Couvercle de pile filet\u00e9 de pr\u00e9cision, imprim\u00e9 sur mesure. Fait \u00e0 la main en bioplastique d'origine v\u00e9g\u00e9tale."),
        "gag-soon": ("Rayon humour",
            "Des articles de fantaisie et humoristiques sont en route. Revenez bient\u00f4t."),
    }
    for pid, (nfr, dfr) in fr_updates.items():
        conn.execute(
            "UPDATE products SET name_fr=?, description_fr=? "
            "WHERE id=? AND (name_fr IS NULL OR name_fr='')", (nfr, dfr, pid))
    # Fulton Sheen photos now exist (added 2026-10-18)
    conn.execute(
        "UPDATE products SET photo='/img/products/sheen-lamp.jpg' "
        "WHERE id='sheen-lamp' AND (photo IS NULL OR photo='')")
    # Seed product photo galleries (once)
    if conn.execute("SELECT COUNT(*) FROM product_photos").fetchone()[0] == 0:
        for pid, photo, sort, is_scale in SEED_PHOTOS:
            conn.execute(
                "INSERT INTO product_photos (id, product_id, photo, sort, is_scale, created) "
                "VALUES (?,?,?,?,?,?)",
                ("ph_" + uuid.uuid4().hex[:10], pid, photo, sort, is_scale, now_iso()))
    # Round-3 gallery photos (2026-10-18): insert any missing (product_id, photo)
    # pairs, appended after existing rows so Antonio's ordering is untouched.
    for pid, photo in SEED_PHOTOS_EXTRA:
        exists = conn.execute(
            "SELECT 1 FROM product_photos WHERE product_id=? AND photo=?",
            (pid, photo)).fetchone()
        if not exists:
            mx = conn.execute(
                "SELECT COALESCE(MAX(sort), -1) FROM product_photos WHERE product_id=?",
                (pid,)).fetchone()[0]
            conn.execute(
                "INSERT INTO product_photos (id, product_id, photo, sort, is_scale, created) "
                "VALUES (?,?,?,?,?,?)",
                ("ph_" + uuid.uuid4().hex[:10], pid, photo, mx + 1, 0, now_iso()))
    # 2026-10-18: Antonio replaced the bust gallery with 3 real photos only.
    # One-time: if any old bust photo is still present, swap the whole gallery
    # for the 3 real ones and point the product card at the first. The gate
    # keys on the old paths so later admin uploads are never touched.
    _bust_old = ("/img/products/bust.jpg", "/img/work/bust-3q.jpg",
                 "/img/work/bust-front.jpg", "/img/products/bust-signature.webp",
                 "/img/products/bust-threequarter.webp", "/img/products/bust-otherside.webp",
                 "/img/products/bust-elevated.webp", "/img/products/bust-rear.webp",
                 "/img/products/bust-face.webp", "/img/products/bust-workshop.webp")
    _bust_new = ("/img/products/bust-real-front.jpg", "/img/products/bust-real-34.jpg",
                 "/img/products/bust-real-front2.jpg")
    if conn.execute(
            "SELECT 1 FROM product_photos WHERE product_id='bust-collector' AND photo IN (%s)"
            % ",".join("?" * len(_bust_old)), _bust_old).fetchone():
        conn.execute("DELETE FROM product_photos WHERE product_id='bust-collector'")
        for _i, _ph in enumerate(_bust_new):
            conn.execute(
                "INSERT INTO product_photos (id, product_id, photo, sort, is_scale, created) "
                "VALUES (?,?,?,?,?,?)",
                ("ph_" + uuid.uuid4().hex[:10], "bust-collector", _ph, _i, 0, now_iso()))
        conn.execute(
            "UPDATE products SET photo='/img/products/bust-real-front.jpg' "
            "WHERE id='bust-collector'")
    # The gift-card case finally has a real photo: use it as the product photo too.
    conn.execute(
        "UPDATE products SET photo='/img/products/giftcard-case.jpg' "
        "WHERE id='giftcard-case' AND (photo IS NULL OR photo='')")
    if conn.execute("SELECT COUNT(*) FROM announcements").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO announcements (id, created, title, title_fr, body, body_fr) VALUES (?,?,?,?,?,?)",
            ("seed1", "2026-10-18T09:00:00",
             "The ADN Creations store is now live",
             "La boutique ADN Creations est maintenant en ligne",
             "You can now order directly from this site. Every piece is designed and hand crafted in Montreal.",
             "Vous pouvez maintenant commander directement sur ce site. Chaque pi\u00e8ce est con\u00e7ue et faite \u00e0 la main \u00e0 Montr\u00e9al."))
        conn.execute(
            "INSERT INTO announcements (id, created, title, title_fr, body, body_fr) VALUES (?,?,?,?,?,?)",
            ("seed2", "2026-10-18T09:00:00",
             "Ordering direct",
             "Commander directement",
             "Our Etsy shop is temporarily under review, so all ordering happens right here for now. Same products, same maker, direct from the workshop.",
             "Notre boutique Etsy est temporairement en r\u00e9vision, donc toutes les commandes passent par ici pour le moment. M\u00eames produits, m\u00eame fabricant, directement de l'atelier."))
    if conn.execute("SELECT COUNT(*) FROM wip_projects").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO wip_projects (id, project, project_fr, status, status_fr, photo, sort, created) VALUES (?,?,?,?,?,?,?,?)",
            ("clock", "Mechanical Regulator Clock", "Horloge mécanique à régulateur",
             "In development", "En développement", "", 1, now_iso()))
        conn.execute(
            "INSERT INTO wip_updates (id, project_id, created, text, text_fr) VALUES (?,?,?,?,?)",
            ("c1", "clock", "2026-10-16T12:00:00",
             "Case design v4 complete: arched printed case with raised-numeral two-colour dials, deadbeat escapement, 135:1 going train and 12:1 hour motion work.",
             "Boîtier v4 terminé : boîtier imprimé en arche avec cadrans bicolores à chiffres en relief, échappement à chevilles, rouage de 135:1 et minuterie de 12:1."))
        conn.execute(
            "INSERT INTO wip_updates (id, project_id, created, text, text_fr) VALUES (?,?,?,?,?)",
            ("c2", "clock", "2026-10-18T09:00:00",
             "Fit test next: verifying the going train meshes cleanly before the full kit print. Spring torque still to be validated.",
             "Prochaine étape, le test d'ajustement : vérifier que le rouage s'engrène proprement avant d'imprimer le kit complet. Le couple du ressort reste à valider."))
        conn.execute(
            "INSERT INTO wip_projects (id, project, project_fr, status, status_fr, photo, sort, created) VALUES (?,?,?,?,?,?,?,?)",
            ("bust", "Saint Frere Andre Collector's Edition Bust",
             "Buste de saint Frère André, édition collectionneur",
             "Complete", "Terminé", "/img/work/bust-front.jpg", 2, now_iso()))
        conn.execute(
            "INSERT INTO wip_updates (id, project_id, created, text, text_fr) VALUES (?,?,?,?,?)",
            ("b1", "bust", "2026-10-18T09:00:00",
             "Finished. 1 of 1. 39 cm on a dark stained wood base with a brass Fr. Andre name plate. Listed in the shop.",
             "Terminé. Pièce unique. 39 cm sur un socle en bois teinté foncé avec une plaque de laiton au nom du Fr. André. En vente dans la boutique."))
    conn.commit()
    conn.close()


# ---------- shared HTML shell (mirrors static pages) ----------
FONT_LINK = ("<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">"
             "<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>"
             "<link href=\"https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700"
             "&family=Inter:wght@400;500;600;700&display=swap\" rel=\"stylesheet\">")

NAV_LINKS = [("work", "nav_work", "/work.html"), ("shop", "nav_shop", "/shop.html"),
             ("engraving", "nav_engraving", "/engraving.html"),
             ("portraits", "nav_portraits", "/portraits.html"),
             ("progress", "nav_progress", "/progress.html"),
             ("reviews", "nav_reviews", "/reviews.html"),
             ("suggest", "nav_suggest", "/suggest.html"),
             ("about", "nav_about", "/about.html"), ("contact", "nav_contact", "/contact.html")]


def t(lang, key):
    return STR.get(lang, STR["fr"]).get(key, STR["en"].get(key, key))


def dept_label(d, lang):
    labels = DEPT_LABELS_FR if lang == "fr" else DEPT_LABELS
    return labels.get(d, d)


def shell(title, description, body, active="", og_image="", og_url="", lang="fr"):
    s = STR["fr"] if lang != "en" else STR["en"]
    nav = "".join(
        f'<a href="{u}" class="{"active" if k == active else ""}">{s[k2]}</a>'
        for k, k2, u in NAV_LINKS)
    other = "en" if lang == "fr" else "fr"
    # Point all share-preview URLs at the canonical domain, whatever SITE_URL says.
    for old in OLD_HOSTS_URLS:
        og_url = og_url.replace(old, CANONICAL_URL)
        og_image = og_image.replace(old, CANONICAL_URL)
    og = ""
    if og_image:
        og = (f'<meta property="og:title" content="{h(title)}">'
              f'<meta property="og:description" content="{h(description)}">'
              f'<meta property="og:type" content="website">'
              f'<meta property="og:url" content="{h(og_url)}">'
              f'<meta property="og:image" content="{h(og_image)}">'
              '<meta name="twitter:card" content="summary_large_image">')
    canonical = CANONICAL_URL + request.path
    office = OFFICE_FR if lang == "fr" else OFFICE_EN
    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{h(title)} | ADN Creations</title>
<meta name="description" content="{h(description)}">
{FONT_LINK}
<link rel="icon" href="/icon.png" type="image/png">
<link rel="apple-touch-icon" href="/icon.png">
<link rel="stylesheet" href="/style.css">
<link rel="canonical" href="{canonical}">
{og}
</head>
<body>
<header class="site-header"><div class="wrap header-inner">
<a class="brand" href="/">ADN <span>Creations</span></a>
<nav class="nav-links" id="navLinks">{nav}<a href="/shop.html" class="nav-cta">{s["nav_cta"]}</a></nav>
<div class="lang-toggle" role="group" aria-label="Language / Langue">
<a href="?lang=fr" class="{"on" if lang == "fr" else ""}">FR</a><a href="?lang=en" class="{"on" if lang == "en" else ""}">EN</a>
</div>
<button class="hamburger" id="navToggle" aria-label="{s["menu"]}">&#9776;</button>
</div></header>
{body}
<footer class="site-footer"><div class="wrap footer-inner">
<div class="footer-grid">
<div>
<div class="footer-brand">ADN <span>Creations</span></div>
<p class="small" style="color:#B9AE97">{s["footer_tag"]}</p>
<a class="social-btn" href="{FB_PAGE_URL}" target="_blank" rel="noopener">{s["follow_ms"]}</a>
</div>
<div><h4>{s["footer_explore"]}</h4><ul class="footer-links">
<li><a href="/work.html">{s["nav_work"]}</a></li><li><a href="/shop.html">{s["nav_shop"]}</a></li>
<li><a href="/engraving.html">{s["nav_engraving"]}</a></li><li><a href="/portraits.html">{s["nav_portraits"]}</a></li>
<li><a href="/progress.html">{s["nav_progress"]}</a></li><li><a href="/suggest.html">{s["nav_suggest"]}</a></li><li><a href="/about.html">{s["nav_about"]}</a></li>
<li><a href="/contact.html">{s["nav_contact"]}</a></li>
</ul></div>
<div><h4>{s["footer_contact"]}</h4><ul class="footer-links">
<li><a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></li>
<li>{office}</li><li>NEQ 2281797763</li>
</ul></div>
</div>
<div class="footer-bottom"><span>&copy; 2026 ADN Creations. {s["footer_rights"]}</span><span>{s["footer_made"]}</span></div>
</div></footer>
<script>document.getElementById('navToggle').addEventListener('click',function(){{document.getElementById('navLinks').classList.toggle('open')}});</script>
</body>
</html>"""
    return html


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


def product_photos(pid):
    """Ordered gallery items: photos first (scale shot last), then videos."""
    conn = db()
    rows = conn.execute(
        "SELECT photo, is_scale, kind FROM product_photos WHERE product_id=? "
        "ORDER BY is_scale ASC, kind ASC, sort ASC", (pid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def lang_response(html, lang):
    """Wrap HTML in a response, persisting ?lang= to the adn_lang cookie."""
    resp = app.make_response(html)
    if (request.args.get("lang") or "").strip().lower() in ("fr", "en"):
        resp.set_cookie("adn_lang", lang, max_age=31536000, path="/")
    return resp


def pick(row, lang, field):
    """Localized DB field with English fallback."""
    if lang == "fr":
        v = (row[field + "_fr"] or "").strip()
        if v:
            return v
    return row[field] or ""


def product_badges(p, lang="fr"):
    out = []
    if p["preorder"]:
        out.append(f'<span class="badge badge-preorder">{t(lang, "preorder_badge")}</span>')
    if p["in_works"]:
        out.append(f'<span class="badge badge-stock">{t(lang, "in_works_badge")}</span>')
    if p["stock"] is not None and p["stock"] <= 3 and p["purchasable"] and not p["in_works"]:
        out.append(f'<span class="badge badge-stock">{t(lang, "only_left").format(n=p["stock"])}</span>')
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


def stars_html(rating):
    """5-star display, e.g. 4 -> ****-style using star glyphs."""
    rating = max(1, min(5, int(rating or 5)))
    return "\u2605" * rating + "\u2606" * (5 - rating)


def reviews_section(pid, lang):
    conn = db()
    rows = conn.execute(
        "SELECT name, rating, text, created FROM reviews "
        "WHERE product_id=? AND approved=1 ORDER BY created DESC", (pid,)).fetchall()
    conn.close()
    n = len(rows)
    avg = round(sum(r["rating"] for r in rows) / n, 1) if n else 0
    if n:
        items = "".join(
            '<div class="review"><div class="review-stars">' + stars_html(r["rating"]) +
            '</div><p>' + h(r["text"]) + '</p>' +
            '<p class="small muted">\u2014 ' + h(r["name"]) + '</p></div>'
            for r in rows)
        summary = ('<p class="review-avg">' + stars_html(round(avg)) +
                   ' <span class="muted">' + str(avg) + ' / 5 \u00b7 ' + str(n) + '</span></p>')
    else:
        items = '<p class="muted">' + t(lang, "reviews_empty") + '</p>'
        summary = ""
    return ("""
<section class="section-sm" id="reviews"><h2>""" + t(lang, "reviews_title") + """</h2>
""" + summary + """
<div class="review-list">""" + items + """</div>
<p style="margin-top:12px"><a href="/reviews.html">""" + t(lang, "reviews_see_all") + """</a></p>
<h3 style="margin-top:24px">""" + t(lang, "review_write") + """</h3>
<form id="reviewForm">
<div class="field"><label for="rv-name">""" + t(lang, "review_name") + """</label>
<input type="text" id="rv-name" maxlength="80" required></div>
<div class="field"><label for="rv-rating">""" + t(lang, "review_rating") + """</label>
<select id="rv-rating">
<option value="5">""" + stars_html(5) + """</option><option value="4">""" + stars_html(4) + """</option>
<option value="3">""" + stars_html(3) + """</option><option value="2">""" + stars_html(2) + """</option>
<option value="1">""" + stars_html(1) + """</option></select></div>
<div class="field"><label for="rv-text">""" + t(lang, "review_text") + """</label>
<textarea id="rv-text" maxlength="2000" required></textarea></div>
<button class="btn btn-outline" type="submit">""" + t(lang, "review_submit") + """</button>
<div id="rv-msg" style="margin-top:10px"></div>
</form></section>
<script>
document.getElementById('reviewForm').addEventListener('submit', async function(e){
  e.preventDefault();
  var msg = document.getElementById('rv-msg');
  var payload = { product_id: """ + json.dumps(pid) + """,
    name: document.getElementById('rv-name').value.trim(),
    rating: parseInt(document.getElementById('rv-rating').value, 10) || 5,
    text: document.getElementById('rv-text').value.trim(),
    lang: """ + json.dumps(lang) + """ };
  if (!payload.name || !payload.text) {
    msg.innerHTML = '<div class="notice notice-err">' + """ + json.dumps(t(lang, "review_err")) + """ + '</div>';
    return;
  }
  var r = await fetch('/api/reviews', { method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
  if (r.ok) {
    msg.innerHTML = '<div class="notice notice-ok">' + """ + json.dumps(t(lang, "review_thanks")) + """ + '</div>';
    document.getElementById('rv-name').value = '';
    document.getElementById('rv-text').value = '';
  } else {
    msg.innerHTML = '<div class="notice notice-err">' + """ + json.dumps(t(lang, "review_err")) + """ + '</div>';
  }
});
</script>""")


@app.route("/reviews.html")
def reviews_page():
    lang = get_lang()
    track_visit("/reviews.html")
    conn = db()
    rows = conn.execute(
        "SELECT r.product_id, r.name, r.rating, r.text, r.created, "
        "p.name as product_name, p.name_fr as product_name_fr "
        "FROM reviews r LEFT JOIN products p ON p.id=r.product_id "
        "WHERE r.approved=1 ORDER BY r.created DESC LIMIT 100").fetchall()
    conn.close()
    if rows:
        items = "".join(
            '<div class="review"><div class="review-stars">' + stars_html(r["rating"]) + '</div>'
            '<p>' + h(r["text"]) + '</p>'
            '<p class="small muted">\u2014 ' + h(r["name"]) +
            ' · <a href="/product/' + h(r["product_id"]) + '">' +
            h(r["product_name_fr"] if lang == "fr" and r["product_name_fr"] else (r["product_name"] or "")) +
            '</a></p></div>'
            for r in rows)
    else:
        items = '<p class="muted">' + t(lang, "reviews_empty") + '</p>'
    body = ('<div class="wrap section"><p class="kicker">ADN Creations</p>'
            '<h1>' + t(lang, "reviews_title") + '</h1>'
            '<p class="lede">' + t(lang, "reviews_page_sub") + '</p>'
            '<div class="review-list" style="margin-top:24px">' + items + '</div></div>')
    return lang_response(shell(t(lang, "reviews_title"), t(lang, "reviews_page_sub"),
                               body, active="reviews",
                               og_url=CANONICAL_URL + "/reviews.html", lang=lang), lang)


@app.route("/product/<pid>")
def product_page(pid):
    lang = get_lang()
    p = get_product(pid)
    if not p:
        abort(404)
    track_visit(f"/product/{pid}")
    track_product_view(pid)
    name = pick(p, lang, "name")
    desc = pick(p, lang, "description")
    story = pick(p, lang, "story")
    depts = json.loads(p["depts"] or "[]")
    tags = " ".join(f'<span class="dept-tag">{dept_label(d, lang)}</span>' for d in depts)

    # Gallery: ordered photos (scale shot last), then videos.
    photos = product_photos(pid)
    if not photos and p["photo"]:
        photos = [{"photo": p["photo"], "is_scale": 0, "kind": "photo"}]
    if photos:
        items = [{"src": ph["photo"], "kind": ph.get("kind") or "photo"} for ph in photos]
        items_json = json.dumps(items)
        name_json = json.dumps(name)
        thumbs = "".join(
            '<button type="button" class="gal-thumb' + (" on" if i == 0 else "") + '" data-i="' + str(i) + '">'
            + ('<span class="gal-vidbadge">&#9654;</span>' if it["kind"] == "video" else "")
            + ('<video src="' + h(it["src"]) + '" muted preload="metadata" playsinline></video>'
               if it["kind"] == "video"
               else '<img src="' + h(it["src"]) + '" alt="' + h(name) + '" loading="lazy">')
            + "</button>"
            for i, it in enumerate(items))
        scale_cap = ""
        if any(ph["is_scale"] for ph in photos):
            scale_cap = f'<p class="small muted" style="margin-top:6px">{t(lang, "scale_caption")}</p>'
        first = items[0]
        if first["kind"] == "video":
            main_html = ('<video src="' + h(first["src"]) + '" controls playsinline '
                         'preload="metadata" style="width:100%;display:block"></video>')
        else:
            main_html = '<img src="' + h(first["src"]) + '" alt="' + h(name) + '">'
        gallery = ('<div class="product-gallery"><div id="galMainWrap">' + main_html + "</div>"
                   '<div class="gal-thumbs">' + thumbs + "</div>" + scale_cap + "</div>")
        gal_js = (
            "<script>"
            "var GAL_ITEMS=" + items_json + ";"
            "var GAL_NAME=" + name_json + ";"
            "var galWrap=document.getElementById('galMainWrap');"
            "function galShow(i){var it=GAL_ITEMS[i];"
            "if(it.kind==='video'){"
            "galWrap.innerHTML='<video src=\"'+it.src+'\" controls playsinline preload=\"metadata\" style=\"width:100%;display:block\"></video>';"
            "}else{"
            "var im=document.createElement('img');im.src=it.src;im.alt=GAL_NAME;"
            "galWrap.innerHTML='';galWrap.appendChild(im);"
            "}"
            "var ts=document.querySelectorAll('.gal-thumb');"
            "ts.forEach(function(x){x.classList.remove('on')});"
            "ts[i].classList.add('on');}"
            "document.querySelectorAll('.gal-thumb').forEach(function(b){"
            "b.addEventListener('click',function(){galShow(parseInt(b.getAttribute('data-i'),10));});"
            "});"
            "</script>"
        )
    else:
        gallery = f'<div class="product-gallery"><div class="photo-placeholder">{t(lang, "photo_soon")}</div></div>'
        gal_js = ""

    engraving_field = ""
    if p["engravable"]:
        engraving_field = (f'<div class="field"><label for="engraving">{t(lang, "engraving_label")}</label>'
                           f'<input type="text" id="engraving" maxlength="120" '
                           f'placeholder="{h(t(lang, "engraving_ph"))}"></div>')
    option_field = ""
    if p["id"] == "custom-lighter":
        _des_opts = "".join(f'<option value="Design {i}">Design {i}</option>' for i in range(1, 13))
        _thumbs = "".join(
            f'<img src="/img/designs/lighter-design-{i}.jpg" data-d="{i}" alt="Design {i}" loading="lazy">'
            for i in range(1, 13))
        option_field = (
            f'<div class="field"><label>{t(lang, "design_title")}</label>'
            f'<div class="design-mode"><label><input type="radio" name="designmode" value="gallery" checked> '
            f'{t(lang, "design_gallery")}</label> '
            f'<label><input type="radio" name="designmode" value="upload"> {t(lang, "design_upload")}</label></div>'
            f'<div id="designGalleryPick"><select id="designSelect">{_des_opts}</select>'
            f'<div class="design-preview"><img id="designPreview" src="/img/designs/lighter-design-1.jpg" '
            f'alt="Design 1"></div><div class="design-thumbs">{_thumbs}</div></div>'
            f'<div id="designUploadPick" style="display:none">'
            f'<input type="file" id="designFile" accept="image/*">'
            f'<input type="hidden" id="designUploadId" value="">'
            f'<span id="designUploadMsg" class="small muted"></span></div></div>')
    elif p["id"] in ("mini-bust-small", "mini-bust-large"):
        option_field = (
            f'<div class="field"><label for="saintSelect">{t(lang, "saint_title")}</label>'
            f'<select id="saintSelect"><option value="Saint Fr\u00e8re Andr\u00e9">Saint Fr\u00e8re Andr\u00e9</option>'
            f'<option value="Carlo Acutis">Carlo Acutis</option></select></div>')
    design_js = ""
    if p["id"] == "custom-lighter":
        design_js = """<script>
(function(){
  var sel = document.getElementById('designSelect'), prev = document.getElementById('designPreview');
  function pick(i){ if(sel) sel.value = 'Design ' + i;
    if(prev){ prev.src = '/img/designs/lighter-design-' + i + '.jpg'; prev.alt = 'Design ' + i; }
    document.querySelectorAll('.design-thumbs img').forEach(function(t){
      t.classList.toggle('on', t.getAttribute('data-d') == String(i)); }); }
  if(sel) sel.addEventListener('change', function(){ pick(sel.value.replace('Design ', '')); });
  document.querySelectorAll('.design-thumbs img').forEach(function(t){
    t.addEventListener('click', function(){ pick(t.getAttribute('data-d')); }); });
  document.querySelectorAll('input[name="designmode"]').forEach(function(r){
    r.addEventListener('change', function(){
      var gal = r.value === 'gallery';
      document.getElementById('designGalleryPick').style.display = gal ? '' : 'none';
      document.getElementById('designUploadPick').style.display = gal ? 'none' : ''; }); });
  var fi = document.getElementById('designFile'), msg = document.getElementById('designUploadMsg');
  if(fi) fi.addEventListener('change', async function(){
    if(!fi.files.length) return;
    msg.textContent = '…'; msg.style.color = '';
    var fd = new FormData(); fd.append('file', fi.files[0]);
    try {
      var r = await fetch('/api/design-upload', {method: 'POST', body: fd});
      var j = await r.json();
      if(j.file){ document.getElementById('designUploadId').value = j.file;
        msg.textContent = '✓'; msg.style.color = 'green'; }
      else { msg.textContent = (j.error || 'upload failed'); msg.style.color = 'red'; }
    } catch(e){ msg.textContent = 'upload failed'; msg.style.color = 'red'; }
  });
})();
</script>"""
    preorder_note = ""
    if p["preorder"]:
        preorder_note = (f'<div class="preorder-note">{t(lang, "preorder_note").format(date=h(p["preorder_ship_date"] or ("bientôt" if lang == "fr" else "soon")))}</div>')
    tier_note = ""
    if p["additional_price_cents"]:
        tier_note = (f'<p class="small muted">{t(lang, "tier_note").format(first=money(p["price_cents"]), extra=money(p["additional_price_cents"]))}</p>')

    buy_html = ""
    if p["in_works"]:
        buy_html = (f'<a class="btn btn-outline btn-block" href="/progress.html?lang={lang}" style="margin-top:10px">{t(lang, "follow_build")}</a>'
                    f'<div class="field" style="margin-top:14px"><label for="notifyEmail">{t(lang, "notify_me_label")}</label>'
                    f'<div style="display:flex;gap:8px"><input type="email" id="notifyEmail" placeholder="{h(t(lang, "notify_me_ph"))}" style="flex:1">'
                    f'<button class="btn btn-brass" id="notifyBtn" type="button">{t(lang, "notify_me_btn")}</button></div></div>'
                    '<div id="notifyMsg" style="margin-top:8px"></div>')
    elif p["purchasable"]:
        if p["stock"] is not None and p["stock"] <= 0:
            buy_html = f'<div class="notice notice-err">{t(lang, "sold_out")}</div>'
        else:
            label = t(lang, "preorder_now") if p["preorder"] else t(lang, "buy_now")
            buy_html = (f'<button class="btn btn-brass btn-block" id="buyBtn">{label} &middot; {money(p["price_cents"])}</button>'
                        f'<p class="small muted" style="margin-top:10px">{t(lang, "secure_checkout")}</p>')
    else:
        buy_html = f'<div class="notice">{t(lang, "coming_soon")}</div>'
    custom = ""
    if p["custom_link"]:
        custom = f'<a class="btn btn-outline btn-block" href="{h(p["custom_link"])}" style="margin-top:10px">{t(lang, "design_yours")}</a>'

    story_html = ""
    if story:
        story_html = (f'<section class="section-sm"><h2>{t(lang, "story_title")}</h2>'
                      f'<div style="max-width:680px"><p class="lede">{h(story)}</p></div></section>')

    buy_js = ""
    if p["purchasable"] and not p["in_works"] and not (p["stock"] is not None and p["stock"] <= 0):
        buy_js = f"""<script>
document.getElementById('buyBtn') && document.getElementById('buyBtn').addEventListener('click', async function() {{
  var btn = this; btn.disabled = true; btn.textContent = {json.dumps(t(lang, "preparing"))};
  var payload = {{ product_id: {json.dumps(p["id"])}, qty: parseInt(document.getElementById('qty').value) || 1, lang: {json.dumps(lang)} }};
  var eng = document.getElementById('engraving');
  if (eng) payload.engraving_text = eng.value;
  var dmode = document.querySelector('input[name="designmode"]:checked');
  if (dmode) {{
    if (dmode.value === 'gallery') {{
      var ds = document.getElementById('designSelect');
      if (ds) payload.design = ds.value;
    }} else {{
      var du = document.getElementById('designUploadId');
      if (du && du.value) payload.design = 'Custom upload ' + du.value;
    }}
  }}
  var ss = document.getElementById('saintSelect');
  if (ss) payload.saint = ss.value;
  var cp = document.getElementById('coupon');
  if (cp && cp.value.trim()) payload.coupon = cp.value.trim();
  try {{
    var r = await fetch('/api/checkout', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(payload) }});
    var j = await r.json();
    if (j.url) window.location = j.url;
    else {{ document.getElementById('buyMsg').innerHTML = '<div class="notice notice-err">' + (j.error || {json.dumps(t(lang, "checkout_failed"))}) + '</div>'; btn.disabled = false; }}
  }} catch(e) {{ document.getElementById('buyMsg').innerHTML = '<div class="notice notice-err">' + {json.dumps(t(lang, "checkout_failed"))} + '</div>'; btn.disabled = false; }}
}});
(function(){{  /* live tier-price total as quantity changes */
  var qtyEl = document.getElementById('qty'), btn = document.getElementById('buyBtn'),
      priceEl = document.getElementById('priceTotal'), cpEl = document.getElementById('coupon'),
      cpMsg = document.getElementById('couponMsg');
  if (!qtyEl || !btn) return;
  var priceCents = {p["price_cents"]}, addCents = {p["additional_price_cents"] or 0};
  var baseLabel = {json.dumps(label)};
  var pctOff = 0;
  var okTpl = {json.dumps(t(lang, "coupon_ok"))}, badTxt = {json.dumps(t(lang, "coupon_bad"))};
  function money(c){{ return "$" + (c/100).toFixed(2); }}
  function total(q){{
    var t;
    if (addCents && q > 1) {{
      var packs = Math.floor(q/4), rest = q % 4;
      t = packs * 9999;
      if (rest) t += priceCents + (rest-1) * addCents;
    }} else {{
      t = priceCents * q;
    }}
    if (pctOff) t = t - Math.round(t * pctOff / 100);
    return t;
  }}
  function refresh(){{
    var q = Math.max(1, Math.min(10, parseInt(qtyEl.value, 10) || 1));
    var t = money(total(q));
    btn.innerHTML = baseLabel + ' &middot; ' + t;
    if (priceEl) priceEl.textContent = t;
  }}
  qtyEl.addEventListener('input', refresh);
  qtyEl.addEventListener('change', refresh);
  var cpTimer = null;
  function checkCoupon(){{
    var code = cpEl.value.trim().toUpperCase();
    if (!code) {{ pctOff = 0; cpMsg.textContent = ""; refresh(); return; }}
    fetch('/api/coupons/validate?code=' + encodeURIComponent(code)).then(function(r){{ return r.json(); }}).then(function(j){{
      if (j.ok) {{
        pctOff = j.percent_off;
        cpMsg.textContent = okTpl.replace("{{pct}}", j.percent_off);
        cpMsg.style.color = "green";
      }} else {{
        pctOff = 0;
        cpMsg.textContent = badTxt;
        cpMsg.style.color = "#A33232";
      }}
      refresh();
    }}).catch(function(){{ pctOff = 0; refresh(); }});
  }}
  if (cpEl) cpEl.addEventListener('input', function(){{ clearTimeout(cpTimer); cpTimer = setTimeout(checkCoupon, 500); }});
  refresh();
}})();
</script>"""
    notify_js = ""
    if p["in_works"]:
        notify_js = f"""<script>
document.getElementById('notifyBtn').addEventListener('click', async function() {{
  var em = document.getElementById('notifyEmail').value.trim();
  var msg = document.getElementById('notifyMsg');
  if (!/^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/.test(em)) {{
    msg.innerHTML = '<div class="notice notice-err">' + {json.dumps(t(lang, "email_invalid"))} + '</div>'; return;
  }}
  var r = await fetch('/api/notify-me', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ product_id: {json.dumps(p["id"])}, email: em, lang: {json.dumps(lang)} }}) }});
  if (r.ok) msg.innerHTML = '<div class="notice notice-ok">' + {json.dumps(t(lang, "notify_ok"))} + '</div>';
  else msg.innerHTML = '<div class="notice notice-err">' + {json.dumps(t(lang, "checkout_failed"))} + '</div>';
}});
</script>"""
    body = f"""
<div class="wrap"><div class="product-detail">
<div>{gallery}</div>
<div>
<div class="buy-box">
<p class="kicker">ADN Creations</p>
<h1 style="font-size:2rem">{h(name)}</h1>
<div class="dept-tags" style="margin-bottom:12px">{tags} {product_badges(p, lang)}</div>
<p class="price" id="priceTotal">{money(p["price_cents"])}</p>
<p class="muted">{h(desc)}</p>
{tier_note}
{preorder_note}
<div class="field"><label for="qty">{t(lang, "qty")}</label>
<input type="number" id="qty" value="1" min="1" max="10"></div>
<div class="field"><label for="coupon">{t(lang, "coupon_label")}</label>
<input type="text" id="coupon" maxlength="32" placeholder="{h(t(lang, "coupon_ph"))}" style="text-transform:uppercase">
<div id="couponMsg" class="small" style="margin-top:6px"></div></div>
{engraving_field}
{option_field}
{buy_html}{custom}
<div id="buyMsg" style="margin-top:12px"></div>
</div>
</div>
</div>
{story_html}
{reviews_section(pid, lang)}
</div>
{gal_js}{buy_js}{design_js}{notify_js}"""
    html = shell(name, desc[:160], body, active="shop",
                 og_image=abs_url(photos[0]["photo"] if photos else p["photo"]),
                 og_url=f"{SITE_URL}/product/{pid}", lang=lang)
    return lang_response(html, lang)


@app.route("/announcement/<aid>")
def announcement_page(aid):
    lang = get_lang()
    conn = db()
    a = conn.execute("SELECT * FROM announcements WHERE id=?", (aid,)).fetchone()
    conn.close()
    if not a:
        abort(404)
    track_visit(f"/announcement/{aid}")
    title = pick(a, lang, "title")
    body_text = pick(a, lang, "body")
    try:
        if lang == "fr":
            months = ["", "janvier", "février", "mars", "avril", "mai", "juin",
                      "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
            dt0 = datetime.fromisoformat(a["created"])
            dt = f"{dt0.day} {months[dt0.month]} {dt0.year}"
        else:
            dt = datetime.fromisoformat(a["created"]).strftime("%B %d, %Y")
    except (ValueError, IndexError):
        dt = a["created"][:10]
    body = f"""
<div class="wrap section"><div style="max-width:680px">
<p class="kicker"><a href="/progress.html" style="text-decoration:none">{t(lang, "announce_back")}</a></p>
<p class="feed-date">{h(dt)}</p>
<h1>{h(title)}</h1>
<p class="lede">{h(body_text)}</p>
</div></div>"""
    html = shell(title, body_text[:160], body, active="progress",
                 og_image=abs_url("/img/products/carlo-lamp.jpg"),
                 og_url=f"{SITE_URL}/announcement/{aid}", lang=lang)
    return lang_response(html, lang)


# ---------- public APIs ----------
@app.route("/api/products")
def api_products():
    dept = (request.args.get("dept") or "").strip()
    conn = db()
    rows = conn.execute("SELECT * FROM products WHERE active=1 ORDER BY sort, name").fetchall()
    photos_by = {}
    for ph in conn.execute(
            "SELECT product_id, photo, is_scale, kind FROM product_photos ORDER BY is_scale ASC, kind ASC, sort ASC").fetchall():
        photos_by.setdefault(ph["product_id"], []).append(
            {"photo": ph["photo"], "is_scale": bool(ph["is_scale"]),
             "kind": ph["kind"] or "photo"})
    conn.close()
    out = []
    for p in rows:
        depts = json.loads(p["depts"] or "[]")
        if dept and dept not in depts:
            continue
        d = dict(p)
        d["price"] = money(p["price_cents"])
        d["depts"] = depts
        d["photos"] = photos_by.get(p["id"], [])
        for k in ("preorder", "engravable", "purchasable", "in_works"):
            d[k] = bool(d[k])
        out.append(d)
    return jsonify({"products": out, "depts": DEPT_LABELS, "depts_fr": DEPT_LABELS_FR})


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


def get_coupon(code):
    """Return (percent_off, code) for a valid active coupon, else (0, '')."""
    code = (code or "").strip().upper()[:32]
    if not code:
        return 0, ""
    conn = db()
    row = conn.execute(
        "SELECT percent_off FROM coupons WHERE code=? AND active=1", (code,)).fetchone()
    conn.close()
    if not row:
        return 0, ""
    return max(0, min(90, int(row["percent_off"] or 0))), code


@app.route("/api/coupons/validate", methods=["GET"])
def api_coupon_validate():
    pct, code = get_coupon(request.args.get("code"))
    if not pct:
        return jsonify({"ok": False})
    return jsonify({"ok": True, "code": code, "percent_off": pct})


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    data = request.get_json(force=True)
    lang = (data.get("lang") or "").strip().lower()
    if lang not in ("fr", "en"):
        lang = "fr"
    pid = (data.get("product_id") or "").strip()
    qty = max(1, min(10, int(data.get("qty") or 1)))
    engraving = (data.get("engraving_text") or "").strip()[:200]
    design = (data.get("design") or "").strip()[:60]
    saint = (data.get("saint") or "").strip()[:40]
    _parts = []
    if design:
        _parts.append(design)
    if saint:
        _parts.append("Saint: " + saint)
    if engraving:
        _parts.append("Text: " + engraving)
    if _parts:
        engraving = "; ".join(_parts)[:200]
    p = get_product(pid)
    if not p or not p["purchasable"] or p["in_works"]:
        return jsonify({"error": t(lang, "err_unknown_product")}), 404
    if p["stock"] is not None and p["stock"] < qty:
        return jsonify({"error": t(lang, "err_stock")}), 400
    # Tiered pricing (memorial lamps: $39.99 first, $29.99 per extra copy,
    # $99.99 per 4-pack of the same design). 4-packs always win when they fit.
    if p["additional_price_cents"] and qty > 1:
        packs, rest = divmod(qty, 4)
        amount = packs * LAMP_PACK4
        if rest:
            amount += p["price_cents"] + (rest - 1) * p["additional_price_cents"]
    else:
        amount = p["price_cents"] * qty
    # Discount coupon (percent off the total, e.g. creator codes).
    pct_off, coupon_code = get_coupon(data.get("coupon"))
    if pct_off:
        amount = amount - round(amount * pct_off / 100)
    name = pick(p, lang, "name")
    oid = "ord_" + uuid.uuid4().hex[:12]
    conn = db()
    conn.execute(
        "INSERT INTO orders (id, created, product_id, product_name, amount_cents, qty, "
        "engraving_text, preorder, preorder_ship_date, paid, coupon) VALUES (?,?,?,?,?,?,?,?,?,0,?)",
        (oid, now_iso(), pid, name, amount, qty, engraving,
         p["preorder"], p["preorder_ship_date"], coupon_code))
    conn.commit()
    conn.close()
    label = name + (f" x{qty}" if qty > 1 else "")
    if coupon_code:
        label += f" ({coupon_code} -{pct_off}%)"
    if p["preorder"]:
        label = ("PRÉCOMMANDE : " if lang == "fr" else "PREORDER: ") + label
    if engraving:
        label += f" (engraving: {engraving[:60]})"
    if not STRIPE_SECRET:
        if DEMO_MODE:
            mark_order_paid(oid, "")
            return jsonify({"url": f"{SITE_URL}/thank-you.html?order={oid}", "demo": True})
        return jsonify({"error": t(lang, "err_payment")}), 503
    import stripe
    stripe.api_key = STRIPE_SECRET
    ship_label = ("Expédition à taux fixe (CA/US)" if lang == "fr"
                  else "Flat-rate shipping (CA/US)")
    sess = stripe.checkout.Session.create(
        payment_method_types=["card"],
        locale="fr" if lang == "fr" else "en",
        line_items=[{"price_data": {
            "currency": "cad", "unit_amount": amount,
            "product_data": {"name": label}}, "quantity": 1}],
        mode="payment",
        shipping_address_collection={"allowed_countries": ["CA", "US"]},
        shipping_options=[{"shipping_rate_data": {
            "type": "fixed_amount",
            "fixed_amount": {"amount": 1000, "currency": "cad"},
            "display_name": ship_label}}],
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


def _fmt_address(addr):
    """Format a Stripe address dict as a few plain-text lines."""
    if not addr:
        return ""
    city_state = ", ".join(p for p in [addr.get("city"), addr.get("state")] if p)
    zip_country = " ".join(p for p in [addr.get("postal_code"), addr.get("country")] if p)
    parts = [addr.get("line1"), addr.get("line2"), city_state, zip_country]
    return "\n".join(p for p in parts if p)


def mark_order_paid(oid, email="", customer_name="", ship_name="", ship_address=""):
    conn = db()
    conn.execute(
        "UPDATE orders SET paid=1, email=?, customer_name=?, ship_name=?, ship_address=? "
        "WHERE id=?",
        (email, customer_name, ship_name, ship_address, oid))
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
    lang = (data.get("lang") or "").strip().lower()
    if lang not in ("fr", "en"):
        lang = "fr"
    name = (data.get("name") or "").strip()[:120]
    email = (data.get("email") or "").strip()[:160]
    product = (data.get("product") or "").strip()[:120]
    message = (data.get("message") or "").strip()[:2000]
    if not name or not message or "@" not in email:
        return jsonify({"error": t(lang, "err_request")}), 400
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


@app.route("/api/portrait-idea", methods=["POST"])
def api_portrait_idea():
    data = request.get_json(force=True)
    lang = (data.get("lang") or "").strip().lower()
    if lang not in ("fr", "en"):
        lang = "fr"
    name = (data.get("name") or "").strip()[:120]
    email = (data.get("email") or "").strip()[:160]
    idea = (data.get("idea") or "").strip()[:2000]
    if not name or not idea or "@" not in email:
        return jsonify({"error": t(lang, "err_request")}), 400
    rid = "por_" + uuid.uuid4().hex[:10]
    conn = db()
    conn.execute(
        "INSERT INTO portrait_ideas (id, created, name, email, idea) "
        "VALUES (?,?,?,?,?)", (rid, now_iso(), name, email, idea))
    conn.commit()
    conn.close()
    ok, _ = send_email(
        SUPPORT_EMAIL, f"New portrait idea from {name}",
        f"Name: {name}\nEmail: {email}\n\n{idea}\n")
    return jsonify({"ok": True, "emailed": ok})


@app.route("/api/notify-me", methods=["POST"])
def api_notify_me():
    data = request.get_json(force=True)
    lang = (data.get("lang") or "").strip().lower()
    if lang not in ("fr", "en"):
        lang = "fr"
    pid = (data.get("product_id") or "").strip()[:40]
    email = (data.get("email") or "").strip()[:160]
    if not pid or "@" not in email:
        return jsonify({"error": t(lang, "email_invalid")}), 400
    conn = db()
    exists = conn.execute(
        "SELECT id FROM notify_me WHERE product_id=? AND email=?", (pid, email)).fetchone()
    if not exists:
        conn.execute("INSERT INTO notify_me (id, created, product_id, email) VALUES (?,?,?,?)",
                     ("ntf_" + uuid.uuid4().hex[:10], now_iso(), pid, email))
        conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/reviews", methods=["GET"])
def api_reviews_list():
    """Public: approved reviews site-wide (or per product), newest first."""
    pid = (request.args.get("product_id") or "").strip()[:40]
    try:
        limit = max(1, min(50, int(request.args.get("limit") or 20)))
    except (TypeError, ValueError):
        limit = 20
    conn = db()
    if pid:
        rows = conn.execute(
            "SELECT r.name, r.rating, r.text, r.created, p.name as product_name "
            "FROM reviews r LEFT JOIN products p ON p.id=r.product_id "
            "WHERE r.product_id=? AND r.approved=1 ORDER BY r.created DESC LIMIT ?",
            (pid, limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT r.product_id, r.name, r.rating, r.text, r.created, p.name as product_name "
            "FROM reviews r LEFT JOIN products p ON p.id=r.product_id "
            "WHERE r.approved=1 ORDER BY r.created DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return jsonify({"reviews": [dict(r) for r in rows]})


@app.route("/api/reviews", methods=["POST"])
def api_reviews():
    data = request.get_json(force=True)
    lang = (data.get("lang") or "").strip().lower()
    if lang not in ("fr", "en"):
        lang = "fr"
    pid = (data.get("product_id") or "").strip()[:40]
    name = (data.get("name") or "").strip()[:80]
    text = (data.get("text") or "").strip()[:2000]
    try:
        rating = max(1, min(5, int(data.get("rating") or 5)))
    except (TypeError, ValueError):
        rating = 5
    if not pid or not name or not text or not get_product(pid):
        return jsonify({"error": t(lang, "review_err")}), 400
    conn = db()
    conn.execute(
        "INSERT INTO reviews (id, product_id, name, rating, text, approved, created) "
        "VALUES (?,?,?,?,?,0,?)",
        ("rv_" + uuid.uuid4().hex[:10], pid, name, rating, text, now_iso()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/reviews")
def admin_reviews():
    if not admin_ok():
        abort(403)
    conn = db()
    rows = conn.execute(
        "SELECT r.*, p.name as product_name FROM reviews r "
        "LEFT JOIN products p ON p.id=r.product_id "
        "ORDER BY r.approved ASC, r.created DESC LIMIT 300").fetchall()
    conn.close()
    return jsonify({"reviews": [dict(r) for r in rows]})


@app.route("/api/admin/reviews/<rid>/approve", methods=["POST"])
def admin_review_approve(rid):
    if not admin_ok():
        abort(403)
    conn = db()
    conn.execute("UPDATE reviews SET approved=1 WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/reviews/<rid>/delete", methods=["POST"])
def admin_review_delete(rid):
    if not admin_ok():
        abort(403)
    conn = db()
    conn.execute("DELETE FROM reviews WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/coupons", methods=["GET", "POST"])
def admin_coupons():
    if not admin_ok():
        abort(403)
    conn = db()
    if request.method == "POST":
        data = request.get_json(force=True)
        code = (data.get("code") or "").strip().upper()[:32]
        try:
            pct = max(1, min(90, int(data.get("percent_off") or 0)))
        except (TypeError, ValueError):
            return jsonify({"error": "bad percent"}), 400
        note = (data.get("note") or "").strip()[:160]
        if not code or not pct:
            return jsonify({"error": "code and percent required"}), 400
        conn.execute(
            "INSERT OR REPLACE INTO coupons (code, percent_off, active, note, created) "
            "VALUES (?,?,1,?,?)", (code, pct, note, now_iso()))
        conn.commit()
    rows = conn.execute("SELECT * FROM coupons ORDER BY created DESC").fetchall()
    conn.close()
    return jsonify({"coupons": [dict(r) for r in rows]})


@app.route("/api/admin/coupons/<code>", methods=["POST", "DELETE"])
def admin_coupon_one(code):
    if not admin_ok():
        abort(403)
    code = (code or "").strip().upper()[:32]
    conn = db()
    if request.method == "DELETE":
        conn.execute("DELETE FROM coupons WHERE code=?", (code,))
    else:
        data = request.get_json(force=True, silent=True) or {}
        active = 1 if data.get("active", True) else 0
        conn.execute("UPDATE coupons SET active=? WHERE code=?", (active, code))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------- custom 4-sided lamp designer ----------
# Pricing 2026-10-18: $39.99 for one custom lamp, $29.99 for each additional copy
# of the same design, 4-pack bundle $99.99.
GALLERY = {
    "solanus-casey": {"name": "Blessed Solanus Casey", "name_fr": "Bienheureux Solanus Casey", "image": "/lamps/gallery/solanus-casey.jpg"},
    "frere-andre": {"name": "Frere Andre", "name_fr": "Frère André", "image": "/lamps/gallery/bishop-example.jpg"},
    "padrepio-face": {"name": "Padre Pio", "name_fr": "Padre Pio", "image": "/lamps/gallery/padrepio-face.jpg"},
    "padrepio-mass": {"name": "Padre Pio at Mass", "name_fr": "Padre Pio à la messe", "image": "/lamps/gallery/padrepio-mass.jpg"},
    "ourlady-child": {"name": "Our Lady with Child", "name_fr": "Notre-Dame avec l'Enfant", "image": "/lamps/gallery/ourlady-child.jpg"},
    "carlo-standing": {"name": "Carlo Acutis, Standing", "name_fr": "Carlo Acutis, debout", "image": "/lamps/carlo-standing.jpg"},
    "carlo-monstrance": {"name": "Carlo Acutis with the Eucharist", "name_fr": "Carlo Acutis avec l'Eucharistie", "image": "/lamps/carlo-monstrance.jpg"},
    "our-lady": {"name": "Our Lady of the Rosary", "name_fr": "Notre-Dame du Rosaire", "image": "/lamps/our-lady.jpg"},
    "basilica-padrepio": {"name": "Basilica", "name_fr": "Basilique", "image": "/lamps/basilica-padrepio.jpg"},
}
LAMP_SINGLE = 3999   # $39.99 for one custom lamp
LAMP_PACK4 = 9999    # $99.99 for a 4-pack of the same design
LAMP_EXTRA = 2499    # $24.99 for each additional copy
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


@app.route("/api/design-upload", methods=["POST"])
def design_upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400
    name = "design_" + uuid.uuid4().hex[:10] + ".jpg"
    path = os.path.join(DESIGN_UPLOAD_DIR, name)
    try:
        img = load_upright(f.stream)
        img.thumbnail((1200, 1200), Image.LANCZOS)
        img.save(path, "JPEG", quality=88)
    except Exception:
        return jsonify({"error": "could not read that image"}), 400
    return jsonify({"file": name, "url": "/design_uploads/" + name})


@app.route("/api/gallery")
def api_gallery():
    return jsonify({"gallery": [{"id": k, "name": v["name"], "name_fr": v["name_fr"], "image": v["image"]} for k, v in GALLERY.items()],
                    "single_cents": LAMP_SINGLE, "pack4_cents": LAMP_PACK4, "extra_cents": LAMP_EXTRA})


def validate_sides(sides, lang="fr"):
    if not isinstance(sides, list) or len(sides) != 4:
        raise ValueError(t(lang, "err_sides"))
    clean, names = [], []
    for s in sides:
        kind = (s or {}).get("kind")
        if kind == "gallery":
            gid = s.get("id") or ""
            if gid not in GALLERY:
                raise ValueError(t(lang, "err_unknown_product"))
            clean.append({"kind": "gallery", "id": gid})
            names.append(GALLERY[gid]["name_fr"] if lang == "fr" else GALLERY[gid]["name"])
        elif kind == "upload":
            fname = s.get("file") or ""
            if not re.fullmatch(r"side_[0-9a-f]{10}\.jpg", fname):
                raise ValueError(t(lang, "err_unknown_product"))
            if not os.path.isfile(os.path.join(LAMP_UPLOAD_DIR, fname)):
                raise ValueError(t(lang, "err_unknown_product"))
            clean.append({"kind": "upload", "file": fname})
            names.append("votre photo" if lang == "fr" else "your photo")
        else:
            raise ValueError(t(lang, "err_sides"))
    return clean, names


@app.route("/api/lamp-checkout", methods=["POST"])
def lamp_checkout():
    data = request.get_json(force=True)
    lang = (data.get("lang") or "").strip().lower()
    if lang not in ("fr", "en"):
        lang = "fr"
    pack = data.get("pack") or "single"
    if pack not in ("single", "pack4"):
        return jsonify({"error": t(lang, "err_unknown_product")}), 400
    try:
        sides, names = validate_sides(data.get("sides"), lang)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    amount = LAMP_PACK4 if pack == "pack4" else LAMP_SINGLE
    side_summary = " / ".join(names)
    label = (t(lang, "lamp_pack4_label") if pack == "pack4" else t(lang, "lamp_single_label"))
    label = f"{label} - {side_summary[:120]}"
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
        return jsonify({"error": t(lang, "err_payment")}), 503
    import stripe
    stripe.api_key = STRIPE_SECRET
    ship_label = ("Expédition à taux fixe (CA/US)" if lang == "fr"
                  else "Flat-rate shipping (CA/US)")
    sess = stripe.checkout.Session.create(
        payment_method_types=["card"],
        locale="fr" if lang == "fr" else "en",
        line_items=[{"price_data": {
            "currency": "cad", "unit_amount": amount,
            "product_data": {"name": label}}, "quantity": 1}],
        mode="payment",
        shipping_address_collection={"allowed_countries": ["CA", "US"]},
        shipping_options=[{"shipping_rate_data": {
            "type": "fixed_amount",
            "fixed_amount": {"amount": LAMP_SHIPPING, "currency": "cad"},
            "display_name": ship_label}}],
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
        cd = obj.get("customer_details") or {}
        email = (cd.get("email") or "").strip()
        cust_name = (cd.get("name") or "").strip()[:120]
        ship = obj.get("shipping_details") or {}
        ship_name = ((ship.get("name") or "").strip() or cust_name)[:120]
        ship_addr = _fmt_address(ship.get("address") or {})
        if meta.get("kind") == "shop" and meta.get("order_id"):
            mark_order_paid(meta["order_id"], email, cust_name, ship_name, ship_addr)
        elif meta.get("kind") == "lamp" and meta.get("order_id"):
            conn = db()
            conn.execute(
                "UPDATE lamp_orders SET paid=1, email=?, customer_name=?, ship_name=?, "
                "ship_address=? WHERE id=?",
                (email, cust_name, ship_name, ship_addr, meta["order_id"]))
            conn.commit()
            conn.close()
    return "ok", 200


# ---------- admin ----------
def admin_ok():
    """Seller session login, or the ?token= backup (constant-time compare)."""
    if session.get("admin_login"):
        return True
    if not ADMIN_TOKEN:
        return False
    token = request.args.get("token", "") or request.headers.get("X-Admin-Token", "")
    return hmac.compare_digest(token, ADMIN_TOKEN)


@app.route("/admin/")
def admin_page():
    if not admin_ok():
        return redirect("/admin/login")
    token = request.args.get("token", "")
    body = f"""
<div class="admin-wrap">
<p class="kicker">ADN Creations</p>
<h1>Store admin</h1>
<p class="muted">Manage products, preorders, announcements, work-in-progress updates, and orders. Changes go live immediately. <a href="/admin/logout">Log out</a></p>

<div class="admin-card">
<h2>Products</h2>
<div id="productList"></div>
<h3 style="margin-top:24px">Add / edit product</h3>
<form id="productForm">
<input type="hidden" id="pf-id">
<div class="field"><label>Name</label><input type="text" id="pf-name" required maxlength="120"></div>
<div class="field"><label>Name (FR)</label><input type="text" id="pf-name-fr" maxlength="120"></div>
<div class="two-col" style="gap:16px">
<div class="field"><label>Price (CAD)</label><input type="number" id="pf-price" step="0.01" min="0" required></div>
<div class="field"><label>Additional unit price (CAD, optional, e.g. $29.99 for extra lamps)</label><input type="number" id="pf-addprice" step="0.01" min="0"></div>
</div>
<div class="field"><label>Stock (blank = unlimited)</label><input type="number" id="pf-stock" min="0"></div>
<div class="field"><label>Photo</label><input type="file" id="pf-photo-file" accept="image/*">
<input type="text" id="pf-photo" placeholder="or paste an image URL, e.g. /img/products/x.jpg" style="margin-top:8px"></div>
<div class="field"><label>Departments</label><div class="checkbox-row" id="pf-depts"></div></div>
<div class="checkbox-row">
<label><input type="checkbox" id="pf-preorder"> Preorder</label>
<label><input type="checkbox" id="pf-engravable"> Engravable (text field at checkout)</label>
<label><input type="checkbox" id="pf-inworks"> In the works (story page, follow-the-build, no buy button)</label>
<label><input type="checkbox" id="pf-purchasable" checked> Available to buy</label>
<label><input type="checkbox" id="pf-active" checked> Visible in shop</label>
</div>
<div class="field" id="pf-shipdate-wrap" style="display:none"><label>Expected ship date (shown to buyer)</label><input type="text" id="pf-shipdate" placeholder="e.g. December 2026" maxlength="60"></div>
<div class="field"><label>Custom page link (optional, e.g. /custom-lamp.html)</label><input type="text" id="pf-customlink" maxlength="120"></div>
<div class="field"><label>Description</label><textarea id="pf-desc" maxlength="2000"></textarea></div>
<div class="field"><label>Description (FR)</label><textarea id="pf-desc-fr" maxlength="2000"></textarea></div>
<div class="field"><label>Story: why this piece exists, how it is made (shown on the product page)</label><textarea id="pf-story" maxlength="3000"></textarea></div>
<div class="field"><label>Story (FR)</label><textarea id="pf-story-fr" maxlength="3000"></textarea></div>
<div class="field"><label>Photos (ordered gallery; tick one as the scale shot shown last)</label>
<div id="pf-photos"></div>
<div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;align-items:center"><input type="file" id="pf-photo-upload" accept="image/*,video/mp4,.mov" multiple><button class="btn btn-outline" type="button" id="pf-photo-add">Upload</button></div>
<p class="small muted">Photos and MP4/MOV videos, several at once. Videos play in the product gallery (50 MB max each). Use Up/Down to reorder; mark one photo as the scale shot shown last.</p>
</div>
<button class="btn btn-primary" type="submit">Save product</button>
<button class="btn btn-outline" type="button" id="pf-cancel" style="margin-left:8px">Clear</button>
</form>
</div>

<div class="admin-card">
<h2>Product views</h2>
<p class="small muted">One view counted per visitor per product per day. Click a column header to sort.</p>
<div id="viewList"><p class="muted">Loading...</p></div>
</div>

<div class="admin-card">
<h2>Announcements</h2>
<div id="annList"></div>
<h3 style="margin-top:24px">New announcement</h3>
<form id="annForm">
<div class="field"><label>Title</label><input type="text" id="af-title" required maxlength="140"></div>
<div class="field"><label>Title (FR)</label><input type="text" id="af-title-fr" maxlength="140"></div>
<div class="field"><label>Body</label><textarea id="af-body" required maxlength="2000"></textarea></div>
<div class="field"><label>Body (FR)</label><textarea id="af-body-fr" maxlength="2000"></textarea></div>
<button class="btn btn-primary" type="submit">Publish announcement</button>
</form>
</div>

<div class="admin-card">
<h2>Work in progress</h2>
<div id="wipList"></div>
<h3 style="margin-top:24px">New project</h3>
<form id="wipForm">
<div class="field"><label>Project name</label><input type="text" id="wf-project" required maxlength="120"></div>
<div class="field"><label>Project name (FR)</label><input type="text" id="wf-project-fr" maxlength="120"></div>
<div class="field"><label>Status (e.g. In development, Complete)</label><input type="text" id="wf-status" maxlength="60"></div>
<div class="field"><label>Status (FR)</label><input type="text" id="wf-status-fr" maxlength="60"></div>
<button class="btn btn-primary" type="submit">Add project</button>
</form>
<h3 style="margin-top:24px">Add progress update</h3>
<form id="wipUpdateForm">
<div class="field"><label>Project</label><select id="wu-project"></select></div>
<div class="field"><label>Update</label><textarea id="wu-text" required maxlength="1000"></textarea></div>
<div class="field"><label>Update (FR)</label><textarea id="wu-text-fr" maxlength="1000"></textarea></div>
<button class="btn btn-primary" type="submit">Add update</button>
</form>
</div>

<div class="admin-card">
<h2>Orders to dispatch</h2>
<p class="small muted"><label style="display:inline-flex;gap:6px;align-items:center"><input type="checkbox" id="ord-showall"> Show all orders, including dispatched and unpaid</label><span id="ord-count" style="margin-left:12px"></span></p>
<div id="orderList"><p class="muted">Loading...</p></div>
</div>

<div class="admin-card">
<h2>Engraving requests</h2>
<div id="engList"><p class="muted">Loading...</p></div>
</div>

<div class="admin-card">
<h2>Portrait ideas</h2>
<div id="porList"><p class="muted">Loading...</p></div>
</div>

<div class="admin-card">
<h2>Project suggestions</h2>
<div id="sgList"><p class="muted">Loading...</p></div>
</div>

<div class="admin-card">
<h2>Notify-me list</h2>
<div id="ntfList"><p class="muted">Loading...</p></div>
</div>

<div class="admin-card">
<h2>Reviews</h2>
<p class="small muted">New reviews appear here for approval before they show on the product page.</p>
<div id="revList"><p class="muted">Loading...</p></div>
</div>

<div class="admin-card">
<h2>Discount codes</h2>
<p class="small muted">Percent-off codes for the shop checkout (e.g. creator codes). The code used is saved on each order for commission tracking.</p>
<div id="couponList"><p class="muted">Loading...</p></div>
<h3 style="margin-top:24px">New code</h3>
<form id="couponForm">
<div class="two-col" style="gap:16px">
<div class="field"><label>Code (e.g. KRISTIE15)</label><input type="text" id="cf-code" required maxlength="32" style="text-transform:uppercase"></div>
<div class="field"><label>Percent off (1-90)</label><input type="number" id="cf-pct" min="1" max="90" required></div>
</div>
<div class="field"><label>Note (e.g. creator name)</label><input type="text" id="cf-note" maxlength="160"></div>
<button class="btn btn-primary" type="submit">Create code</button>
</form>
</div>
</div>
<script>var ADMIN_TOKEN = {json.dumps(token)};</script>
<script src="/admin.js"></script>"""
    return shell("Store admin", "ADN Creations store administration.", body)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_login"):
        return redirect("/admin/")
    lang = get_lang()
    s = STR["fr"] if lang != "en" else STR["en"]
    err = ""
    code = 200
    login_enabled = bool(ADMIN_USER and ADMIN_PASSWORD)
    if request.method == "POST":
        if not login_enabled:
            err = s["login_disabled"]
            code = 503
        else:
            u = request.form.get("username", "")
            pw = request.form.get("password", "")
            if hmac.compare_digest(u, ADMIN_USER) and hmac.compare_digest(pw, ADMIN_PASSWORD):
                session["admin_login"] = True
                session.permanent = True
                return redirect("/admin/")
            err = s["login_bad"]
            code = 401
    notice = f'<div class="notice notice-err">{h(err)}</div>' if err else ""
    dis = "" if login_enabled else "disabled"
    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title data-i18n="login.title">{h(s["login_title"])}</title>
<link rel="icon" href="/icon.png" type="image/png">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<div class="admin-wrap" style="max-width:440px">
<p class="kicker">ADN Creations</p>
<h1 data-i18n="login.h">{h(s["login_h"])}</h1>
<div class="admin-card">
{notice}
<form method="post" action="/admin/login">
<div class="field"><label for="lg-user" data-i18n="login.user">{h(s["login_user"])}</label>
<input type="text" id="lg-user" name="username" autocomplete="username" required {dis}></div>
<div class="field"><label for="lg-pass" data-i18n="login.pass">{h(s["login_pass"])}</label>
<input type="password" id="lg-pass" name="password" autocomplete="current-password" required {dis}></div>
<button class="btn btn-brass btn-block" type="submit" data-i18n="login.submit"{"" if login_enabled else " disabled"}>{h(s["login_submit"])}</button>
</form>
<p style="margin-top:16px"><a href="/" data-i18n="login.back">{h(s["login_back"])}</a></p>
<p style="margin-top:8px"><span class="lang-toggle" role="group" aria-label="Language / Langue"><button type="button" data-lang="fr" class="on">FR</button><button type="button" data-lang="en">EN</button></span></p>
</div>
</div>
<script src="/i18n.js"></script>
</body>
</html>"""
    return html, code


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_login", None)
    return redirect("/admin/login")


@app.route("/api/suggest-project", methods=["POST"])
def api_suggest_project():
    data = request.get_json(force=True)
    lang = (data.get("lang") or "").strip().lower()
    if lang not in ("fr", "en"):
        lang = "fr"
    name = (data.get("name") or "").strip()[:120]
    email = (data.get("email") or "").strip()[:160]
    title = (data.get("title") or "").strip()[:160]
    description = (data.get("description") or "").strip()[:2000]
    category = (data.get("category") or "other").strip().lower()
    if category not in ("product", "custom", "collab", "other"):
        category = "other"
    if not name or not title or not description or "@" not in email:
        return jsonify({"error": t(lang, "err_request")}), 400
    sid = "sg_" + uuid.uuid4().hex[:10]
    conn = db()
    conn.execute(
        "INSERT INTO project_suggestions (id, created, name, email, title, description, category) "
        "VALUES (?,?,?,?,?,?,?)", (sid, now_iso(), name, email, title, description, category))
    conn.commit()
    conn.close()
    ok, _ = send_email(
        SUPPORT_EMAIL, f"New project suggestion from {name}: {title}",
        f"Name: {name}\nEmail: {email}\nCategory: {category}\nTitle: {title}\n\n{description}\n")
    return jsonify({"ok": True, "emailed": ok})


@app.route("/api/admin/suggestions")
def admin_suggestions():
    if not admin_ok():
        abort(403)
    conn = db()
    rows = conn.execute("SELECT * FROM project_suggestions ORDER BY created DESC").fetchall()
    conn.close()
    return jsonify({"suggestions": [dict(r) for r in rows]})


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
    add_raw = data.get("additional_price")
    add_price = int(round(float(add_raw) * 100)) if add_raw not in ("", None) else None
    stock_raw = (data.get("stock") or "").strip() if isinstance(data.get("stock"), str) else data.get("stock")
    stock = int(stock_raw) if stock_raw not in ("", None) else None
    depts = [d for d in (data.get("depts") or []) if d in DEPTS]
    conn.execute(
        "INSERT INTO products (id, name, name_fr, price_cents, additional_price_cents, "
        "photo, description, description_fr, story, story_fr, depts, stock, "
        "preorder, preorder_ship_date, engravable, in_works, purchasable, custom_link, active, sort, created) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, name_fr=excluded.name_fr, "
        "price_cents=excluded.price_cents, additional_price_cents=excluded.additional_price_cents, "
        "photo=excluded.photo, description=excluded.description, description_fr=excluded.description_fr, "
        "story=excluded.story, story_fr=excluded.story_fr, depts=excluded.depts, "
        "stock=excluded.stock, preorder=excluded.preorder, "
        "preorder_ship_date=excluded.preorder_ship_date, engravable=excluded.engravable, "
        "in_works=excluded.in_works, purchasable=excluded.purchasable, custom_link=excluded.custom_link, "
        "active=excluded.active",
        (pid, (data.get("name") or "").strip()[:120], (data.get("name_fr") or "").strip()[:120],
         price, add_price,
         (data.get("photo") or "").strip()[:300],
         (data.get("description") or "").strip()[:2000],
         (data.get("description_fr") or "").strip()[:2000],
         (data.get("story") or "").strip()[:3000],
         (data.get("story_fr") or "").strip()[:3000],
         json.dumps(depts), stock, 1 if data.get("preorder") else 0,
         (data.get("preorder_ship_date") or "").strip()[:60],
         1 if data.get("engravable") else 0, 1 if data.get("in_works") else 0,
         1 if data.get("purchasable", True) else 0,
         (data.get("custom_link") or "").strip()[:120],
         1 if data.get("active", True) else 0,
         int(data.get("sort") or 0), now_iso()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": pid})


@app.route("/api/admin/photos", methods=["GET", "POST"])
def admin_photos():
    if not admin_ok():
        abort(403)
    conn = db()
    if request.method == "GET":
        pid = request.args.get("product_id", "")
        rows = conn.execute(
            "SELECT * FROM product_photos WHERE product_id=? ORDER BY is_scale ASC, sort ASC",
            (pid,)).fetchall()
        conn.close()
        return jsonify({"photos": [dict(r) for r in rows]})
    data = request.get_json(force=True)
    pid = (data.get("product_id") or "").strip()
    photo = (data.get("photo") or "").strip()[:300]
    kind = (data.get("kind") or "photo").strip().lower()
    if kind not in ("photo", "video"):
        kind = "photo"
    if not pid or not photo:
        conn.close()
        return jsonify({"error": "product and photo required"}), 400
    n = conn.execute("SELECT COUNT(*) FROM product_photos WHERE product_id=?", (pid,)).fetchone()[0]
    phid = "ph_" + uuid.uuid4().hex[:10]
    conn.execute(
        "INSERT INTO product_photos (id, product_id, photo, kind, sort, is_scale, created) "
        "VALUES (?,?,?,?,?,?,?)", (phid, pid, photo, kind, n, 0, now_iso()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": phid})


@app.route("/api/admin/photos/<phid>", methods=["POST", "DELETE"])
def admin_photo_one(phid):
    if not admin_ok():
        abort(403)
    conn = db()
    if request.method == "DELETE":
        conn.execute("DELETE FROM product_photos WHERE id=?", (phid,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    data = request.get_json(force=True)
    action = data.get("action")
    row = conn.execute("SELECT * FROM product_photos WHERE id=?", (phid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "unknown photo"}), 404
    if action == "scale":
        conn.execute("UPDATE product_photos SET is_scale=0 WHERE product_id=?", (row["product_id"],))
        conn.execute("UPDATE product_photos SET is_scale=1 WHERE id=?", (phid,))
    elif action == "move":
        direction = int(data.get("direction") or 0)
        sibs = conn.execute(
            "SELECT id, sort FROM product_photos WHERE product_id=? AND is_scale=? ORDER BY sort ASC",
            (row["product_id"], row["is_scale"])).fetchall()
        ids = [s["id"] for s in sibs]
        i = ids.index(phid)
        j = i + direction
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            for k, sid in enumerate(ids):
                conn.execute("UPDATE product_photos SET sort=? WHERE id=?", (k, sid))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


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
    fname = (f.filename or "").lower()
    mt = (f.mimetype or "").lower()
    is_video = mt.startswith("video/") or fname.endswith((".mp4", ".mov"))
    if is_video:
        if request.content_length and request.content_length > VIDEO_MAX_BYTES + 1024 * 1024:
            return jsonify({"error": "video too large (50 MB max)"}), 413
        if not (fname.endswith((".mp4", ".mov")) or mt in ("video/mp4", "video/quicktime")):
            return jsonify({"error": "videos must be MP4 or MOV"}), 400
        vid = "vid_" + uuid.uuid4().hex[:10]
        tmp = os.path.join(VIDEO_DIR, vid + ".upload")
        try:
            total = 0
            with open(tmp, "wb") as out:
                while True:
                    chunk = f.stream.read(256 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > VIDEO_MAX_BYTES:
                        raise ValueError("too large")
                    out.write(chunk)
        except ValueError:
            if os.path.exists(tmp):
                os.remove(tmp)
            return jsonify({"error": "video too large (50 MB max)"}), 413
        final = os.path.join(VIDEO_DIR, vid + ".mp4")
        if fname.endswith(".mov") or mt == "video/quicktime":
            # iPhone MOV -> widely playable MP4 (H.264 + AAC).
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", tmp, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                     "-crf", "23", "-preset", "veryfast", "-c:a", "aac",
                     "-movflags", "+faststart", final],
                    check=True, capture_output=True, timeout=300)
                os.remove(tmp)
            except Exception:
                if os.path.exists(tmp):
                    os.remove(tmp)
                return jsonify({"error": "could not process that video"}), 400
        else:
            os.rename(tmp, final)
        return jsonify({"url": "/media/videos/" + vid + ".mp4", "kind": "video"})
    name = "prod_" + uuid.uuid4().hex[:10] + ".jpg"
    try:
        img = ImageOps.exif_transpose(Image.open(f.stream)).convert("RGB")
        if img.width > 1400:
            img = img.resize((1400, int(img.height * 1400 / img.width)), Image.LANCZOS)
        img.save(os.path.join(PRODUCT_IMG_DIR, name), "JPEG", quality=80, optimize=True)
    except Exception:
        return jsonify({"error": "could not read that image"}), 400
    return jsonify({"url": "/img/products/" + name, "kind": "photo"})


@app.route("/media/videos/<path:fname>")
def media_video(fname):
    if "/" in fname or "\\" in fname or not fname.endswith(".mp4"):
        abort(404)
    return send_from_directory(VIDEO_DIR, fname, mimetype="video/mp4")


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
    conn.execute("INSERT INTO announcements (id, created, title, title_fr, body, body_fr) VALUES (?,?,?,?,?,?)",
                 (aid, now_iso(), (data.get("title") or "").strip()[:140],
                  (data.get("title_fr") or "").strip()[:140],
                  (data.get("body") or "").strip()[:2000],
                  (data.get("body_fr") or "").strip()[:2000]))
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
    conn.execute("INSERT INTO wip_projects (id, project, project_fr, status, status_fr, photo, sort, created) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (wid, (data.get("project") or "").strip()[:120],
                  (data.get("project_fr") or "").strip()[:120],
                  (data.get("status") or "").strip()[:60],
                  (data.get("status_fr") or "").strip()[:60], "", 99, now_iso()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": wid})


@app.route("/api/admin/wip-update", methods=["POST"])
def admin_wip_update():
    if not admin_ok():
        abort(403)
    data = request.get_json(force=True)
    conn = db()
    conn.execute("INSERT INTO wip_updates (id, project_id, created, text, text_fr) VALUES (?,?,?,?,?)",
                 ("wu_" + uuid.uuid4().hex[:10], data.get("project_id"),
                  now_iso(), (data.get("text") or "").strip()[:1000],
                  (data.get("text_fr") or "").strip()[:1000]))
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


def send_tracking_email(order):
    """Email the customer their tracking number. Returns (ok, detail)."""
    to = (order.get("email") or "").strip()
    if not to or "@" not in to:
        return False, "no customer email on file"
    name = order.get("customer_name") or order.get("ship_name") or ""
    tn = order.get("tracking_number", "")
    carrier = order.get("carrier", "")
    carrier_line = f"Carrier: {carrier}\n" if carrier else ""
    carrier_line_fr = f"Transporteur : {carrier}\n" if carrier else ""
    body = (
        f"Hi{name and ' ' + name or ''},\n\n"
        f"Good news: your ADN Creations order {order['id']} is on its way.\n\n"
        f"Tracking number: {tn}\n"
        f"{carrier_line}"
        "\nThank you for supporting hand crafted work from Montreal.\n\n"
        "Antonio\nADN Creations\n"
        "-----\n\n"
        f"Bonjour{name and ', ' + name or ''},\n\n"
        f"Bonne nouvelle : votre commande ADN Creations {order['id']} est en route.\n\n"
        f"Numéro de suivi : {tn}\n"
        f"{carrier_line_fr}"
        "\nMerci de soutenir le travail fait à la main à Montréal.\n\n"
        "Antonio\nADN Creations\n"
    )
    return send_email(
        to, f"Your ADN Creations order {order['id']} has shipped", body)


@app.route("/api/admin/dispatch", methods=["POST"])
def admin_dispatch():
    """Save a tracking number on a paid order, mark it dispatched, email the customer."""
    if not admin_ok():
        abort(403)
    data = request.get_json(force=True)
    oid = (data.get("order_id") or "").strip()
    tracking = (data.get("tracking_number") or "").strip()[:80]
    carrier = (data.get("carrier") or "").strip()[:60]
    if not oid or not tracking:
        return jsonify({"error": "order and tracking number required"}), 400
    conn = db()
    o = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    table = "orders"
    if not o:
        o = conn.execute("SELECT * FROM lamp_orders WHERE id=?", (oid,)).fetchone()
        table = "lamp_orders"
    if not o:
        conn.close()
        return jsonify({"error": "unknown order"}), 404
    o = dict(o)
    if not o.get("paid"):
        conn.close()
        return jsonify({"error": "order is not paid yet"}), 400
    conn.execute(
        f"UPDATE {table} SET shipped=1, tracking_number=?, carrier=?, shipped_date=? "
        "WHERE id=?",
        (tracking, carrier, now_iso(), oid))
    conn.commit()
    conn.close()
    o["tracking_number"] = tracking
    o["carrier"] = carrier
    emailed, detail = send_tracking_email(o)
    return jsonify({"ok": True, "emailed": emailed, "email_detail": detail})


@app.route("/api/admin/product-views")
def admin_product_views():
    """Per-product view counts: total + last 30 days. Admin stays English."""
    if not admin_ok():
        abort(403)
    conn = db()
    rows = conn.execute(
        "SELECT v.product_id, COALESCE(p.name, v.product_id) AS name, "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN v.day >= date('now', '-30 days') THEN 1 ELSE 0 END) AS last30 "
        "FROM product_views v LEFT JOIN products p ON p.id = v.product_id "
        "GROUP BY v.product_id ORDER BY total DESC").fetchall()
    conn.close()
    views = [{"product_id": r["product_id"], "name": r["name"],
              "total": r["total"], "last30": r["last30"]} for r in rows]
    return jsonify({
        "views": views,
        "grand_total": sum(v["total"] for v in views),
        "grand_last30": sum(v["last30"] for v in views),
    })


@app.route("/api/admin/engraving-requests")
def admin_engraving_requests():
    if not admin_ok():
        abort(403)
    conn = db()
    rows = conn.execute("SELECT * FROM engraving_requests ORDER BY created DESC LIMIT 200").fetchall()
    conn.close()
    return jsonify({"requests": [dict(r) for r in rows]})


@app.route("/api/admin/portrait-ideas")
def admin_portrait_ideas():
    if not admin_ok():
        abort(403)
    conn = db()
    rows = conn.execute("SELECT * FROM portrait_ideas ORDER BY created DESC LIMIT 200").fetchall()
    conn.close()
    return jsonify({"ideas": [dict(r) for r in rows]})


@app.route("/api/admin/notify-me")
def admin_notify_me():
    if not admin_ok():
        abort(403)
    conn = db()
    rows = conn.execute(
        "SELECT n.*, p.name as product_name FROM notify_me n "
        "LEFT JOIN products p ON p.id=n.product_id "
        "ORDER BY n.created DESC LIMIT 200").fetchall()
    conn.close()
    return jsonify({"list": [dict(r) for r in rows]})


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
