from __future__ import annotations

import html as py_html
import json
import math
import os
import re
import unicodedata
import time
import uuid
import shutil
import posixpath
import zipfile
import hashlib
from io import BytesIO
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from markupsafe import Markup, escape

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


from werkzeug.utils import secure_filename


import os
STRIPE_SECRET_KEY_DEFAULT = os.getenv(
    "STRIPE_SECRET_KEY",
    "sk_test_REPLACE_WITH_ENV_VARIABLE"
)
from werkzeug.utils import secure_filename
STRIPE_PUBLISHABLE_KEY_DEFAULT = os.getenv(
    "STRIPE_PUBLISHABLE_KEY",
    "pk_test_REPLACE_WITH_ENV_VARIABLE"
)

def _load_dotenv() -> None:
    """Best-effort .env loader (no external dependency).

    Only sets variables that are not already present in the environment.
    Supports simple KEY=VALUE lines (optionally quoted); ignores blanks and comments.
    """
    try:
        base_dir = os.path.abspath(os.path.dirname(__file__))
        env_path = os.path.join(base_dir, ".env")
        if not os.path.isfile(env_path):
            return
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if (v.startswith("'") and v.endswith("'")) or (v.startswith("\"") and v.endswith("\"")):
                    v = v[1:-1]
                if not k:
                    continue
                if k not in os.environ:
                    os.environ[k] = v
    except Exception:
        return



def build_stripe_line_items(cart: Dict[str, int], catalog: List["Product"]) -> List[Dict[str, Any]]:
    """Convert current cart to Stripe Checkout line_items."""
    by_id = {p.id: p for p in catalog}
    line_items: List[Dict[str, Any]] = []

    for pid, qty in cart.items():
        try:
            qty_int = int(qty)
        except Exception:
            continue
        if qty_int <= 0:
            continue

        p = by_id.get(pid)
        if not p:
            continue

        unit = p.unit_price_for_cart()
        amount = int(round(float(unit) * 100))

        line_items.append(
            {
                "quantity": qty_int,
                "price_data": {
                    "currency": "pln",
                    "unit_amount": amount,
                    "product_data": {"name": p.title},
                },
            }
        )

    return line_items


import stripe


# -------------------------
# Helpers
# -------------------------
def format_pln(value: float) -> str:
    """Polish formatting: 69,00 zł (space thousands, comma decimals)."""
    try:
        v = float(value)
    except Exception:
        v = 0.0
    s = f"{v:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", " ")
    return f"{s} zł"


def slugify(name: str, max_len: int = 80) -> str:
    norm = unicodedata.normalize("NFKD", (name or "").strip())
    chars = []
    for ch in norm:
        if unicodedata.category(ch) == "Mn":
            continue
        if ord(ch) < 128:
            chars.append(ch)
        else:
            chars.append("-")
    s = "".join(chars).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    s = s or "item"
    return s[:max_len] if len(s) > max_len else s


# -------------------------
# DocuBeauty dynamic catalog (48 kategorii z lokalnego katalogu "produkty")
# -------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DOCUBEAUTY_PRODUCTS_ROOT = os.getenv(
    "DOCUBEAUTY_PRODUCTS_ROOT",
    os.path.join(BASE_DIR, "produkty"),
)

CATEGORY_META = {'autologiczny-wypelniacz-pakiet-dokumentacji': {'name_pl': 'Autologiczny wypełniacz — pakiet dokumentacji', 'price_from': 89, 'short_desc': 'Zestaw zgód, ankiet i kart zabiegowych do zabiegów z autologicznym wypełniaczem.'}, 'beauty-plan-druk': {'name_pl': 'Beauty Plan — druk (PDF)', 'price_from': 29, 'short_desc': 'Gotowy szablon planu pielęgnacji/terapii do wydruku i przekazania klientce.'}, 'certyfikaty': {'name_pl': 'Certyfikaty — szablony', 'price_from': 29, 'short_desc': 'Edytowalne szablony certyfikatów ukończenia zabiegu/szkolenia (PDF/Canva).'}, 'depilacja-laserowa-dokumenty-zabiegowe-pakiet': {'name_pl': 'Depilacja laserowa — pakiet dokumentów zabiegowych', 'price_from': 79, 'short_desc': 'Komplet dokumentów: wywiad, przeciwwskazania, zgody i karta zabiegowa.'}, 'elektroepilacja-dokumenty-zabiegowe': {'name_pl': 'Elektroepilacja — dokumenty zabiegowe', 'price_from': 69, 'short_desc': 'Zgody, wywiad i karta zabiegowa do elektroepilacji.'}, 'fizjoterapia-dokumentacja-pakiet': {'name_pl': 'Fizjoterapia — pakiet dokumentacji', 'price_from': 79, 'short_desc': 'Wywiad, zgody i karta wizyty do prowadzenia dokumentacji fizjoterapeutycznej.'}, 'j-ang-przedluzanie-rzes-dokumenty': {'name_pl': 'Przedłużanie rzęs — dokumenty (PL/EN)', 'price_from': 69, 'short_desc': 'Dwujęzyczny zestaw formularzy: konsultacja, zgoda, zalecenia pozabiegowe.'}, 'keratynowe-prostowanie-wlosow-dokumenty-zabiegowe-pakiet': {'name_pl': 'Keratynowe prostowanie włosów — pakiet dokumentów', 'price_from': 69, 'short_desc': 'Wywiad, zgoda, instrukcje pielęgnacji i karta zabiegowa.'}, 'kosmetyczne-wybielanie-zebow-dokumentacja-zabiegowa': {'name_pl': 'Kosmetyczne wybielanie zębów — dokumentacja zabiegowa', 'price_from': 69, 'short_desc': 'Wywiad, przeciwwskazania, zgody i zalecenia po zabiegu.'}, 'laminacja-brwi-dokumenty-canva': {'name_pl': 'Laminacja brwi — dokumenty (Canva)', 'price_from': 69, 'short_desc': 'Szablony do edycji w Canva: wywiad, zgoda, karta zabiegowa.'}, 'laminacja-brwi': {'name_pl': 'Laminacja brwi — dokumentacja zabiegowa', 'price_from': 59, 'short_desc': 'Gotowe formularze PDF do laminacji brwi.'}, 'laser-frakcyjny-co2-dokumentacja-zabiegowa': {'name_pl': 'Laser frakcyjny CO2 — dokumentacja zabiegowa', 'price_from': 99, 'short_desc': 'Komplet zgód i formularzy zgodnych z praktyką medycyny estetycznej.'}, 'lifting-laminacja-rzes-dokumentacja-zabiegowa': {'name_pl': 'Lifting i laminacja rzęs — dokumentacja', 'price_from': 59, 'short_desc': 'Wywiad, zgoda i karta zabiegowa oraz zalecenia.'}, 'lipoliza-iniekcyjna-dokumentacja-zabiegowa': {'name_pl': 'Lipoliza iniekcyjna — dokumentacja zabiegowa', 'price_from': 99, 'short_desc': 'Formularze: kwalifikacja, przeciwwskazania, zgoda i karta zabiegowa.'}, 'makijaz-permanentny-pakiet-dokumentacji': {'name_pl': 'Makijaż permanentny (PMU) — pakiet dokumentacji', 'price_from': 99, 'short_desc': 'Komplet formularzy konsultacyjnych i zgód oraz zalecenia.'}, 'manicure-dokumenty-zabiegowe-zestaw': {'name_pl': 'Manicure — zestaw dokumentów zabiegowych', 'price_from': 49, 'short_desc': 'Karta klienta, zgoda i zalecenia do usług manicure.'}, 'masaz-dokumenty-zabiegowe': {'name_pl': 'Masaż — dokumenty zabiegowe', 'price_from': 49, 'short_desc': 'Wywiad, zgoda i karta zabiegowa do masażu.'}, 'mezoterapia-beziglowa-dokumentacja-zabiegowa': {'name_pl': 'Mezoterapia bezigłowa — dokumentacja zabiegowa', 'price_from': 79, 'short_desc': 'Formularze kwalifikacji, zgody i zalecenia pozabiegowe.'}, 'mezoterapia-iglowa-dokumentacja-zabiegowa': {'name_pl': 'Mezoterapia igłowa — dokumentacja zabiegowa', 'price_from': 99, 'short_desc': 'Wywiad medyczny, przeciwwskazania, zgoda i karta zabiegowa.'}, 'mezoterapia-mikroiglowa-dokumentacja-zabiegowa-1': {'name_pl': 'Mezoterapia mikroigłowa — dokumentacja zabiegowa', 'price_from': 79, 'short_desc': 'Zestaw formularzy do terapii mikroigłowej (np. Dermapen).'}, 'miesnie-twarzy': {'name_pl': 'Mięśnie twarzy — plansza/anatomia', 'price_from': 19, 'short_desc': 'Pomocnicza plansza do konsultacji, edukacji i szkoleń.'}, 'modelowanie-ust-dokumentacja-zabiegowa-pakiet': {'name_pl': 'Modelowanie ust — pakiet dokumentacji', 'price_from': 99, 'short_desc': 'Komplet formularzy kwalifikacji i zgód do zabiegów w obrębie ust.'}, 'nici-pdo': {'name_pl': 'Nici PDO — dokumentacja zabiegowa', 'price_from': 99, 'short_desc': 'Wywiad, przeciwwskazania, zgoda i karta zabiegowa.'}, 'oczyszczanie-wodorowe-1': {'name_pl': 'Oczyszczanie wodorowe — dokumentacja', 'price_from': 59, 'short_desc': 'Zgoda, karta zabiegowa i zalecenia po zabiegu.'}, 'osocze-bogatoplytkowe': {'name_pl': 'Osocze bogatopłytkowe (PRP) — dokumentacja', 'price_from': 109, 'short_desc': 'Kwalifikacja, zgody i karta zabiegowa do terapii PRP.'}, 'pakiet-dokumentacji-endermologia': {'name_pl': 'Endermologia — pakiet dokumentacji', 'price_from': 79, 'short_desc': 'Wywiad, zgoda, karta serii zabiegów i zalecenia.'}, 'pedicure-dokumentacja-zabiegowa-zestaw': {'name_pl': 'Pedicure — zestaw dokumentacji', 'price_from': 49, 'short_desc': 'Formularze dla pedicure kosmetycznego: karta, zgoda i zalecenia.'}, 'peeling-weglowy-dokumenty-zabiegowe-zestaw': {'name_pl': 'Peeling węglowy — zestaw dokumentów', 'price_from': 69, 'short_desc': 'Wywiad, zgoda i zalecenia do zabiegu peelingu węglowego.'}, 'peelingi-chemiczne': {'name_pl': 'Peelingi chemiczne — dokumentacja zabiegowa', 'price_from': 79, 'short_desc': 'Kwalifikacja, przeciwwskazania, zgoda i zalecenia.'}, 'permanent-makeup-consultation-forms': {'name_pl': 'Permanent Makeup — formularze konsultacyjne (EN)', 'price_from': 69, 'short_desc': 'Anglojęzyczne formularze konsultacji i zgody dla usług PMU.'}, 'piercing': {'name_pl': 'Piercing — dokumentacja zabiegowa', 'price_from': 59, 'short_desc': 'Wywiad, zgoda, instrukcja pielęgnacji i karta zabiegu.'}, 'pmu-canva': {'name_pl': 'PMU — dokumenty (Canva)', 'price_from': 89, 'short_desc': 'Szablony PMU do edycji w Canva: konsultacja, zgoda i zalecenia.'}, 'podologia-dokumenty-zabiegowe': {'name_pl': 'Podologia — dokumenty zabiegowe', 'price_from': 79, 'short_desc': 'Wywiad, zgoda, karta zabiegowa i zalecenia pozabiegowe.'}, 'przedluzanie-rzes': {'name_pl': 'Przedłużanie rzęs — dokumentacja zabiegowa', 'price_from': 59, 'short_desc': 'Wywiad, zgoda i zalecenia pielęgnacyjne po aplikacji.'}, 'regulamin-salonu': {'name_pl': 'Regulamin salonu — szablon', 'price_from': 39, 'short_desc': 'Gotowy regulamin usług, zapisów i płatności do dopasowania.'}, 'rf-mikroiglowa': {'name_pl': 'RF mikroigłowa — dokumentacja zabiegowa', 'price_from': 99, 'short_desc': 'Zestaw formularzy do zabiegów RF mikroigłowej.'}, 'rodo': {'name_pl': 'RODO/GDPR — pakiet dokumentów', 'price_from': 69, 'short_desc': 'Klauzule informacyjne, zgody i podstawowe wzory do salonu.'}, 'salon-fryzjerski-dokumentacja': {'name_pl': 'Salon fryzjerski — dokumentacja i formularze', 'price_from': 59, 'short_desc': 'Karta klienta, zgody i zalecenia do usług fryzjerskich.'}, 'stymulatory-tkankowe': {'name_pl': 'Stymulatory tkankowe — dokumentacja', 'price_from': 109, 'short_desc': 'Kwalifikacja, przeciwwskazania, zgoda i karta zabiegowa.'}, 'tatuaz': {'name_pl': 'Tatuaż — dokumentacja zabiegowa', 'price_from': 59, 'short_desc': 'Wywiad, zgoda, pielęgnacja i karta zabiegu.'}, 'toksyna-botulinowa-botoks-pakiet-dokumentacji': {'name_pl': 'Toksyna botulinowa (botoks) — pakiet dokumentacji', 'price_from': 109, 'short_desc': 'Formularze med.-estetyczne: kwalifikacja, zgody i karta zabiegowa.'}, 'tooth-gems-dokumentacja-zabiegowa-pakiet': {'name_pl': 'Tooth Gems — pakiet dokumentacji zabiegowej', 'price_from': 59, 'short_desc': 'Zgody, wywiad i zalecenia do aplikacji biżuterii nazębnej.'}, 'unaczynienie-twarzy': {'name_pl': 'Unaczynienie twarzy — plansza/anatomia', 'price_from': 19, 'short_desc': 'Plansza poglądowa przydatna w konsultacjach i szkoleniach.'}, 'unerwienie-twarzy': {'name_pl': 'Unerwienie twarzy — plansza/anatomia', 'price_from': 19, 'short_desc': 'Plansza poglądowa dotycząca unerwienia twarzy do edukacji.'}, 'uniwersalne-karty-zabiegowe-1': {'name_pl': 'Uniwersalne karty zabiegowe — zestaw', 'price_from': 39, 'short_desc': 'Uniwersalne formularze do różnych usług: karta zabiegu i zalecenia.'}, 'usuwanie-tatuazu-pmu-dokumenty-zabiegowe-zestaw': {'name_pl': 'Usuwanie tatuażu/PMU — zestaw dokumentów', 'price_from': 79, 'short_desc': 'Zgody, przeciwwskazania i zalecenia do laserowego usuwania.'}, 'wolumetria': {'name_pl': 'Wolumetria twarzy — dokumentacja zabiegowa', 'price_from': 109, 'short_desc': 'Komplet formularzy do zabiegów wolumetrycznych (wypełniacze).'}, 'zgoda': {'name_pl': 'Zgoda na zabieg — uniwersalny wzór', 'price_from': 19, 'short_desc': 'Uniwersalny formularz zgody z miejscem na opis procedury.'}}

def scan_docubeauty_categories(app_dir: str) -> List[Dict[str, Any]]:
    """Scan DOCUBEAUTY_PRODUCTS_ROOT and return category objects.
    Each category can be a directory or a .zip file. Card images are served from /static/cards/<slug>.png.
    """
    root = DOCUBEAUTY_PRODUCTS_ROOT
    if not root or not os.path.isdir(root):
        return []

    cards_dir = os.path.join(app_dir, "static", "cards")
    cats: List[Dict[str, Any]] = []

    try:
        for name in os.listdir(root):
            if not name or name.startswith("."):
                continue

            full = os.path.join(root, name)

            kind = None
            base = None
            if os.path.isdir(full):
                kind = "dir"
                base = name
            elif os.path.isfile(full) and name.lower().endswith(".zip"):
                kind = "zip"
                base = os.path.splitext(name)[0]
            else:
                continue

            slug = slugify(base)
            meta = CATEGORY_META.get(slug, {})

            display_name = (meta.get("name_pl") or base).strip()
            price_from = meta.get("price_from")
            short_desc = (meta.get("short_desc") or "").strip()

            card_file = f"{slug}.png"
            card_rel = f"cards/{card_file}" if os.path.exists(os.path.join(cards_dir, card_file)) else "cards/_placeholder.png"

            cats.append(
                {
                    "slug": slug,
                    "name": base,
                    "display_name": display_name,
                    "price_from": price_from,
                    "short_desc": short_desc,
                    "kind": kind,
                    "source_path": full,
                    "card_rel": card_rel,
                }
            )
    except Exception:
        return []

    cats.sort(key=lambda c: c.get("display_name", "").lower())
    return cats



def item_id_from_path(rel_path: str) -> str:
    """Stable item id used for DocuBeauty item-card filenames."""
    h = hashlib.md5(rel_path.encode("utf-8", errors="ignore")).hexdigest()[:10]
    base = os.path.basename(rel_path)
    return f"{slugify(base)}-{h}"


def _docubeauty_price_bucket(value: float) -> float:
    """Snap a raw value to a small set of 'normal' PLN prices used in the shop UI."""
    buckets = [19, 29, 39, 49, 59, 69]
    try:
        v = float(value)
    except Exception:
        v = 39.0
    # Choose the closest bucket
    return float(min(buckets, key=lambda b: abs(b - v)))


def docubeauty_item_price(price_from: float, n_items: int, item_key: str) -> float:
    """Derive a reasonable per-file price from a package 'price_from'.

    Requirements from UX:
    - Prices should be on individual items (not category cards).
    - Keep them in simple, familiar PLN buckets (19/29/39/49/59/69).
    - Deterministic (same file keeps same price).
    """
    try:
        pf = float(price_from or 0.0)
    except Exception:
        pf = 0.0
    if pf <= 0:
        pf = 79.0

    try:
        n = int(n_items)
    except Exception:
        n = 1
    n = max(1, n)

    # Base factor: more files in package -> lower per-file price.
    if n >= 10:
        factor = 0.30
    elif n >= 7:
        factor = 0.34
    elif n >= 5:
        factor = 0.38
    elif n >= 3:
        factor = 0.42
    else:
        factor = 0.48

    base = _docubeauty_price_bucket(pf * factor)

    # Small deterministic variation so not every file in a category has identical price.
    # (Still snapped to buckets.)
    seed = int(hashlib.md5((item_key or "").encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    offsets = [0, 0, 0, 10, -10]
    raw = base + offsets[seed % len(offsets)]
    raw = max(19.0, min(69.0, raw))
    return _docubeauty_price_bucket(raw)


def list_docubeauty_items_for_category(cat: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items for a DocuBeauty category (dir or zip)."""
    items: List[Dict[str, Any]] = []
    kind = cat.get("kind")
    if kind == "dir":
        root = cat.get("source_path") or ""
        if not root or not os.path.isdir(root):
            return []
        for r, _, files in os.walk(root):
            for fn in files:
                full = os.path.join(r, fn)
                rel = os.path.relpath(full, root).replace("\\", "/")
                items.append(
                    {
                        "display": rel,
                        "rel": rel,
                        "abs": full,
                        "id": item_id_from_path(full),
                        "ext": os.path.splitext(fn)[1].lower(),
                    }
                )
        items.sort(key=lambda x: x["display"].lower())
        return items

    # ZIP
    zp = cat.get("source_path") or ""
    if not zp or not os.path.isfile(zp):
        return []
    try:
        with zipfile.ZipFile(zp, "r") as zf:
            for info in zf.infolist():
                member = info.filename
                if not member or member.endswith("/"):
                    continue
                member_raw = member
                display = member_raw.replace("\\", "/")
                if display.startswith("__MACOSX/") or display.lower().endswith(".ds_store"):
                    continue
                items.append(
                    {
                        "display": display,
                        "rel": member_raw,
                        "abs": None,
                        "id": item_id_from_path(member_raw),
                        "ext": os.path.splitext(member)[1].lower(),
                    }
                )
    except Exception:
        return []
    items.sort(key=lambda x: x["display"].lower())
    return items


def get_docubeauty_category(app_dir: str, slug: str) -> Optional[Dict[str, Any]]:
    for c in scan_docubeauty_categories(app_dir):
        if c.get("slug") == slug:
            return c
    return None


def get_docubeauty_item_by_id(cat: Dict[str, Any], item_id: str) -> Optional[Dict[str, Any]]:
    for it in list_docubeauty_items_for_category(cat):
        if it.get("id") == item_id:
            return it
    return None


def ensure_cached_dir_zip(app_dir: str, cat: Dict[str, Any]) -> str:
    """Create (or reuse) a ZIP bundle for a directory-category and return its path.
    Cached under static/cache/docubeauty_bundles/<slug>/...
    """
    root = cat.get("source_path") or ""
    if not root or not os.path.isdir(root):
        raise FileNotFoundError("Missing directory category")

    slug = str(cat.get("slug") or "cat")
    cache_base = os.path.join(app_dir, "static", "cache", "docubeauty_bundles", slug)
    os.makedirs(cache_base, exist_ok=True)

    try:
        mtime = os.path.getmtime(root)
    except Exception:
        mtime = 0.0

    key = f"{os.path.abspath(root)}:{mtime}"
    key_hash = hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest()[:12]
    out_name = f"{slug}-{key_hash}.zip"
    out_path = os.path.join(cache_base, out_name)

    if os.path.exists(out_path):
        return out_path

    # Build ZIP
    tmp_path = out_path + ".tmp"
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for r, _, files in os.walk(root):
            for fn in files:
                full = os.path.join(r, fn)
                rel = os.path.relpath(full, root).replace("\\", "/")
                if not rel or rel.startswith("../"):
                    continue
                zf.write(full, rel)

    os.replace(tmp_path, out_path)
    return out_path

def ensure_cached_zip_member(app_dir: str, cat: Dict[str, Any], item: Dict[str, Any]) -> str:
    """Extract a single file from a category ZIP into static/cache/docubeauty and return its path."""
    zp = cat.get("source_path") or ""
    rel = item.get("rel") or ""
    if not zp or not rel:
        raise FileNotFoundError("Missing zip or rel path")

    cache_base = os.path.join(app_dir, "static", "cache", "docubeauty", cat.get("slug") or "cat")
    os.makedirs(cache_base, exist_ok=True)

    try:
        mtime = os.path.getmtime(zp)
    except Exception:
        mtime = 0.0

    key = f"{zp}|{mtime}|{rel}"
    key_hash = hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest()[:16]

    fn = os.path.basename(rel)
    safe_fn = slugify(fn) or "file"
    out_name = f"{safe_fn}-{key_hash}{os.path.splitext(fn)[1]}"
    out_path = os.path.join(cache_base, out_name)

    if os.path.exists(out_path):
        return out_path

    with zipfile.ZipFile(zp, "r") as zf:
        target = rel.replace("\\", "/")
        for info in zf.infolist():
            if info.filename.replace("\\", "/") == target:
                with zf.open(info, "r") as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                return out_path

    raise FileNotFoundError("Member not found in zip")


def build_docubeauty_products(app_dir: str) -> List["Product"]:
    """Build shop Product list from DocuBeauty **categories** and their **items**.

    UX goal (per request):
    - Category cards are used for navigation (no pricing / no cart).
    - Pricing and cart actions belong to the individual files inside each category.
    """
    cats = scan_docubeauty_categories(app_dir)
    if not cats:
        return []

    products: List[Product] = []
    item_products: List[Product] = []
    for c in cats:
        slug = str(c.get("slug") or "")
        title = str(c.get("display_name") or c.get("name") or "").strip()
        if not slug or not title:
            continue

        # Category card = navigation only (pricing is on items).
        price = 0.0

        desc = str(c.get("short_desc") or "").strip()
        # Category card: use the first item's preview if available (DocuBeauty behavior).
        img = "cards/_placeholder.png"
        try:
            cat = get_docubeauty_category(app_dir, slug)
            if cat:
                items = list_docubeauty_items_for_category(cat)
                if items:
                    first_id = items[0].get("id")
                    if first_id:
                        cand = f"cards/items/{slug}/{first_id}.png"
                        if os.path.exists(os.path.join(app_dir, "static", cand)):
                            img = cand
        except Exception:
            pass

        # Fallback to prebuilt category card (if present)
        if img == "cards/_placeholder.png":
            fallback = str(c.get("card_rel") or "").strip()
            if fallback and os.path.exists(os.path.join(app_dir, "static", fallback)):
                img = fallback
        pid = f"dbcat:{slug}"

        products.append(
            Product(
                id=pid,
                title=title,
                category="DocuBeauty",
                category_url="",
                price_pln=price,
                description=desc,
                images=(img,),
                image_source="static",
                source_url="",
                docu_cat_slug=slug,
                docu_item_id="",
            )
        )

        # Build sellable item-products inside this category.
        try:
            cat_obj = get_docubeauty_category(app_dir, slug)
            if cat_obj:
                raw_items = list_docubeauty_items_for_category(cat_obj)
                n_items = len(raw_items)
                try:
                    pf = float(c.get("price_from") or 0.0)
                except Exception:
                    pf = 0.0

                for it in raw_items:
                    item_id = str(it.get("id") or "")
                    if not item_id:
                        continue

                    filename = str(it.get("display") or "").rsplit("/", 1)[-1].strip()
                    if not filename:
                        filename = item_id

                    thumb_rel = f"cards/items/{slug}/{item_id}.png"
                    item_img = img
                    if os.path.exists(os.path.join(app_dir, "static", thumb_rel)):
                        item_img = thumb_rel

                    item_pid = f"dbitem:{slug}:{item_id}"
                    item_price = docubeauty_item_price(pf, n_items, it.get("rel") or item_id)

                    item_products.append(
                        Product(
                            id=item_pid,
                            title=filename,
                            category=title,  # show category name in cart
                            category_url="",
                            price_pln=float(item_price),
                            description="",
                            images=(item_img,) if item_img else tuple(),
                            image_source="static",
                            source_url="",
                            docu_cat_slug=slug,
                            docu_item_id=item_id,
                        )
                    )
        except Exception:
            # If file listing fails, keep the category card.
            pass

    # Stable ordering
    products.sort(key=lambda p: p.title.lower())
    item_products.sort(key=lambda p: (p.category.lower(), p.title.lower()))
    return products + item_products

def format_description_html(raw: str) -> Markup:
    """
    Converts scraped description (often containing literal <br>) into safe structured HTML.
    - converts <br> to newlines
    - removes any remaining tags
    - builds paragraphs + lists
    """
    if not raw:
        return Markup("")

    s = str(raw)
    s = py_html.unescape(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)  # strip all tags

    lines = [ln.strip() for ln in s.split("\n")]
    out_parts: List[str] = []
    list_items: List[str] = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            out_parts.append(
                "<ul>" + "".join(f"<li>{escape(x)}</li>" for x in list_items) + "</ul>"
            )
            list_items = []

    for ln in lines:
        if not ln:
            flush_list()
            continue

        m = re.match(r"^(\*|-|•)\s+(.*)$", ln)
        if m:
            list_items.append(m.group(2).strip())
            continue

        m = re.match(r"^(\d+)[\.)]\s+(.*)$", ln)
        if m:
            list_items.append(f"{m.group(1)}. {m.group(2).strip()}")
            continue

        flush_list()

        # Short line ending with ':' → heading
        if ln.endswith(":") and len(ln) <= 120:
            out_parts.append(f"<h3 class='desc-h'>{escape(ln[:-1])}</h3>")
        else:
            out_parts.append(f"<p>{escape(ln)}</p>")

    flush_list()
    return Markup("\n".join(out_parts))


def is_mobile_request() -> bool:
    """
    Heuristic mobile detection based on User-Agent.
    Goal: reduce per-page items on phones (1-column grid).
    """
    ua = (request.headers.get("User-Agent") or "").lower()
    # common mobile indicators
    tokens = ("mobile", "android", "iphone", "ipod", "windows phone", "opera mini")
    return any(t in ua for t in tokens)


# -------------------------
# Model
# -------------------------
@dataclass(frozen=True)
class Product:
    id: str
    title: str
    category: str
    category_url: str
    price_pln: float
    description: str
    images: Tuple[str, ...]      # relative paths to export_all/images/<...>
    image_source: str            # "media" or "static"
    source_url: str
    download_file: str = ""
    docu_cat_slug: str = ""
    docu_item_id: str = ""


    def display_price(self) -> str:
        return format_pln(self.price_pln)

    def unit_price_for_cart(self) -> float:
        return float(self.price_pln or 0.0)

    def primary_image(self) -> Optional[str]:
        return self.images[0] if self.images else None


# -------------------------
# App factory
# -------------------------
def create_app() -> Flask:
    app = Flask(__name__)

    # Hard disable static caching during development
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

    # Stripe configuration (test keys; override with env vars in production)
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", STRIPE_SECRET_KEY_DEFAULT)
    app.config["STRIPE_PUBLISHABLE_KEY"] = os.getenv(
        "STRIPE_PUBLISHABLE_KEY", STRIPE_PUBLISHABLE_KEY_DEFAULT
    )

    STATIC_VERSION = str(int(time.time()))

    # Template filters
    app.add_template_filter(format_pln, name="pln")
    app.add_template_filter(slugify, name="slug")
    app.add_template_filter(format_description_html, name="desc_html")

    EXPORT_DIR = os.path.join(app.root_path, "export_all")
    EXPORT_PRODUCTS = os.path.join(EXPORT_DIR, "products.json")
    EXPORT_IMAGES = os.path.join(EXPORT_DIR, "images")
    FALLBACK_PRODUCTS = os.path.join(app.root_path, "data", "products.json")
    PRICE_OVERRIDES_PATH = os.path.join(app.root_path, "data", "price_overrides.json")
    os.makedirs(os.path.dirname(PRICE_OVERRIDES_PATH), exist_ok=True)
    DESCRIPTION_OVERRIDES_PATH = os.path.join(app.root_path, "data", "description_overrides.json")
    os.makedirs(os.path.dirname(DESCRIPTION_OVERRIDES_PATH), exist_ok=True)
    TITLE_OVERRIDES_PATH = os.path.join(app.root_path, "data", "title_overrides.json")
    os.makedirs(os.path.dirname(TITLE_OVERRIDES_PATH), exist_ok=True)
    CATEGORY_OVERRIDES_PATH = os.path.join(app.root_path, "data", "category_overrides.json")
    os.makedirs(os.path.dirname(CATEGORY_OVERRIDES_PATH), exist_ok=True)

    CUSTOM_PRODUCTS_PATH = os.path.join(app.root_path, "data", "custom_products.json")
    os.makedirs(os.path.dirname(CUSTOM_PRODUCTS_PATH), exist_ok=True)

    CUSTOM_CATEGORIES_PATH = os.path.join(app.root_path, "data", "custom_categories.json")
    DELETED_PRODUCTS_PATH = os.path.join(app.root_path, "data", "deleted_products.json")
    PHOTO_OVERRIDES_PATH = os.path.join(app.root_path, "data", "photo_overrides.json")
    os.makedirs(os.path.dirname(CUSTOM_CATEGORIES_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(DELETED_PRODUCTS_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(PHOTO_OVERRIDES_PATH), exist_ok=True)

    UPLOADS_DIR = os.path.join(app.root_path, "static", "uploads")
    os.makedirs(UPLOADS_DIR, exist_ok=True)

    # -------------------------
    # Digital goods (downloads after payment)
    # -------------------------
    DIGITAL_GOODS_DIR = os.path.join(app.root_path, "digital_goods")
    DIGITAL_MANIFEST = os.path.join(DIGITAL_GOODS_DIR, "manifest.json")
    DOWNLOAD_TTL_SECONDS = int(os.getenv("DOWNLOAD_TTL_SECONDS", "604800"))  # 7 days

    # Custom product files must NOT be served from /static (otherwise they are downloadable without payment).
    # We store them under DIGITAL_GOODS_DIR and serve only through /download/<token>.
    CUSTOM_DIGITAL_DIR = os.path.join(DIGITAL_GOODS_DIR, "custom_uploads")
    os.makedirs(CUSTOM_DIGITAL_DIR, exist_ok=True)

    def _serializer() -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(app.secret_key, salt="downloads-v1")

    def load_manifest() -> Dict[str, Any]:
        """Load digital manifest mapping product_id -> file or list of files.

        Example:
          {
            "default": "00 DocuBeauty produkty.zip",
            "06L8k": "LAMINACJA BRWI - dokumenty - CANVA.zip",
            "bundle": "00 DocuBeauty produkty.zip"
          }
        """
        if os.path.exists(DIGITAL_MANIFEST):
            try:
                with open(DIGITAL_MANIFEST, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        return {}

    def resolve_files_for_products(product_ids: List[str]) -> Tuple[List[str], Optional[str]]:
        """Return (files, bundle_file). Paths are relative to DIGITAL_GOODS_DIR."""
        manifest = load_manifest()
        default_file = manifest.get("default") or ""
        bundle_file = manifest.get("bundle") or None

        files: List[str] = []
        for pid in product_ids:
            entry = manifest.get(pid, default_file)
            if not entry:
                continue
            if isinstance(entry, list):
                for x in entry:
                    if isinstance(x, str) and x.strip():
                        files.append(x.strip())
            elif isinstance(entry, str) and entry.strip():
                files.append(entry.strip())

        # de-dup while preserving order
        seen = set()
        uniq: List[str] = []
        for f in files:
            if f not in seen:
                uniq.append(f)
                seen.add(f)

        bundle = bundle_file.strip() if isinstance(bundle_file, str) and bundle_file.strip() else None
        return uniq, bundle

    def make_download_token(session_id: str, payload_or_relpath) -> str:
        """
        Create signed download token.
    
        Backward-compatible:
          - if payload_or_relpath is str -> treated as relpath under DIGITAL_GOODS_DIR (stored as key "p")
          - if payload_or_relpath is dict -> stored as-is (must include "sid", auto-filled if missing)
        """
        if isinstance(payload_or_relpath, str):
            payload = {"sid": session_id, "p": payload_or_relpath}
        elif isinstance(payload_or_relpath, dict):
            payload = dict(payload_or_relpath)
            payload.setdefault("sid", session_id)
        else:
            payload = {"sid": session_id}
        return _serializer().dumps(payload)

    def read_download_token(token: str) -> Dict[str, str]:
        return _serializer().loads(token, max_age=DOWNLOAD_TTL_SECONDS)

    def verify_paid_checkout_session(session_id: str) -> stripe.checkout.Session:
        """Verify Stripe Checkout session is paid; returns the session object."""
        try:
            cs = stripe.checkout.Session.retrieve(session_id)
        except Exception:
            abort(400, "Invalid session_id")
        if getattr(cs, "payment_status", None) != "paid":
            abort(403, "Payment not completed")
        return cs

    def safe_goods_path(relpath: str) -> str:
        """Return absolute path under DIGITAL_GOODS_DIR, preventing path traversal."""
        rel = (relpath or "").replace("\\", "/").lstrip("/")
        if ".." in rel.split("/"):
            abort(400, "Invalid file path")
        abs_path = os.path.join(DIGITAL_GOODS_DIR, rel)
        base = os.path.abspath(DIGITAL_GOODS_DIR)
        ap = os.path.abspath(abs_path)
        if not ap.startswith(base):
            abort(400, "Invalid file path")
        return abs_path

    def _move_to_custom_digital_storage(static_rel: str) -> str:
        """Move a file from static/uploads/... into DIGITAL_GOODS_DIR/custom_uploads/ and return new relpath."""
        rel = (static_rel or "").replace("\\", "/").lstrip("/")
        # Typical values: "uploads/<name>.pdf" stored under static.
        if rel.startswith("static/"):
            rel = rel[len("static/"):]
        if not rel.startswith("uploads/"):
            return ""

        src = os.path.join(app.static_folder, rel)
        if not os.path.isfile(src):
            return ""

        ext = os.path.splitext(src)[1].lower() or ""
        new_name = f"{uuid.uuid4().hex}{ext}"
        dst = os.path.join(CUSTOM_DIGITAL_DIR, new_name)
        try:
            shutil.move(src, dst)
        except Exception:
            return ""

        # relpath under DIGITAL_GOODS_DIR
        return f"custom_uploads/{new_name}"

    # -------------------------
    # Image helpers
    # -------------------------
    PLACEHOLDER_THUMB = "img/placeholder.svg"

    def thumb_url(p: Product) -> str:
        """Return a usable thumbnail URL (never empty).

        - If product has an image and it exists on disk, return its URL.
        - Otherwise, return a built-in placeholder.
        """
        thumb = p.primary_image() or ""
        if thumb:
            if p.image_source == "media":
                fs = os.path.join(EXPORT_IMAGES, thumb)
                if os.path.exists(fs):
                    return url_for("media", filename=thumb)
            else:
                fs = os.path.join(app.static_folder, thumb)
                if os.path.exists(fs):
                    return url_for("static", filename=thumb)
        return url_for("static", filename=PLACEHOLDER_THUMB)

    # expose to templates
    app.add_template_global(thumb_url, name="thumb_url")

    # -------------------------
    # Data loading
    # -------------------------

    # -------------------------
    # Price overrides (simple JSON {product_id: price})
    # -------------------------
    def load_price_overrides() -> Dict[str, float]:
        try:
            with open(PRICE_OVERRIDES_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}
        clean: Dict[str, float] = {}
        for pid, val in raw.items():
            try:
                clean[str(pid)] = float(val)
            except Exception:
                continue
        return clean

    def save_price_overrides(data: Dict[str, float]) -> None:
        tmp_path = PRICE_OVERRIDES_PATH + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, PRICE_OVERRIDES_PATH)
        except Exception:
            # Best-effort; ignore disk errors in runtime.
            pass

    def apply_price_overrides(products: List[Product], overrides: Dict[str, float]) -> List[Product]:
        if not overrides:
            return products
        try:
            from dataclasses import replace as _dc_replace
        except Exception:
            _dc_replace = None
        result: List[Product] = []
        for p in products:
            new_price = overrides.get(p.id)
            if new_price is not None and _dc_replace is not None:
                try:
                    result.append(_dc_replace(p, price_pln=float(new_price)))
                    continue
                except Exception:
                    pass
            result.append(p)
        return result

    # -------------------------
    # Description overrides (simple JSON {product_id: description})
    # -------------------------
    def load_description_overrides() -> Dict[str, str]:
        try:
            with open(DESCRIPTION_OVERRIDES_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}
        clean: Dict[str, str] = {}
        for pid, val in raw.items():
            if not isinstance(pid, str):
                pid = str(pid)
            try:
                text_val = str(val)
            except Exception:
                continue
            clean[pid] = text_val
        return clean

    def save_description_overrides(data: Dict[str, str]) -> None:
        tmp_path = DESCRIPTION_OVERRIDES_PATH + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, DESCRIPTION_OVERRIDES_PATH)
        except Exception:
            pass

    # -------------------------
    # Title overrides (simple JSON {product_id: title})
    # -------------------------
    def load_title_overrides() -> Dict[str, str]:
        try:
            with open(TITLE_OVERRIDES_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}
        clean: Dict[str, str] = {}
        if isinstance(raw, dict):
            for pid, val in raw.items():
                try:
                    key = str(pid)
                    title = str(val).strip()
                except Exception:
                    continue
                if title:
                    clean[key] = title
        return clean

    def save_title_overrides(data: Dict[str, str]) -> None:
        tmp_path = TITLE_OVERRIDES_PATH + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, TITLE_OVERRIDES_PATH)
        except Exception:
            pass

    def apply_title_overrides(products: List[Product], overrides: Dict[str, str]) -> List[Product]:
        if not overrides:
            return products
        try:
            from dataclasses import replace as _dc_replace
        except Exception:
            _dc_replace = None
        result: List[Product] = []
        for p in products:
            new_title = overrides.get(p.id)
            if new_title and _dc_replace is not None:
                try:
                    result.append(_dc_replace(p, title=str(new_title)))
                    continue
                except Exception:
                    pass
            result.append(p)
        return result

    def load_category_overrides() -> Dict[str, str]:
        try:
            with open(CATEGORY_OVERRIDES_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}
        clean: Dict[str, str] = {}
        if isinstance(raw, dict):
            for pid, val in raw.items():
                try:
                    key = str(pid)
                    clean[key] = str(val)
                except Exception:
                    continue
        return clean

    def save_category_overrides(data: Dict[str, str]) -> None:
        tmp_path = CATEGORY_OVERRIDES_PATH + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, CATEGORY_OVERRIDES_PATH)
        except Exception:
            pass

    def apply_category_overrides(products: List[Product], overrides: Dict[str, str]) -> List[Product]:
        if not overrides:
            return products
        try:
            from dataclasses import replace as _dc_replace
        except Exception:
            _dc_replace = None
        if not _dc_replace:
            return products
        result: List[Product] = []
        for p in products:
            new_category = overrides.get(p.id)
            if new_category is not None:
                try:
                    result.append(_dc_replace(p, category=str(new_category)))
                    continue
                except Exception:
                    pass
            result.append(p)
        return result


    def _load_json(path: str, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except Exception:
            return default

    def _save_json(path: str, data) -> None:
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            pass

    def load_custom_categories() -> List[str]:
        raw = _load_json(CUSTOM_CATEGORIES_PATH, [])
        if not isinstance(raw, list):
            return []
        out: List[str] = []
        seen: set[str] = set()
        for x in raw:
            try:
                name = str(x).strip()
            except Exception:
                continue
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
        return out

    def save_custom_categories(items: List[str]) -> None:
        _save_json(CUSTOM_CATEGORIES_PATH, items)

    def load_deleted_products() -> set[str]:
        raw = _load_json(DELETED_PRODUCTS_PATH, [])
        out: set[str] = set()
        if isinstance(raw, list):
            for x in raw:
                try:
                    pid = str(x).strip()
                except Exception:
                    continue
                if pid:
                    out.add(pid)
        elif isinstance(raw, dict):
            # backward compatible: {id: true}
            for k, v in raw.items():
                if v:
                    out.add(str(k))
        return out

    def save_deleted_products(items: set[str]) -> None:
        _save_json(DELETED_PRODUCTS_PATH, sorted(items))

    def load_photo_overrides() -> Dict[str, str]:
        raw = _load_json(PHOTO_OVERRIDES_PATH, {})
        if not isinstance(raw, dict):
            return {}
        out: Dict[str, str] = {}
        for k, v in raw.items():
            try:
                pid = str(k).strip()
                rel = str(v).strip()
            except Exception:
                continue
            if pid and rel:
                out[pid] = rel
        return out

    def save_photo_overrides(items: Dict[str, str]) -> None:
        _save_json(PHOTO_OVERRIDES_PATH, items)

    def apply_photo_overrides(products: List[Product], overrides: Dict[str, str]) -> List[Product]:
        if not overrides:
            return products
        try:
            from dataclasses import replace as _dc_replace
        except Exception:
            _dc_replace = None
        if not _dc_replace:
            return products
        out: List[Product] = []
        for p in products:
            rel = overrides.get(p.id)
            if rel:
                try:
                    out.append(_dc_replace(p, images=(rel,), image_source="static"))
                    continue
                except Exception:
                    pass
            out.append(p)
        return out

    def apply_deleted_products(products: List[Product], deleted: set[str]) -> List[Product]:
        if not deleted:
            return products
        return [p for p in products if str(p.id) not in deleted]

    def load_custom_products() -> List[Product]:
        # One-time best-effort migration: move downloadable files out of /static/uploads
        # into DIGITAL_GOODS_DIR/custom_uploads so they can't be downloaded without payment.
        def _migrate_if_needed() -> None:
            try:
                with open(CUSTOM_PRODUCTS_PATH, "r", encoding="utf-8") as f:
                    raw_local = json.load(f) or []
            except FileNotFoundError:
                return
            except Exception:
                return
            if not isinstance(raw_local, list):
                return

            changed = False

            for rec in raw_local:
                if not isinstance(rec, dict):
                    continue
                rel = str(rec.get("file") or "").strip().replace("\\", "/")
                if not rel:
                    continue

                # Already protected
                if rel.startswith("custom_uploads/"):
                    continue

                # Legacy: stored under static/uploads
                fn = ""
                if rel.startswith("uploads/"):
                    fn = rel.split("/", 1)[1]
                elif rel.startswith("static/uploads/"):
                    fn = rel.split("static/uploads/", 1)[1]
                elif rel.startswith("/static/uploads/"):
                    fn = rel.split("/static/uploads/", 1)[1]
                if not fn:
                    continue

                old_abs = os.path.join(app.static_folder, "uploads", os.path.basename(fn))
                if not os.path.isfile(old_abs):
                    continue

                ext = os.path.splitext(old_abs)[1].lower()
                new_name = f"{uuid.uuid4().hex}{ext}"
                new_abs = os.path.join(CUSTOM_DIGITAL_DIR, new_name)
                try:
                    os.replace(old_abs, new_abs)
                except Exception:
                    continue

                rec["file"] = f"custom_uploads/{new_name}"
                changed = True

            if changed:
                try:
                    save_custom_products(raw_local)
                except Exception:
                    pass

        _migrate_if_needed()

        try:
            with open(CUSTOM_PRODUCTS_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f) or []
        except FileNotFoundError:
            return []
        except Exception:
            return []

        items: List[Product] = []
        if not isinstance(raw, list):
            return items

        for x in raw:
            if not isinstance(x, dict):
                continue
            pid = str(x.get("id") or "").strip()
            title = str(x.get("title") or "").strip()
            if not pid or not title:
                continue

            desc = str(x.get("description") or "").strip()
            try:
                price = float(x.get("price_pln") or 0.0)
            except Exception:
                price = 0.0

            img = str(x.get("image") or "").strip()
            dl = str(x.get("file") or "").strip()
            category = str(x.get("category") or "Produkty").strip() or "Produkty"

            # Optional: bind a custom product to a DocuBeauty category (stable key).
            # If missing, infer it from the category name when possible.
            docu_cat_slug = str(x.get("docu_cat_slug") or "").strip()
            if not docu_cat_slug:
                try:
                    inferred = slugify(category)
                    if inferred in CATEGORY_META:
                        docu_cat_slug = inferred
                except Exception:
                    docu_cat_slug = ""

            items.append(
                Product(
                    id=pid,
                    title=title,
                    category=category,
                    category_url="",
                    price_pln=price,
                    description=desc,
                    images=(img,) if img else tuple(),
                    image_source="static",
                    source_url="",
                    download_file=dl,
                    docu_cat_slug=docu_cat_slug,
                )
            )
        return items

    def build_custom_category_cards(
        custom_products: List[Product],
        blocked_slugs: Optional[set[str]] = None,
        blocked_names: Optional[set[str]] = None,
    ) -> List[Product]:
        """Build navigation-only cards for custom categories.

        In DocuBeauty mode the main /shop page shows navigation cards (packages).
        Custom categories should behave similarly (click -> filtered catalog view),
        and can have an independent category thumbnail via photo override key: cat:<slug>.

        IMPORTANT:
        If a custom product uses a category name that already exists as a DocuBeauty category,
        we must NOT create a duplicate custom category card.
        """
        # Collect names from explicit categories list + categories used by custom products.
        names: List[str] = []
        seen: set[str] = set()
        for n in load_custom_categories():
            nn = (n or "").strip()
            if nn and nn.lower() not in seen:
                names.append(nn)
                seen.add(nn.lower())
        for p in custom_products:
            nn = (p.category or "").strip()
            if nn and nn.lower() not in seen:
                names.append(nn)
                seen.add(nn.lower())

        cards: List[Product] = []
        if not names:
            return cards

        photo_overrides = load_photo_overrides()

        def _infer_source(rel_path: str) -> str:
            rel_path = (rel_path or "").strip()
            if not rel_path or rel_path.startswith("http"):
                return "static"
            # Images uploaded from /edit are stored under /static/uploads/...
            if rel_path.startswith("uploads/") or rel_path.startswith("images/") or rel_path.startswith("img/"):
                return "static"
            # Everything else is assumed to be served from /media/<filename>
            return "media"

        # Choose a default image (first product image) if no override exists.
        by_cat: Dict[str, List[Product]] = {}
        for p in custom_products:
            by_cat.setdefault((p.category or "").strip().lower(), []).append(p)

        blocked_names_lc = {str(x).strip().lower() for x in (blocked_names or set()) if str(x).strip()}

        for name in names:
            name_lc = name.strip().lower()
            slug = slugify(name)

            if name_lc in blocked_names_lc:
                # This category is already represented by a DocuBeauty category card (dbcat:...).
                continue
            if blocked_slugs and slug in blocked_slugs:
                # This category is already represented by a DocuBeauty category card (dbcat:<slug>).
                continue

            pid = f"cat:{slug}"

            override_img = str(photo_overrides.get(pid) or "").strip()
            default_img = ""
            img_source = "static"
            if override_img:
                default_img = override_img
                img_source = _infer_source(override_img)
            else:
                # Prefer an independent static category card image if present.
                # This prevents the category thumbnail from "following" the newest/first product image.
                card_rel = f"cards/{slug}.png"
                card_abs = os.path.join(app.static_folder, card_rel.replace("/", os.sep))
                if os.path.exists(card_abs):
                    default_img = card_rel
                    img_source = "static"
                else:
                    prods = by_cat.get(name_lc, [])
                    if prods:
                        # Pick the first product that actually has a hero image.
                        hero = ""
                        hero_src = "static"
                        for pp in prods:
                            h = pp.primary_image() or ""
                            if h:
                                hero = h
                                hero_src = str(getattr(pp, "image_source", "static") or "static")
                                break
                        if hero:
                            default_img = hero
                            img_source = hero_src

            cards.append(
                Product(
                    id=pid,
                    title=name,
                    category="",  # navigation-only
                    category_url="",
                    price_pln=0.0,
                    description="",
                    images=(default_img,) if default_img else tuple(),
                    image_source=img_source,
                    source_url="",
                )
            )
        return cards

        photo_overrides = load_photo_overrides()

        # Choose a default image (first product image) if no override exists.
        by_cat: Dict[str, List[Product]] = {}
        for p in custom_products:
            by_cat.setdefault((p.category or "").strip().lower(), []).append(p)

        for name in names:
            slug = slugify(name)

            if blocked_slugs and slug in blocked_slugs:
                # This category is already represented by a DocuBeauty category card (dbcat:<slug>).
                # Let that card handle navigation and thumbnail overrides.
                continue

            pid = f"cat:{slug}"

            override_img = str(photo_overrides.get(pid) or "").strip()
            default_img = ""
            if override_img:
                default_img = override_img
            else:
                prods = by_cat.get(name.lower(), [])
                if prods:
                    hero = prods[0].primary_image() or ""
                    if hero and prods[0].image_source == "static":
                        default_img = hero

            cards.append(
                Product(
                    id=pid,
                    title=name,
                    category="",  # navigation-only
                    category_url="",
                    price_pln=0.0,
                    description="",
                    images=(default_img,) if default_img else tuple(),
                    image_source="static",
                    source_url="",
                )
            )
        return cards

    def load_custom_products_raw() -> list:
        """Load custom_products.json as raw list[dict] for in-place edits."""
        try:
            with open(CUSTOM_PRODUCTS_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f) or []
        except FileNotFoundError:
            return []
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        out = []
        for x in raw:
            if isinstance(x, dict):
                out.append(x)
        return out

    def save_custom_products(raw: List[Dict[str, Any]]) -> None:
        tmp_path = CUSTOM_PRODUCTS_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CUSTOM_PRODUCTS_PATH)

    def append_custom_product(record: Dict[str, Any]) -> None:
        try:
            existing = []
            if os.path.exists(CUSTOM_PRODUCTS_PATH):
                with open(CUSTOM_PRODUCTS_PATH, "r", encoding="utf-8") as f:
                    existing = json.load(f) or []
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
        existing.append(record)
        save_custom_products(existing)


    def apply_description_overrides(products: List[Product], overrides: Dict[str, str]) -> List[Product]:
        if not overrides and all((p.description or "") for p in products):
            # Nothing to change
            return products
        try:
            from dataclasses import replace as _dc_replace
        except Exception:
            _dc_replace = None
        result: List[Product] = []
        for p in products:
            base_desc = (p.description or "").strip()
            override_val = overrides.get(p.id)
            override_val = override_val if override_val is None or isinstance(override_val, str) else str(override_val)
            final_desc = None
            if override_val is not None and override_val.strip():
                final_desc = override_val.strip()
            elif base_desc:
                final_desc = base_desc
            else:
                # fallback: use product title when nothing else is defined
                final_desc = p.title
            if final_desc == base_desc or _dc_replace is None:
                # keep original if unchanged or cannot replace
                if not base_desc and final_desc and final_desc != base_desc and _dc_replace is not None:
                    try:
                        result.append(_dc_replace(p, description=final_desc))
                        continue
                    except Exception:
                        pass
                result.append(p)
            else:
                try:
                    result.append(_dc_replace(p, description=final_desc))
                except Exception:
                    result.append(p)
        return result




    def load_products() -> List[Product]:
        items: List[Product] = []

        price_overrides = load_price_overrides()
        desc_overrides = load_description_overrides()
        title_overrides = load_title_overrides()
        category_overrides = load_category_overrides()
        photo_overrides = load_photo_overrides()
        deleted_ids = load_deleted_products()

        # Prefer DocuBeauty catalog if available
        docu_products = build_docubeauty_products(app.root_path)
        if docu_products:
            custom_prods = list(load_custom_products())

            # IMPORTANT BUGFIX:
            # Category navigation cards may use the first product image in that category as a
            # thumbnail. In the editor, product photos are commonly stored via photo_overrides.json.
            # Previously we built category cards BEFORE applying photo overrides to custom products,
            # which caused the category card to render with an empty/placeholder image (looks like a
            # "duplicate" blank tile) right after uploading/changing photos.
            #
            # Apply photo overrides to a temporary copy of custom products so category thumbnails can
            # pick up the latest overridden images. We still apply overrides to the final combined
            # items list further below (idempotent).
            custom_prods_for_cards = apply_photo_overrides(list(custom_prods), photo_overrides)
            # Add navigation cards for custom categories (click -> /shop?category=...)
            # so new categories behave like the built-in DocuBeauty packages.
            # IMPORTANT: do not create a duplicate custom category card if a DocuBeauty
            # category card with the same slug already exists. Otherwise the duplicate
            # can appear to "take over" the category thumbnail (fallback = first product).
            docu_slugs: set[str] = {p.docu_cat_slug for p in docu_products if p.docu_cat_slug and not p.docu_item_id}
            docu_names: set[str] = {str(p.title).strip().lower() for p in docu_products if p.docu_cat_slug and not p.docu_item_id}
            def dedupe_category_cards(all_items: List[Product]) -> List[Product]:
                """Remove duplicate navigation cards for the same category in DocuBeauty mode.

                We may end up with both:
                - DocuBeauty category card: id 'dbcat:<slug>' (docu_cat_slug set, docu_item_id empty)
                - Custom category card:   id 'cat:<slug>'

                When admin uploads a category thumbnail, the override may be stored for 'cat:<slug>'.
                If both cards exist, /shop shows two versions of the same category (often one empty).
                This function keeps a single card per category title-slug and, when needed, transfers
                the best thumbnail from the discarded card to the kept one.
                """
                try:
                    from dataclasses import replace as _dc_replace
                except Exception:
                    _dc_replace = None

                def _is_cat_card(p: Product) -> bool:
                    return bool((p.docu_cat_slug and not p.docu_item_id) or str(p.id).startswith("cat:"))

                winners: Dict[str, Product] = {}
                losers: set[str] = set()

                for p in all_items:
                    if not _is_cat_card(p):
                        continue
                    key = slugify(str(p.title or ""))
                    if not key:
                        continue
                    prev = winners.get(key)
                    if not prev:
                        winners[key] = p
                        continue

                    # Prefer DocuBeauty card over custom 'cat:' card.
                    prev_is_db = bool(prev.docu_cat_slug and not prev.docu_item_id)
                    cur_is_db = bool(p.docu_cat_slug and not p.docu_item_id)

                    keep = prev
                    drop = p
                    if cur_is_db and not prev_is_db:
                        keep, drop = p, prev
                    # If the kept card has no usable image but the dropped one does, transfer it.
                    keep_img = keep.primary_image() or ""
                    drop_img = drop.primary_image() or ""

                    # If an admin uploaded a custom thumbnail for a category, it is often stored
                    # on the custom card id (cat:<slug>). In that case, prefer the custom image
                    # even if the DocuBeauty card already has a default preview.
                    prefer_drop = bool(
                        str(drop.id).startswith("cat:")
                        and drop_img
                        and not drop_img.endswith("cards/_placeholder.png")
                    )

                    if _dc_replace is not None and drop_img and (
                        prefer_drop or (not keep_img or keep_img.endswith("cards/_placeholder.png"))
                    ):
                        try:
                            keep = _dc_replace(
                                keep,
                                images=(drop_img,),
                                image_source=getattr(drop, "image_source", "static") or "static",
                            )
                        except Exception:
                            pass

                    winners[key] = keep
                    losers.add(str(drop.id))

                if not losers:
                    return all_items

                out: List[Product] = []
                for p in all_items:
                    if str(p.id) in losers:
                        continue
                    # If this is a category card and we updated the winner instance, replace it.
                    if _is_cat_card(p):
                        key = slugify(str(p.title or ""))
                        w = winners.get(key)
                        if w and str(w.id) == str(p.id) and w is not p:
                            out.append(w)
                            continue
                    out.append(p)

                # Ensure unique IDs in case replacements introduced duplicates.
                seen_ids: set[str] = set()
                final: List[Product] = []
                for p in out:
                    if str(p.id) in seen_ids:
                        continue
                    seen_ids.add(str(p.id))
                    final.append(p)
                return final


            custom_cat_cards = build_custom_category_cards(custom_prods_for_cards, blocked_slugs=docu_slugs, blocked_names=docu_names)
            items = list(docu_products) + custom_cat_cards + custom_prods
            items = apply_title_overrides(items, title_overrides)
            items = apply_price_overrides(items, price_overrides)
            items = apply_description_overrides(items, desc_overrides)
            items = apply_category_overrides(items, category_overrides)
            items = apply_photo_overrides(items, photo_overrides)
            items = apply_deleted_products(items, deleted_ids)
            items = dedupe_category_cards(items)
            return items

        # Export from parser (1cart)
        if os.path.exists(EXPORT_PRODUCTS):
            try:
                with open(EXPORT_PRODUCTS, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                raw = []

            if isinstance(raw, list):
                for x in raw:
                    if not isinstance(x, dict):
                        continue
                    pid = str(x.get("product_id", "")).strip()
                    title = str(x.get("title", "")).strip()
                    if not pid or not title:
                        continue

                    category = str(x.get("category_name", "Bez kategorii")).strip() or "Bez kategorii"
                    category_url = str(x.get("category_url", "")).strip()
                    description = str(x.get("description") or "").strip()

                    img_files = [str(p).replace("\\", "/") for p in (x.get("image_files") or [])]
                    rel_imgs: List[str] = []
                    for pth in img_files:
                        pth = pth.lstrip("/")
                        if pth.startswith("images/"):
                            pth = pth[len("images/"):]
                        if pth:
                            rel_imgs.append(pth)

                    try:
                        price_pln = float(x.get("price_pln") or 0.0)
                    except Exception:
                        price_pln = 0.0

                    items.append(
                        Product(
                            id=pid,
                            title=title,
                            category=category,
                            category_url=category_url,
                            price_pln=price_pln,
                            description=description,
                            images=tuple(rel_imgs),
                            image_source="media",
                            source_url=str(x.get("url", "")).strip(),
                        )
                    )

        # Fallback demo
        if not items and os.path.exists(FALLBACK_PRODUCTS):
            try:
                with open(FALLBACK_PRODUCTS, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                raw = []

            if isinstance(raw, list):
                for x in raw:
                    if not isinstance(x, dict):
                        continue
                    pid = str(x.get("id", "")).strip()
                    title = str(x.get("name", "")).strip()
                    if not pid or not title:
                        continue
                    try:
                        price_pln = float(x.get("price") or 0.0)
                    except Exception:
                        price_pln = 0.0

                    img = str(x.get("image", "")).strip()
                    items.append(
                        Product(
                            id=pid,
                            title=title,
                            category=str(x.get("category", "Bez kategorii")).strip() or "Bez kategorii",
                            category_url="",
                            price_pln=price_pln,
                            description=str(x.get("description", "")).strip(),
                            images=(img,) if img else tuple(),
                            image_source="static",
                            source_url="",
                        )
                    )

        # Always include custom products
        items.extend(load_custom_products())

        items = apply_title_overrides(items, title_overrides)
        items = apply_price_overrides(items, price_overrides)
        items = apply_description_overrides(items, desc_overrides)
        items = apply_category_overrides(items, category_overrides)
        items = apply_photo_overrides(items, photo_overrides)
        items = apply_deleted_products(items, deleted_ids)
        return items

    def get_catalog() -> List[Product]:
        return load_products()

    def get_categories(catalog: List[Product]) -> List[str]:
        cats = {p.category for p in catalog if (p.category or '').strip()}
        for c in load_custom_categories():
            cats.add(c)
        return sorted(cats, key=lambda x: x.lower())

    # -------------------------
    # Cart
    # -------------------------
    def get_cart() -> Dict[str, int]:
        cart = session.get("cart", {})
        if not isinstance(cart, dict):
            cart = {}
        clean: Dict[str, int] = {}
        for k, v in cart.items():
            try:
                qty = int(v)
            except Exception:
                continue
            if qty > 0:
                clean[str(k)] = min(qty, 99)
        session["cart"] = clean
        return clean

    def cart_summary(catalog: List[Product]) -> Dict[str, Any]:
        cart = get_cart()
        by_id = {p.id: p for p in catalog}

        # Count only items that still exist in the catalog.
        # This prevents showing "1" when the cart contains stale/unknown product IDs.
        valid_cart: Dict[str, int] = {}
        count = 0
        total = 0.0

        for pid, qty in cart.items():
            p = by_id.get(pid)
            if not p:
                continue
            valid_cart[pid] = qty
            count += qty
            total += p.unit_price_for_cart() * qty

        # Persist only valid items back to session
        session["cart"] = valid_cart
        return {"count": count, "total": total}

    # -------------------------
    # Cache headers
    # -------------------------
    @app.after_request
    def add_no_cache_headers(resp):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    # -------------------------
    # Globals for templates
    # -------------------------
    @app.context_processor
    def inject_globals():
        catalog = get_catalog()
        summ = cart_summary(catalog)
        return dict(
            cart_count=summ["count"],
            cart_total=format_pln(summ["total"]),
            categories=get_categories(catalog),
            static_version=STATIC_VERSION,
        )

    # -------------------------
    # Media serving (exported images)
    # -------------------------
    @app.get("/media/<path:filename>")
    def media(filename: str):
        # If a file is missing, return a safe placeholder instead of a broken image.
        fs = os.path.join(EXPORT_IMAGES, filename)
        if os.path.exists(fs):
            return send_from_directory(EXPORT_IMAGES, filename)
        return send_file(
            os.path.join(app.static_folder, PLACEHOLDER_THUMB),
            mimetype="image/svg+xml",
        )

    # -------------------------
    # Routes
    # -------------------------
    @app.get("/")
    def home():
        return redirect(url_for("shop"))

    @app.get("/o-nas")
    def about():
        return render_template(
            "index.html",
            view="about",
            title="O nas – profesjonalne produkty cyfrowe dla branży beauty",
        )

    @app.get("/kontakt")
    def contact():
        return render_template(
            "index.html",
            view="contact",
            title="Kontakt",
        )

    @app.get("/shop")
    def shop():
        catalog = get_catalog()

        is_docu_mode = any(p.docu_cat_slug for p in catalog)

        q = (request.args.get("q") or "").strip()
        cat = (request.args.get("category") or "").strip()  # slug
        sort = (request.args.get("sort") or "").strip()
        page = request.args.get("page", "1")

        try:
            page_i = max(1, int(page))
        except Exception:
            page_i = 1

        # ---- Per-page: desktop vs mobile ----
        # Desktop = 24 (как было)
        # Mobile (телефон) = 12 (оптимально для 1 колонки)
        per_page = 12 if is_mobile_request() else 24

        # Optional manual override if you ever need it:
        # /shop?per_page=9
        per_page_arg = (request.args.get("per_page") or "").strip()
        if per_page_arg:
            try:
                v = int(per_page_arg)
                if 1 <= v <= 60:
                    per_page = v
            except Exception:
                pass
        # Category menu source:
        # - In DocuBeauty mode: categories are navigation cards (dbcat:...) + custom category cards (cat:...).
        # - Otherwise: categories are derived from product.category.
        if is_docu_mode:
            menu_source = [p for p in catalog if ((p.docu_cat_slug and not p.docu_item_id) or p.id.startswith("cat:"))]
        else:
            menu_source = catalog

        filtered = catalog

        # DocuBeauty default view: show only category cards unless a category is selected.
        if is_docu_mode and not cat:
            filtered = list(menu_source)

        if cat:
            selected_docu_slug = ""
            if is_docu_mode:
                try:
                    for cp in menu_source:
                        if cp.docu_cat_slug and not cp.docu_item_id and slugify(cp.title) == cat:
                            selected_docu_slug = cp.docu_cat_slug
                            break
                except Exception:
                    selected_docu_slug = ""

            def _cat_match(p: Product) -> bool:
                # DocuBeauty category cards (dbcat:...) and custom category cards (cat:...) are
                # matched by their title slug.
                if (p.docu_cat_slug and not p.docu_item_id) or p.id.startswith("cat:"):
                    return slugify(p.title) == cat
                # DocuBeauty items: match the selected DocuBeauty slug when available.
                if selected_docu_slug and p.docu_cat_slug:
                    return p.docu_cat_slug == selected_docu_slug
                # Custom/regular products fall back to matching by category name.
                # Additionally accept docu-cat slug stored on custom products.
                if selected_docu_slug and p.id.startswith("custom:") and p.docu_cat_slug:
                    return p.docu_cat_slug == selected_docu_slug
                return slugify(p.category) == cat

            filtered = [p for p in filtered if _cat_match(p)]

            # In DocuBeauty mode when a category is selected, show only products/items inside it
            # (hide the category card itself).
            if is_docu_mode:
                filtered = [p for p in filtered if not ((p.docu_cat_slug and not p.docu_item_id) or p.id.startswith("cat:"))]

        if q:
            ql = q.lower()
            filtered = [
                p
                for p in filtered
                if ql in p.title.lower() or ql in (p.description or "").lower()
            ]

        if sort == "price_asc":
            filtered = sorted(filtered, key=lambda p: (p.price_pln, p.title.lower()))
        elif sort == "price_desc":
            filtered = sorted(filtered, key=lambda p: (-p.price_pln, p.title.lower()))
        else:
            filtered = sorted(filtered, key=lambda p: p.title.lower())


        # Build category menu (unique categories for left sidebar / mobile strip)
        menu_categories: List[Dict[str, str]] = []
        seen_slugs: set[str] = set()
        for p in menu_source:
            if (p.docu_cat_slug and not p.docu_item_id) or p.id.startswith("cat:"):
                label = p.title
            else:
                label = p.category
            slug = slugify(label)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            menu_categories.append({"label": label, "slug": slug})

        total = len(filtered)
        pages = max(1, math.ceil(total / per_page))
        page_i = min(page_i, pages)

        start = (page_i - 1) * per_page
        end = start + per_page
        page_items = filtered[start:end]

        window = 3
        lo = max(1, page_i - window)
        hi = min(pages, page_i + window)
        page_range = list(range(lo, hi + 1))

        return render_template(
            "index.html",
            view="shop",
            title="Produkty",
            products=page_items,
            q=q,
            active_category=cat,
            sort=sort,
            page=page_i,
            pages=pages,
            per_page=per_page,
            total=total,
            page_range=page_range,
            categories=menu_categories,
        )

    @app.get("/api/search_suggest")
    def search_suggest():
        catalog = get_catalog()
        q = (request.args.get("q") or "").strip().lower()

        # Suggestions should appear immediately while typing.
        if len(q) < 1:
            return jsonify({"products": [], "categories": []})

        prod_matches = []
        for p in catalog:
            # Exclude navigation-only category cards from product suggestions.
            if p.id.startswith("cat:") or (p.docu_cat_slug and not p.docu_item_id) or p.id.startswith("dbcat:"):
                continue

            hay = f"{p.title} {p.category} {getattr(p, 'description', '')}".lower()
            if q in hay:
                thumb_url_str = thumb_url(p)
                prod_matches.append(
                    {
                        "id": p.id,
                        "title": p.title,
                        "category": p.category,
                        "category_slug": slugify(p.category),
                        "price": p.display_price(),
                        "thumb": thumb_url_str,
                    }
                )
            if len(prod_matches) >= 8:
                break

        cat_counts: Dict[str, int] = {}
        for p in catalog:
            if p.id.startswith("cat:") or (p.docu_cat_slug and not p.docu_item_id) or p.id.startswith("dbcat:"):
                continue
            cat_counts[p.category] = cat_counts.get(p.category, 0) + 1

        cat_matches = []
        for name, cnt in sorted(cat_counts.items(), key=lambda x: x[0].lower()):
            if q in name.lower():
                cat_matches.append({"name": name, "slug": slugify(name), "count": cnt})
            if len(cat_matches) >= 6:
                break

        return jsonify({"products": prod_matches, "categories": cat_matches})

    @app.get("/product/<pid>")
    def product(pid: str):
        catalog = get_catalog()
        # Used to fully hide deleted products from DocuBeauty category pages and deep links.
        deleted_ids = load_deleted_products()
        p = next((x for x in catalog if x.id == pid), None)
        if not p:
            return redirect(url_for("shop"))

        # Navigation-only custom category cards.
        if pid.startswith("cat:"):
            slug = pid.split(":", 1)[1].strip()
            return redirect(url_for("shop", category=slug))

        # DocuBeauty item-product: render a clean product page for a single file.
        if p.docu_cat_slug and p.docu_item_id:
            # If an item was deleted in admin, treat it as non-existent.
            if f"dbitem:{p.docu_cat_slug}:{p.docu_item_id}" in deleted_ids:
                return redirect(url_for("shop"))
            cat = get_docubeauty_category(app.root_path, p.docu_cat_slug)
            if not cat:
                return redirect(url_for("shop"))
            item = get_docubeauty_item_by_id(cat, p.docu_item_id)
            if not item:
                return redirect(url_for("shop"))

            # Ensure item page reflects overrides (title/description/photo) stored on Product.
            item = dict(item)

            # Prefer product thumbnail if available (e.g., after admin photo update).
            hero = p.primary_image()
            if hero and p.image_source == "media":
                item["thumb_url"] = url_for("media", filename=hero)
            elif hero and p.image_source == "static":
                item["thumb_rel"] = hero
            else:
                thumb_rel = f"cards/items/{p.docu_cat_slug}/{p.docu_item_id}.png"
                if os.path.exists(os.path.join(app.static_folder, thumb_rel)):
                    item["thumb_rel"] = thumb_rel

            # Ensure displayed category name can be renamed via overrides.
            docu_cat = dict(cat)
            if p.category:
                docu_cat["display_name"] = p.category

            return render_template(
                "index.html",
                view="docu_item",
                title=p.title,
                item=item,
                p=p,
                docu_cat=docu_cat,
            )

        # If this is a DocuBeauty category-product, load the included files to display on the page.
        docu_cat = None
        docu_items = []
        custom_in_docu_cat: List[Product] = []
        if p.docu_cat_slug and not p.docu_item_id:
            docu_cat = get_docubeauty_category(app.root_path, p.docu_cat_slug)
            if docu_cat:
                # Map file-id -> sellable product (price, cart id)
                item_product_by_id = {
                    x.docu_item_id: x
                    for x in catalog
                    if x.docu_cat_slug == p.docu_cat_slug and x.docu_item_id
                }
                raw_items = list_docubeauty_items_for_category(docu_cat)
                # attach optional preview card (if exists)
                for it in raw_items:
                    it = dict(it)
                    item_id_str = str(it.get("id") or "").strip()

                    # If this file-product was deleted in admin, do not show it on the category page.
                    if item_id_str and f"dbitem:{p.docu_cat_slug}:{item_id_str}" in deleted_ids:
                        continue

                    # Default thumb: prebuilt card if exists
                    thumb_rel = f"cards/items/{p.docu_cat_slug}/{item_id_str}.png"
                    if item_id_str and os.path.exists(os.path.join(app.static_folder, thumb_rel)):
                        it["thumb_rel"] = thumb_rel

                    # If there is a sellable product for this file, prefer its (possibly overridden)
                    # title/description/photo/price.
                    prod = item_product_by_id.get(item_id_str)
                    if prod:
                        it["product_id"] = prod.id
                        it["price"] = prod.display_price()
                        it["display"] = prod.title
                        if prod.description:
                            it["description"] = prod.description

                        hero = prod.primary_image()
                        if hero and prod.image_source == "media":
                            it["thumb_url"] = url_for("media", filename=hero)
                        elif hero and prod.image_source == "static":
                            it["thumb_rel"] = hero
                    docu_items.append(it)

                # Also show custom products that were added in /edit into this DocuBeauty category.
                # Match by stable docu_cat_slug when available, otherwise by category name slug.
                try:
                    cat_label = str(docu_cat.get("name_pl") or p.title or "").strip()
                except Exception:
                    cat_label = str(p.title or "").strip()
                wanted = {p.docu_cat_slug, slugify(cat_label), slugify(p.title)}
                custom_in_docu_cat = [
                    x for x in catalog
                    if x.id.startswith("custom:")
                    and (
                        (x.docu_cat_slug and x.docu_cat_slug in wanted)
                        or slugify(x.category) in wanted
                    )
                ]

        download_url = None
        # Only allow direct downloads after payment (verified with Stripe).
        try:
            paid_sid = str(session.get("paid_session_id") or "").strip()
            paid_pids = set(session.get("paid_product_ids") or [])
        except Exception:
            paid_sid = ""
            paid_pids = set()

        if paid_sid and p.id in paid_pids and (p.download_file or ""):
            try:
                cs = verify_paid_checkout_session(paid_sid)
                meta = getattr(cs, "metadata", {}) or {}
                raw_ids = meta.get("product_ids") or "[]"
                purchased = {str(x) for x in __import__("json").loads(raw_ids) if str(x)}
                if p.id in purchased:
                    tok = make_download_token(paid_sid, {"kind": "custom", "pid": p.id})
                    download_url = url_for("download_file", token=tok)
                else:
                    # Stale session data; cleanup.
                    session.pop("paid_session_id", None)
                    session.pop("paid_product_ids", None)
            except Exception:
                # If Stripe verification fails, do not show download.
                download_url = None

        return render_template(
            "index.html",
            view="product",
            title=p.title,
            p=p,
            docu_cat=docu_cat,
            docu_items=docu_items,
            custom_products=custom_in_docu_cat,
            download_url=download_url,
        )


    @app.get("/docu/<cat_slug>/<item_id>")
    def docu_item_detail(cat_slug: str, item_id: str):
        """Detail page for a single file inside a DocuBeauty package."""
        # If an admin deleted this item-product, hide the deep link as well.
        deleted_ids = load_deleted_products()
        if f"dbitem:{cat_slug}:{item_id}" in deleted_ids:
            return redirect(url_for("shop"))

        cat = get_docubeauty_category(app.root_path, cat_slug)
        if not cat:
            return redirect(url_for("shop"))

        item = get_docubeauty_item_by_id(cat, item_id)
        if not item:
            return redirect(url_for("shop"))

        # Resolve the sellable item-product (price/cart id).
        catalog = get_catalog()
        prod = next((x for x in catalog if x.docu_cat_slug == cat_slug and x.docu_item_id == item_id), None)
        if not prod:
            # Fallback pseudo-product (keeps the page usable even if item products are not prebuilt).
            try:
                pf = float(cat.get("price_from") or 0.0)
            except Exception:
                pf = 79.0
            price = docubeauty_item_price(pf, 1, item_id)
            prod = Product(
                id=f"dbitem:{cat_slug}:{item_id}",
                title=item.get("display", "").rsplit("/", 1)[-1] or item_id,
                category=str(cat.get("name_pl") or cat_slug),
                category_url="",
                price_pln=float(price),
                description="",
                images=tuple(),
                image_source="static",
                source_url="",
                docu_cat_slug=cat_slug,
                docu_item_id=item_id,
            )

        # Attach thumb_rel if exists (prebuilt cards)
        item = dict(item)

        # Prefer the (possibly overridden) product title/description/photo.
        if prod:
            if prod.title:
                item["display"] = prod.title
            if prod.description:
                item["description"] = prod.description

            hero = prod.primary_image()
            if hero and prod.image_source == "static":
                item["thumb_rel"] = hero

        # Fallback to prebuilt cards/items/... if product does not provide a thumb.
        if not item.get("thumb_rel"):
            thumb_rel = f"cards/items/{cat_slug}/{item_id}.png"
            if os.path.exists(os.path.join(app.static_folder, thumb_rel)):
                item["thumb_rel"] = thumb_rel

        # Ensure the displayed category name reflects category overrides.
        docu_cat = dict(cat)
        if prod and prod.category:
            docu_cat["display_name"] = prod.category

        return render_template(
            "index.html",
            view="docu_item",
            title=(prod.title if prod else item.get("display", "")).rsplit("/", 1)[-1],
            item=item,
            p=prod,
            docu_cat=docu_cat,
        )


    @app.get("/open/<cat_slug>/<item_id>")
    def docu_open_item(cat_slug: str, item_id: str):
        """Direct download for DocuBeauty item (folder file or extracted from ZIP)."""
        # Deleted items must not be downloadable.
        deleted_ids = load_deleted_products()
        if f"dbitem:{cat_slug}:{item_id}" in deleted_ids:
            abort(404)

        cat = get_docubeauty_category(app.root_path, cat_slug)
        if not cat:
            abort(404)

        item = get_docubeauty_item_by_id(cat, item_id)
        if not item:
            abort(404)

        try:
            if cat.get("kind") == "dir":
                fs_path = item.get("abs")
                if not fs_path or not os.path.isfile(fs_path):
                    abort(404)
                return send_file(fs_path, as_attachment=True, download_name=os.path.basename(fs_path))

            cached = ensure_cached_zip_member(app.root_path, cat, item)
            return send_file(cached, as_attachment=True, download_name=os.path.basename(cached))
        except Exception:
            abort(500)



    # -------------------------
    # Simple admin page: edit product prices
    # -------------------------

    @app.route("/edit", methods=["GET", "POST"])
    def edit():
        # Very basic login with hardcoded credentials: sklep / sklep
        logged_in = bool(session.get("is_admin"))

        def _save_upload(f, allowed_exts: set[str], *, dst_dir: str = UPLOADS_DIR, rel_prefix: str = "uploads/") -> str:
            if not f or not getattr(f, "filename", ""):
                return ""
            name = secure_filename(f.filename)
            ext = os.path.splitext(name)[1].lower()
            if ext not in allowed_exts:
                return ""
            new_name = f"{uuid.uuid4().hex}{ext}"
            dst = os.path.join(dst_dir, new_name)
            try:
                f.save(dst)
            except Exception:
                return ""
            rel_prefix = (rel_prefix or "").replace("\\", "/")
            if rel_prefix and not rel_prefix.endswith("/"):
                rel_prefix += "/"
            return f"{rel_prefix}{new_name}"

        def _delete_static_rel(rel: str) -> None:
            rel = (rel or "").strip()
            if not rel:
                return
            if rel.startswith("http"):
                return
            fs_path = os.path.join(app.static_folder, rel.replace("/", os.sep))
            if os.path.isfile(fs_path):
                try:
                    os.remove(fs_path)
                except Exception:
                    pass

        def _delete_digital_rel(rel: str) -> None:
            """Delete a file under DIGITAL_GOODS_DIR (best-effort)."""
            rel = (rel or "").strip().replace("\\", "/").lstrip("/")
            if not rel:
                return
            if ".." in rel.split("/"):
                return
            fs_path = os.path.join(DIGITAL_GOODS_DIR, rel.replace("/", os.sep))
            base = os.path.abspath(DIGITAL_GOODS_DIR)
            ap = os.path.abspath(fs_path)
            if not ap.startswith(base):
                return
            if os.path.isfile(ap):
                try:
                    os.remove(ap)
                except Exception:
                    pass

        def _delete_any_file_rel(rel: str) -> None:
            rel = (rel or "").strip().replace("\\", "/")
            if rel.startswith("custom_uploads/"):
                _delete_digital_rel(rel)
            else:
                _delete_static_rel(rel)

        def _build_groups_and_categories():
            catalog = list(get_catalog())
            photo_overrides = load_photo_overrides()
            grouped = {}
            for p in catalog:
                grouped.setdefault(p.category or "Bez kategorii", []).append(p)
            for c in load_custom_categories():
                grouped.setdefault(c, [])

            groups = []
            for cat_name in sorted(grouped.keys(), key=lambda x: x.lower()):
                prods = sorted(grouped[cat_name], key=lambda p: p.title.lower())

                # Category thumbnail shown in /edit: prefer explicit override (dbcat:/cat:),
                # fallback to first product image in the group.
                cat_docu_slug = ""
                for _p in prods:
                    ds = getattr(_p, "docu_cat_slug", "") or ""
                    if ds:
                        cat_docu_slug = ds
                        break
                cat_pid = f"dbcat:{cat_docu_slug}" if cat_docu_slug else f"cat:{slugify(cat_name)}"

                cat_thumb_url = None
                rel = (photo_overrides.get(cat_pid) or "").strip()
                if rel:
                    cat_thumb_url = url_for("static", filename=rel)
                else:
                    # If a static independent category card exists, show it (keeps category thumbnail stable).
                    try:
                        slug_for_card = cat_docu_slug or slugify(cat_name)
                    except Exception:
                        slug_for_card = ""
                    if slug_for_card:
                        card_rel = f"cards/{slug_for_card}.png"
                        card_abs = os.path.join(app.static_folder, card_rel.replace("/", os.sep))
                        if os.path.exists(card_abs):
                            cat_thumb_url = url_for("static", filename=card_rel)
                    if not cat_thumb_url:
                        for _p in prods:
                            hero = _p.primary_image()
                            if not hero:
                                continue
                            if getattr(_p, "image_source", "static") == "media":
                                cat_thumb_url = url_for("media", filename=hero)
                            else:
                                cat_thumb_url = url_for("static", filename=hero)
                            break

                view_prods = []
                for p in prods:
                    hero = p.primary_image()
                    photo_url = None
                    if hero:
                        if p.image_source == "media":
                            photo_url = url_for("media", filename=hero)
                        else:
                            photo_url = url_for("static", filename=hero)
                    view_prods.append({
                        "id": p.id,
                        "title": p.title,
                        "description": p.description,
                        "price_pln": p.price_pln,
                        "photo_url": photo_url,
                        "category": p.category,
                        "docu_cat_slug": getattr(p, "docu_cat_slug", "") or "",
                        "docu_item_id": getattr(p, "docu_item_id", "") or "",
                    })
                groups.append((cat_name, view_prods, cat_thumb_url, cat_docu_slug))

            categories = sorted(grouped.keys(), key=lambda x: x.lower())
            return groups, categories

        if request.method == "POST":
            if not logged_in:
                username = (request.form.get("username") or "").strip()
                password = (request.form.get("password") or "").strip()
                if username == "sklep" and password == "sklep":
                    session["is_admin"] = True
                    return redirect(url_for("edit"))
                return render_template(
                    "edit.html",
                    logged_in=False,
                    login_error="Nieprawidłowy login lub hasło.",
                )

            action = (request.form.get("action") or "").strip()
            wants_json = (request.form.get("ajax") == "1") or (
                (request.headers.get("X-Requested-With") or "").lower() == "xmlhttprequest"
            )
            def _ok(**extra):
                if wants_json:
                    return jsonify({"ok": True, **extra})
                return None
            def _fail(message: str, status: int = 400, **extra):
                if wants_json:
                    payload = {"ok": False, "error": message}
                    payload.update(extra)
                    return jsonify(payload), status
                return None

            # ---------- Logout ----------
            if action == "logout":
                session.pop("is_admin", None)
                return redirect(url_for("edit"))

            # ---------- Category: add ----------
            if action == "add_category":
                name = (request.form.get("category_name") or "").strip()
                if not name:
                    return _fail("Podaj nazwę kategorii.") or redirect(
                        url_for("edit", error="Podaj nazwę kategorii.")
                    )

                cats = load_custom_categories()
                if name.lower() not in {c.lower() for c in cats}:
                    cats.append(name)
                    save_custom_categories(cats)

                return _ok(added_category=1) or redirect(url_for("edit", added_category=1))

            # ---------- Category: rename ----------
            if action == "cat_rename":
                old_name = (request.form.get("old_name") or "").strip()
                new_name = (request.form.get("new_name") or "").strip()
                if not old_name or not new_name:
                    return _fail("Podaj starą i nową nazwę kategorii.") or redirect(url_for("edit", error="Podaj starą i nową nazwę kategorii."))
                if old_name == new_name:
                    return _ok() or redirect(url_for("edit"))

                # Update stored categories list
                cats = load_custom_categories()
                replaced = False
                out = []
                for c in cats:
                    if not replaced and c.lower() == old_name.lower():
                        out.append(new_name)
                        replaced = True
                    else:
                        out.append(c)
                if not replaced and new_name.lower() not in {c.lower() for c in out}:
                    out.append(new_name)
                save_custom_categories(out)

                # Update products currently assigned to old category
                catalog = list(get_catalog())
                cat_overrides = load_category_overrides()

                # Also rewrite any existing overrides values equal to old_name
                for pid, val in list(cat_overrides.items()):
                    if str(val).strip().lower() == old_name.lower():
                        cat_overrides[pid] = new_name

                # Update custom products JSON
                try:
                    raw = []
                    if os.path.exists(CUSTOM_PRODUCTS_PATH):
                        with open(CUSTOM_PRODUCTS_PATH, "r", encoding="utf-8") as f:
                            raw = json.load(f) or []
                    if not isinstance(raw, list):
                        raw = []
                except Exception:
                    raw = []

                changed_custom = False
                for rec in raw:
                    if not isinstance(rec, dict):
                        continue
                    if str(rec.get("category") or "").strip().lower() == old_name.lower():
                        rec["category"] = new_name
                        changed_custom = True

                for p in catalog:
                    if str(p.category).strip().lower() != old_name.lower():
                        continue
                    if str(p.id).startswith("custom:"):
                        cat_overrides.pop(str(p.id), None)
                    else:
                        cat_overrides[str(p.id)] = new_name

                if changed_custom:
                    try:
                        save_custom_products(raw)
                    except Exception:
                        pass
                save_category_overrides(cat_overrides)

                # DocuBeauty: category cards are rendered from Product(title) (id: dbcat:<slug>).
                # When renaming a category group (typically used for DocuBeauty item-products), also
                # update the matching category-card title so the shop/category pages reflect the change.
                try:
                    title_overrides = load_title_overrides()
                    for p in catalog:
                        if str(p.id).startswith("dbcat:") and str(p.title).strip().lower() == old_name.lower():
                            title_overrides[str(p.id)] = new_name
                    save_title_overrides(title_overrides)
                except Exception:
                    pass

                # Move thumbnail override for custom category (cat:<slugified-name>)
                try:
                    photo_overrides = load_photo_overrides()
                    old_key = f"cat:{slugify(old_name)}"
                    new_key = f"cat:{slugify(new_name)}"
                    if old_key in photo_overrides and new_key not in photo_overrides:
                        photo_overrides[new_key] = photo_overrides.pop(old_key)
                        save_photo_overrides(photo_overrides)
                except Exception:
                    pass

                return _ok() or redirect(url_for("edit"))

            # ---------- Category: delete ----------
            if action == "cat_delete":
                name = (request.form.get("name") or "").strip()
                if not name:
                    return _fail("Brak nazwy kategorii.") or redirect(url_for("edit"))

                # DocuBeauty category deletion:
                # If the category exists as a DocuBeauty navigation card (dbcat:<slug>), deleting the category
                # in admin should hide BOTH the category card and ALL its items (dbitem:<slug>:<id>).
                # This makes "Usuń kategorię" behave predictably for DocuBeauty content.
                try:
                    docu = build_docubeauty_products(app.root_path)
                    match_slug = ""
                    for p0 in docu:
                        if str(getattr(p0, "id", "")).startswith("dbcat:") and str(getattr(p0, "title", "")).strip().lower() == name.lower():
                            match_slug = getattr(p0, "docu_cat_slug", "") or str(p0.id).split(":", 1)[1]
                            break
                    if match_slug:
                        deleted = load_deleted_products()
                        ids_to_clean = {f"dbcat:{match_slug}"}
                        for p0 in docu:
                            if getattr(p0, "docu_cat_slug", "") == match_slug and getattr(p0, "docu_item_id", ""):
                                ids_to_clean.add(str(p0.id))

                        for _id in ids_to_clean:
                            deleted.add(_id)
                        save_deleted_products(deleted)

                        # cleanup overrides for removed docu IDs
                        price_overrides = load_price_overrides()
                        desc_overrides = load_description_overrides()
                        title_overrides = load_title_overrides()
                        cat_overrides = load_category_overrides()
                        photo_overrides = load_photo_overrides()
                        for _id in ids_to_clean:
                            for d in (price_overrides, desc_overrides, title_overrides, cat_overrides, photo_overrides):
                                d.pop(_id, None)
                        save_price_overrides(price_overrides)
                        save_description_overrides(desc_overrides)
                        save_title_overrides(title_overrides)
                        save_category_overrides(cat_overrides)
                        save_photo_overrides(photo_overrides)

                        return _ok(deleted_category=1) or redirect(url_for("edit", deleted_category=1))
                except Exception:
                    pass

                # remove from custom categories list
                cats = [c for c in load_custom_categories() if c.lower() != name.lower()]
                save_custom_categories(cats)

                catalog = list(get_catalog())
                cat_overrides = load_category_overrides()
                price_overrides = load_price_overrides()
                desc_overrides = load_description_overrides()
                photo_overrides = load_photo_overrides()
                deleted_ids = load_deleted_products()

                # delete custom products in this category
                try:
                    raw = []
                    if os.path.exists(CUSTOM_PRODUCTS_PATH):
                        with open(CUSTOM_PRODUCTS_PATH, "r", encoding="utf-8") as f:
                            raw = json.load(f) or []
                    if not isinstance(raw, list):
                        raw = []
                except Exception:
                    raw = []

                new_raw = []
                for rec in raw:
                    if not isinstance(rec, dict):
                        continue
                    if str(rec.get("category") or "").strip().lower() == name.lower():
                        _delete_any_file_rel(str(rec.get("image") or ""))
                        _delete_any_file_rel(str(rec.get("file") or ""))
                        pid = str(rec.get("id") or "").strip()
                        if pid:
                            price_overrides.pop(pid, None)
                            desc_overrides.pop(pid, None)
                            cat_overrides.pop(pid, None)
                            photo_overrides.pop(pid, None)
                            deleted_ids.discard(pid)
                        continue
                    new_raw.append(rec)

                try:
                    save_custom_products(new_raw)
                except Exception:
                    pass

                # for non-custom products -> move to 'Produkty'
                for p in catalog:
                    if str(p.category).strip().lower() == name.lower() and not str(p.id).startswith("custom:"):
                        cat_overrides[str(p.id)] = "Produkty"

                save_price_overrides(price_overrides)
                save_description_overrides(desc_overrides)
                save_category_overrides(cat_overrides)
                save_photo_overrides(photo_overrides)
                save_deleted_products(deleted_ids)

                return _ok(deleted_category=1) or redirect(url_for("edit", deleted_category=1))

            # ---------- Category: photo update (category header button) ----------
            # - DocuBeauty category groups (items) should update the *category card* product: dbcat:<slug>
            # - Custom/regular categories can also store a thumbnail override under: cat:<slugified-name>
            #   (used currently for admin/category thumbnail if needed).
            if action == "cat_photo":
                cat_slug = (request.form.get("cat_slug") or "").strip()
                cat_name = (request.form.get("cat_name") or "").strip()
                photo = request.files.get("photo")
                if (not cat_slug and not cat_name) or not photo:
                    return _fail("Brak kategorii lub pliku zdjęcia.") or redirect(url_for("edit"))

                img_rel = _save_upload(photo, {".png", ".jpg", ".jpeg", ".webp", ".jfif"})
                if not img_rel:
                    return _fail("Nieprawidłowy plik zdjęcia.") or redirect(url_for("edit", error="Nieprawidłowy plik zdjęcia."))

                if cat_slug:
                    pid = f"dbcat:{cat_slug}"
                else:
                    pid = f"cat:{slugify(cat_name)}"

                overrides = load_photo_overrides()
                old = str(overrides.get(pid) or "").strip()
                if old and old != img_rel:
                    _delete_static_rel(old)
                overrides[pid] = img_rel
                save_photo_overrides(overrides)

                return _ok(photo_updated=1) or redirect(url_for("edit", photo_updated=1))

            # ---------- Product: add ----------
            if action == "add_product":
                title = (request.form.get("new_title") or "").strip()
                desc = (request.form.get("new_description") or "").strip()
                raw_price = (request.form.get("new_price") or "").strip()
                category_label = (request.form.get("new_category") or "").strip() or "Produkty"
                photo = request.files.get("new_photo")
                product_file = request.files.get("new_file")

                try:
                    cleaned = raw_price.replace("zł", "").replace("ZŁ", "").replace(" ", "").replace(",", ".")
                    price = float(cleaned) if cleaned else 0.0
                except Exception:
                    price = 0.0

                # Validate required inputs with precise diagnostics.
                allowed_img = {".png", ".jpg", ".jpeg", ".webp", ".jfif"}
                allowed_file = {".pdf", ".zip", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}

                def _ext_of(file_obj):
                    try:
                        name = secure_filename(getattr(file_obj, "filename", "") or "")
                        return os.path.splitext(name)[1].lower()
                    except Exception:
                        return ""

                if not title:
                    err_msg = "Brak nazwy produktu."
                elif price <= 0:
                    err_msg = "Nieprawidłowa cena (musi być większa niż 0)."
                elif not photo or not getattr(photo, "filename", ""):
                    err_msg = "Brak zdjęcia produktu."
                elif _ext_of(photo) not in allowed_img:
                    err_msg = "Nieobsługiwany format zdjęcia (dozwolone: JPG, PNG, WEBP)."
                elif not product_file or not getattr(product_file, "filename", ""):
                    err_msg = "Brak pliku produktu (PDF/ZIP/DOCX itd.)."
                elif _ext_of(product_file) not in allowed_file:
                    err_msg = "Nieobsługiwany format pliku (dozwolone: PDF, ZIP, DOC/DOCX, PPT/PPTX, XLS/XLSX)."
                else:
                    err_msg = ""

                img_rel = _save_upload(photo, allowed_img)
                # Downloadable file is stored outside /static to prevent free downloads.
                file_rel = _save_upload(
                    product_file,
                    allowed_file,
                    dst_dir=CUSTOM_DIGITAL_DIR,
                    rel_prefix="custom_uploads",
                )

                # If saving failed despite passing basic validation (e.g. filesystem issue), show a clear error.
                if not err_msg and (not img_rel or not file_rel):
                    err_msg = "Nie udało się zapisać plików. Spróbuj ponownie (lub zmień nazwę/format pliku)."

                if err_msg:
                    if wants_json:
                        return _fail(err_msg)
                    groups, categories = _build_groups_and_categories()
                    return render_template(
                        "edit.html",
                        logged_in=True,
                        groups=groups,
                        categories=categories,
                        saved=False,
                        added=False,
                        added_category=False,
                        deleted_category=False,
                        deleted_product=False,
                        photo_updated=False,
                        add_error=err_msg,
                        error_message=None,
                    )

                pid = f"custom:{uuid.uuid4().hex}"

                # If the selected category corresponds to a DocuBeauty package, store its slug.
                # This makes the association stable even if the category display name changes.
                docu_slug = ""
                try:
                    docu_slug_guess = slugify(category_label)
                    if docu_slug_guess in CATEGORY_META:
                        docu_slug = docu_slug_guess
                except Exception:
                    docu_slug = ""

                record = {
                    "id": pid,
                    "title": title,
                    "description": desc,
                    "price_pln": price,
                    "image": img_rel,
                    "file": file_rel,
                    "category": category_label,
                    "docu_cat_slug": docu_slug,
                    "created_at": int(time.time()),
                }
                append_custom_product(record)

                # Ensure category is visible in dropdown even if empty later
                cats = load_custom_categories()
                if category_label.lower() not in {c.lower() for c in cats}:
                    cats.append(category_label)
                    save_custom_categories(cats)

                return _ok(added=1) or redirect(url_for("edit", added=1))

            # ---------- Product: delete ----------
            if action == "product_delete":
                pid = (request.form.get("product_id") or "").strip()
                if pid:
                    # custom product removal
                    if pid.startswith("custom:"):
                        try:
                            raw = []
                            if os.path.exists(CUSTOM_PRODUCTS_PATH):
                                with open(CUSTOM_PRODUCTS_PATH, "r", encoding="utf-8") as f:
                                    raw = json.load(f) or []
                            if not isinstance(raw, list):
                                raw = []
                        except Exception:
                            raw = []

                        new_raw = []
                        for rec in raw:
                            if not isinstance(rec, dict):
                                continue
                            if str(rec.get("id") or "").strip() == pid:
                                _delete_any_file_rel(str(rec.get("image") or ""))
                                _delete_any_file_rel(str(rec.get("file") or ""))
                                continue
                            new_raw.append(rec)
                        try:
                            save_custom_products(new_raw)
                        except Exception:
                            pass
                    else:
                        # Mark as deleted (non-custom). If this is a DocuBeauty category card (dbcat:<slug>),
                        # also hide all items (dbitem:<slug>:<id>) so the whole category disappears.
                        deleted = load_deleted_products()
                        ids_to_clean = {pid}

                        if pid.startswith("dbcat:"):
                            slug = pid.split(":", 1)[1]
                            try:
                                docu = build_docubeauty_products(app.root_path)
                                for p0 in docu:
                                    if getattr(p0, "docu_cat_slug", "") == slug and getattr(p0, "docu_item_id", ""):
                                        ids_to_clean.add(str(p0.id))
                            except Exception:
                                pass

                        for _id in ids_to_clean:
                            deleted.add(_id)
                        save_deleted_products(deleted)

                    # cleanup overrides (for the deleted ID(s))
                    price_overrides = load_price_overrides()
                    desc_overrides = load_description_overrides()
                    title_overrides = load_title_overrides()
                    cat_overrides = load_category_overrides()
                    photo_overrides = load_photo_overrides()

                    ids_to_clean = locals().get("ids_to_clean", {pid})
                    for _id in ids_to_clean:
                        for d in (price_overrides, desc_overrides, title_overrides, cat_overrides, photo_overrides):
                            d.pop(_id, None)

                    save_price_overrides(price_overrides)
                    save_description_overrides(desc_overrides)
                    save_title_overrides(title_overrides)
                    save_category_overrides(cat_overrides)
                    save_photo_overrides(photo_overrides)

                return _ok(deleted_product=1) or redirect(url_for("edit", deleted_product=1))

            # ---------- Product: photo update ----------
            if action == "product_photo":
                pid = (request.form.get("product_id") or "").strip()
                photo = request.files.get("photo")
                if not pid or not photo:
                    return _fail("Brak ID produktu lub pliku zdjęcia.") or redirect(url_for("edit"))

                img_rel = _save_upload(photo, {".png", ".jpg", ".jpeg", ".webp", ".jfif"})
                if not img_rel:
                    return _fail("Nieprawidłowy plik zdjęcia.") or redirect(url_for("edit", error="Nieprawidłowy plik zdjęcia."))

                if pid.startswith("custom:"):
                    try:
                        raw = []
                        if os.path.exists(CUSTOM_PRODUCTS_PATH):
                            with open(CUSTOM_PRODUCTS_PATH, "r", encoding="utf-8") as f:
                                raw = json.load(f) or []
                        if not isinstance(raw, list):
                            raw = []
                    except Exception:
                        raw = []

                    for rec in raw:
                        if not isinstance(rec, dict):
                            continue
                        if str(rec.get("id") or "").strip() == pid:
                            old = str(rec.get("image") or "").strip()
                            if old and old != img_rel:
                                _delete_static_rel(old)
                            rec["image"] = img_rel
                    try:
                        save_custom_products(raw)
                    except Exception:
                        pass
                else:
                    overrides = load_photo_overrides()
                    overrides[pid] = img_rel
                    save_photo_overrides(overrides)

                return _ok(photo_updated=1) or redirect(url_for("edit", photo_updated=1))


            # ---------- Product update: price + description (per-card) ----------
            if action == "product_update":
                pid = (request.form.get("product_id") or "").strip()
                if not pid:
                    return _fail("Brak ID produktu.") or redirect(url_for("edit", error="Brak ID produktu."))

                raw_title = (request.form.get("title") or "").strip()
                raw_price = (request.form.get("price") or "").strip()
                raw_desc = (request.form.get("description") or "").strip()

                # Normalize price
                price_val = None
                if raw_price != "":
                    cleaned = raw_price.replace("zł", "").replace("ZŁ", "").replace(" ", "").replace(",", ".")
                    try:
                        price_val = float(cleaned)
                    except Exception:
                        price_val = None

                # Custom product -> update in custom_products.json
                if pid.startswith("custom:"):
                    custom = load_custom_products_raw()
                    found = False
                    for cp in custom:
                        if str(cp.get("id")) == pid:
                            if raw_title != "":
                                cp["title"] = raw_title
                            if raw_desc != "":
                                cp["description"] = raw_desc
                            if price_val is not None:
                                cp["price_pln"] = float(price_val)
                            found = True
                            break
                    if found:
                        save_custom_products(custom)
                        return _ok(product_saved=1) or redirect(url_for("edit", product_saved="1"))
                    return _fail("Nie znaleziono produktu (custom).") or redirect(url_for("edit", error="Nie znaleziono produktu (custom)."))

                # Regular product -> store overrides
                if raw_title != "":
                    title_overrides = load_title_overrides()
                    title_overrides[pid] = raw_title
                    save_title_overrides(title_overrides)

                if raw_desc != "":
                    desc_overrides = load_description_overrides()
                    desc_overrides[pid] = raw_desc
                    save_description_overrides(desc_overrides)

                if price_val is not None:
                    price_overrides = load_price_overrides()
                    price_overrides[pid] = float(price_val)
                    save_price_overrides(price_overrides)

                return _ok(product_saved=1) or redirect(url_for("edit", product_saved="1"))

            # ---------- Bulk update: price + description ----------
            if action == "bulk_update":
                price_overrides = load_price_overrides()
                desc_overrides = load_description_overrides()
                catalog = list(get_catalog())

                changed_price = False
                changed_desc = False

                for p in catalog:
                    field_price = f"price_{p.id}"
                    if field_price in request.form:
                        raw_price = (request.form.get(field_price) or "").strip()
                        if raw_price:
                            cleaned = raw_price.replace("zł", "").replace("ZŁ", "").replace(" ", "").replace(",", ".")
                            try:
                                val = float(cleaned)
                            except Exception:
                                val = None
                        else:
                            val = None

                        if val is None:
                            if p.id in price_overrides:
                                price_overrides.pop(p.id, None)
                                changed_price = True
                        else:
                            if val > 0 and price_overrides.get(p.id) != val:
                                price_overrides[p.id] = val
                                changed_price = True

                    field_desc = f"desc_{p.id}"
                    if field_desc in request.form:
                        raw_desc = (request.form.get(field_desc) or "").strip()
                        if not raw_desc:
                            if p.id in desc_overrides:
                                desc_overrides.pop(p.id, None)
                                changed_desc = True
                        else:
                            if desc_overrides.get(p.id, "") != raw_desc:
                                desc_overrides[p.id] = raw_desc
                                changed_desc = True

                if changed_price:
                    save_price_overrides(price_overrides)
                if changed_desc:
                    save_description_overrides(desc_overrides)

                return redirect(url_for("edit", saved=1))

            return redirect(url_for("edit"))

        # GET
        logged_in = bool(session.get("is_admin"))
        if not logged_in:
            return render_template("edit.html", logged_in=False)

        groups, categories = _build_groups_and_categories()
        return render_template(
            "edit.html",
            logged_in=True,
            groups=groups,
            categories=categories,
            saved=(request.args.get("saved") == "1"),
            added=(request.args.get("added") == "1"),
            added_category=(request.args.get("added_category") == "1"),
            deleted_category=(request.args.get("deleted_category") == "1"),
            deleted_product=(request.args.get("deleted_product") == "1"),
            photo_updated=(request.args.get("photo_updated") == "1"),
            product_saved=(request.args.get("product_saved") == "1"),
            add_error=None,
            error_message=((request.args.get("error_message") or request.args.get("error") or "") or None),
        )

    @app.get("/edit/download-data")
    def download_data():
        """Download an admin backup ZIP.

        The ZIP is meant to be unpacked into the project root on another server.
        It includes:
          - data/                       (JSON overrides, categories, deletions, etc.)
          - static/uploads/             (category/product images uploaded in /edit)
          - digital_goods/custom_uploads/ (paid files uploaded in /edit)
        """
        if not session.get("is_admin"):
            return redirect(url_for("edit"))

        base_dir = os.path.abspath(os.path.dirname(__file__))
        paths = [
            os.path.join(base_dir, "data"),
            os.path.join(base_dir, "static", "uploads"),
            os.path.join(base_dir, "digital_goods", "custom_uploads"),
        ]

        def _add_dir(zf: zipfile.ZipFile, abs_dir: str) -> None:
            if not abs_dir or not os.path.isdir(abs_dir):
                return
            for root, _dirs, files in os.walk(abs_dir):
                for fn in files:
                    fp = os.path.join(root, fn)
                    # Store paths relative to project root so unzip is drop-in.
                    rel = os.path.relpath(fp, base_dir).replace("\\", "/")
                    zf.write(fp, rel)

        mem = BytesIO()
        with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            for d in paths:
                _add_dir(z, d)

        mem.seek(0)
        ts = time.strftime("%Y-%m-%d_%H-%M-%S")
        return send_file(
            mem,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"backup_{ts}.zip",
        )

    @app.get("/cart")
    def cart():
        catalog = get_catalog()
        cart_data = get_cart()
        by_id = {p.id: p for p in catalog}

        lines = []
        subtotal = 0.0
        for pid, qty in cart_data.items():
            p = by_id.get(pid)
            if not p:
                continue
            unit = p.unit_price_for_cart()
            line_total = unit * qty
            subtotal += line_total
            lines.append(
                {"product": p, "qty": qty, "unit": unit, "line_total": line_total}
            )

        return render_template(
            "index.html",
            view="cart",
            title="Koszyk",
            lines=lines,
            subtotal=subtotal,
        )
    @app.post("/checkout")
    def checkout():
        """Create Stripe Checkout Session and redirect to payment page."""
        catalog = get_catalog()
        cart_data = get_cart()
        line_items = build_stripe_line_items(cart_data, catalog)

        if not line_items:
            return redirect(url_for("cart"))

        try:
            # Keep a server-side snapshot in case Stripe metadata is unavailable on redirect.
            session["last_checkout_cart"] = {k: int(v) for k, v in cart_data.items()}
            session["last_checkout_product_ids"] = list(cart_data.keys())
            base_url = request.url_root.rstrip("/")
            checkout_session = stripe.checkout.Session.create(
                mode="payment",
                line_items=line_items,
                # Store purchased product ids in session metadata so we can resolve downloads on /checkout/success
                metadata={
                    "product_ids": json.dumps(list(cart_data.keys())),
                    "cart": json.dumps({k: int(v) for k, v in cart_data.items()}),
                },
                success_url=base_url + url_for("checkout_success") + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=base_url + url_for("checkout_cancel"),
            )
            return redirect(checkout_session.url, code=303)
        except Exception as e:
            return f"Błąd Stripe Checkout: {e}", 500

    @app.get("/checkout/success")
    def checkout_success():
        """Success page: verifies Stripe payment and shows download links."""
        session_id = (request.args.get("session_id") or "").strip()

        if not session_id:
            return render_template(
                "success.html",
                title="Dziękujemy za zamówienie",
                paid=False,
                downloads=[],
                bundle_url=None,
                customer_email=None,
                static_version=STATIC_VERSION,
            )

        cs = verify_paid_checkout_session(session_id)

        # Extract purchased product ids from metadata (preferred)
        product_ids: List[str] = []
        try:
            meta = getattr(cs, "metadata", {}) or {}
            raw_ids = meta.get("product_ids") or "[]"
            product_ids = [str(x) for x in json.loads(raw_ids) if str(x)]
        except Exception:
            product_ids = []

        # Fallback: use server-side snapshot (useful if Stripe metadata is missing).
        if not product_ids:
            try:
                snap = session.get("last_checkout_product_ids") or []
                product_ids = [str(x) for x in snap if str(x)]
            except Exception:
                product_ids = []

        # Fallback: if metadata is missing, use the last checkout snapshot stored in the browser session.
        if not product_ids:
            try:
                snap = session.get("last_checkout_product_ids") or []
                if isinstance(snap, list):
                    product_ids = [str(x) for x in snap if str(x)]
            except Exception:
                product_ids = []

        # Keep last paid session in browser session so we can show download buttons on product pages.
        session["paid_session_id"] = session_id
        session["paid_product_ids"] = product_ids

        # Build download links for purchased items.
        # - DocuBeauty: products are categories (dbcat:<slug>), and we expose:
        #   * bundle ZIP (whole product)
        #   * individual files inside the category (watermarked previews elsewhere; downloads are originals)
        # - Legacy: use digital_goods/manifest.json mapping.
        catalog = get_catalog()
        by_id = {p.id: p for p in catalog}
        docu_cats: List[Product] = []
        docu_items: List[Product] = []
        custom_products: List[Product] = []
        legacy_product_ids: List[str] = []

        for pid in product_ids:
            p = by_id.get(pid)
            if p and p.docu_cat_slug and p.docu_item_id:
                docu_items.append(p)
            elif p and p.docu_cat_slug and not p.docu_item_id:
                docu_cats.append(p)
            elif p and str(p.id).startswith("custom:"):
                custom_products.append(p)
            else:
                legacy_product_ids.append(pid)

        downloads: List[Dict[str, str]] = []

        bundle_url = None

        # DocuBeauty item purchases (single files)
        for p in docu_items:
            cat = get_docubeauty_category(app.root_path, p.docu_cat_slug)
            if not cat:
                continue
            token = make_download_token(session_id, {"kind": "docu", "cat": p.docu_cat_slug, "item": p.docu_item_id})
            this_url = url_for("download_file", token=token)
            downloads.append({"name": f"{p.category} / {p.title}", "url": this_url})
        # DocuBeauty category purchases (bundle only).
        # If a category card ever ends up in a paid cart, the customer should receive
        # the exact purchased bundle (ZIP) — not all internal files listed separately.
        for p in docu_cats:
            cat = get_docubeauty_category(app.root_path, p.docu_cat_slug)
            if not cat:
                continue
            try:
                token = make_download_token(session_id, {"kind": "docu_bundle", "cat": p.docu_cat_slug})
                this_bundle_url = url_for("download_file", token=token)
                bundle_name = os.path.basename(cat.get("source_path") or "") or f"{p.docu_cat_slug}.zip"
                downloads.append({"name": f"{p.title} — {bundle_name}", "url": this_bundle_url})
            except Exception:
                continue

        # Custom product downloads (protected; served via /download/<token>)
        for p in custom_products:
            rel = (p.download_file or '').strip()
            if not rel:
                continue
            token = make_download_token(session_id, {"kind": "custom", "pid": p.id})
            this_url = url_for("download_file", token=token)
            downloads.append({"name": p.title, "url": this_url})

        # Legacy digital_goods downloads (manifest-based)
        files, bundle_file = resolve_files_for_products(legacy_product_ids)

        for rel in files:
            token = make_download_token(session_id, rel)
            downloads.append({"name": os.path.basename(rel), "url": url_for("download_file", token=token)})
        # clear cart only after verified payment
        session["cart"] = {}

        customer_email = None
        try:
            cd = getattr(cs, "customer_details", None)
            if cd and getattr(cd, "email", None):
                customer_email = cd.email
        except Exception:
            customer_email = None

        return render_template(
            "success.html",
            title="Dziękujemy za zamówienie",
            paid=True,
            downloads=downloads,
            bundle_url=bundle_url,
            customer_email=customer_email,
            static_version=STATIC_VERSION,
        )

    @app.get("/checkout/cancel")
    def checkout_cancel():
        return render_template("cancel.html", title="Płatność anulowana", static_version=STATIC_VERSION)


    # -------------------------
    # Download routes (post-payment)
    # -------------------------
    @app.get("/download/<token>")
    def download_file(token: str):
        """Serve a digital file (legacy manifest) or DocuBeauty item (C:\produkty) if token is valid and payment is confirmed."""
        try:
            data = read_download_token(token)
        except SignatureExpired:
            abort(410, "Link expired")
        except BadSignature:
            abort(400, "Invalid link")

        session_id = str(data.get("sid") or "").strip()
        if not session_id:
            abort(400, "Invalid link")

        # Always verify payment status
        cs = verify_paid_checkout_session(session_id)


        # DocuBeauty downloads (C:\produkty):
        # - kind == "docu": single file inside a purchased category
        # - kind == "docu_bundle": whole purchased category as ZIP (original ZIP or generated from directory)
        kind = str(data.get("kind") or "").strip()

        if kind in ("docu", "docu_bundle"):
            cat_slug = str(data.get("cat") or "").strip()
            if not cat_slug:
                abort(400, "Invalid link")

            # Verify the purchased products include this DocuBeauty category
            purchased_ids: List[str] = []
            try:
                meta = getattr(cs, "metadata", {}) or {}
                raw_ids = meta.get("product_ids") or "[]"
                purchased_ids = [str(x) for x in json.loads(raw_ids) if str(x)]
            except Exception:
                purchased_ids = []

            # Access control:
            # - If the customer purchased a whole category (dbcat:<slug>), they may download any file from it.
            # - If the customer purchased a single file (dbitem:<slug>:<item_id>), they may download only that file.
            item_id = ""
            if kind == "docu_bundle":
                expected_cat_pid = f"dbcat:{cat_slug}"
                if expected_cat_pid not in purchased_ids:
                    abort(403, "Access denied")
            else:
                item_id = str(data.get("item") or "").strip()
                if not item_id:
                    abort(400, "Invalid link")
                expected_item_pid = f"dbitem:{cat_slug}:{item_id}"
                expected_cat_pid = f"dbcat:{cat_slug}"
                if (expected_item_pid not in purchased_ids) and (expected_cat_pid not in purchased_ids):
                    abort(403, "Access denied")

            cat = get_docubeauty_category(app.root_path, cat_slug)
            if not cat:
                abort(404, "Category not found")

            if kind == "docu_bundle":
                # Whole product as ZIP
                if cat.get("kind") == "zip":
                    zp = cat.get("source_path") or ""
                    if not zp or not os.path.isfile(zp):
                        abort(404, "File not found")
                    return send_file(zp, as_attachment=True, download_name=os.path.basename(zp))
                # Directory -> zip it and serve cached archive
                bundle_path = ensure_cached_dir_zip(app.root_path, cat)
                return send_file(bundle_path, as_attachment=True, download_name=f"{cat_slug}.zip")

            # kind == "docu" -> single file

            item = get_docubeauty_item_by_id(cat, item_id)
            if not item:
                abort(404, "Item not found")

            if cat.get("kind") == "dir":
                fs_path = item.get("abs")
                if not fs_path or not os.path.isfile(fs_path):
                    abort(404, "File not found")
                return send_file(fs_path, as_attachment=True, download_name=os.path.basename(fs_path))

            cached = ensure_cached_zip_member(app.root_path, cat, item)
            return send_file(cached, as_attachment=True, download_name=os.path.basename(cached))


        # Custom product download (served from digital_goods/custom_uploads)
        if kind == "custom":
            pid = str(data.get("pid") or "").strip()
            if not pid:
                abort(400, "Invalid link")

            # Verify the purchased products include this product id
            purchased_ids: List[str] = []
            try:
                meta = getattr(cs, "metadata", {}) or {}
                raw_ids = meta.get("product_ids") or "[]"
                purchased_ids = [str(x) for x in json.loads(raw_ids) if str(x)]
            except Exception:
                purchased_ids = []

            if pid not in purchased_ids:
                abort(403, "Access denied")

            catalog = get_catalog()
            prod = next((p for p in catalog if p.id == pid), None)
            if not prod or not (prod.download_file or '').strip():
                abort(404, "File not found")

            relpath = (prod.download_file or '').strip()
            abs_path = safe_goods_path(relpath)
            if not os.path.isfile(abs_path):
                abort(404, "File not found")

            return send_file(abs_path, as_attachment=True, download_name=os.path.basename(abs_path))

        # Legacy digital_goods file download (manifest-based)
        relpath = str(data.get("p") or "").strip()
        if not relpath:
            abort(400, "Invalid link")

        abs_path = safe_goods_path(relpath)
        if not os.path.isfile(abs_path):
            abort(404, "File not found on server")

        return send_file(abs_path, as_attachment=True, download_name=os.path.basename(abs_path))



    # -------------------------
    # Cart API
    # -------------------------
    @app.post("/api/cart/add")
    def api_cart_add():
        payload = request.get_json(silent=True) or {}
        pid = str(payload.get("id") or "").strip()
        qty = payload.get("qty", 1)

        if not pid:
            return jsonify({"ok": False, "error": "Invalid payload"}), 400

        try:
            qty_int = max(1, min(int(qty), 99))
        except Exception:
            return jsonify({"ok": False, "error": "Invalid payload"}), 400

        catalog = get_catalog()
        prod = next((p for p in catalog if p.id == pid), None)
        if not prod:
            return jsonify({"ok": False, "error": "Unknown product"}), 404

        # DocuBeauty: category cards are navigation-only.
        if prod.docu_cat_slug and not prod.docu_item_id:
            return jsonify({"ok": False, "error": "Wybierz plik w środku kategorii"}), 400

        # Custom category cards are navigation-only.
        if prod.id.startswith("cat:"):
            return jsonify({"ok": False, "error": "To jest kategoria, wybierz produkt"}), 400

        cart_data = get_cart()
        # DocuBeauty files are single-purchase items (no multi-quantity).
        if prod.docu_cat_slug and prod.docu_item_id:
            cart_data[pid] = 1
        else:
            cart_data[pid] = min(99, int(cart_data.get(pid, 0)) + qty_int)
        session["cart"] = cart_data

        summ = cart_summary(catalog)
        return jsonify({"ok": True, "count": summ["count"], "total": summ["total"]})

    @app.post("/api/cart/update")
    def api_cart_update():
        payload = request.get_json(silent=True) or {}
        pid = str(payload.get("id") or "").strip()
        qty = payload.get("qty", 1)

        if not pid:
            return jsonify({"ok": False, "error": "Invalid payload"}), 400

        try:
            qty_int = int(qty)
        except Exception:
            return jsonify({"ok": False, "error": "Invalid payload"}), 400

        catalog = get_catalog()
        prod = next((p for p in catalog if p.id == pid), None)
        if prod and ((prod.docu_cat_slug and not prod.docu_item_id) or prod.id.startswith("cat:")):
            # Prevent category cards from ending up in the cart.
            cart_data = get_cart()
            cart_data.pop(pid, None)
            session["cart"] = cart_data
            summ = cart_summary(catalog)
            return jsonify({"ok": True, "count": summ["count"], "total": summ["total"]})

        if prod and prod.docu_cat_slug and prod.docu_item_id:
            cart_data = get_cart()
            if qty_int <= 0:
                cart_data.pop(pid, None)
            else:
                cart_data[pid] = 1
            session["cart"] = cart_data
            summ = cart_summary(catalog)
            return jsonify({"ok": True, "count": summ["count"], "total": summ["total"]})

        cart_data = get_cart()
        if qty_int <= 0:
            cart_data.pop(pid, None)
        else:
            cart_data[pid] = min(99, qty_int)
        session["cart"] = cart_data

        summ = cart_summary(catalog)
        return jsonify({"ok": True, "count": summ["count"], "total": summ["total"]})

    @app.post("/api/cart/clear")
    def api_cart_clear():
        session["cart"] = {}
        catalog = get_catalog()
        summ = cart_summary(catalog)
        return jsonify({"ok": True, "count": summ["count"], "total": summ["total"]})

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)