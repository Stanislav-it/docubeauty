from __future__ import annotations

import html as py_html
import json
import math
import os
import re
import unicodedata
import time
import shutil
import posixpath
import zipfile
import hashlib
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



import os

STRIPE_SECRET_KEY_DEFAULT = os.getenv(
    "STRIPE_SECRET_KEY",
    "sk_test_REPLACE_WITH_ENV_VARIABLE"
)

STRIPE_PUBLISHABLE_KEY_DEFAULT = os.getenv(
    "STRIPE_PUBLISHABLE_KEY",
    "pk_test_REPLACE_WITH_ENV_VARIABLE"
)


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
# DocuBeauty dynamic catalog (48 kategorii z C:\produkty)
# -------------------------
DOCUBEAUTY_PRODUCTS_ROOT = os.getenv("DOCUBEAUTY_PRODUCTS_ROOT", r"C:\produkty")

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

    # -------------------------
    # Digital goods (downloads after payment)
    # -------------------------
    DIGITAL_GOODS_DIR = os.path.join(app.root_path, "digital_goods")
    DIGITAL_MANIFEST = os.path.join(DIGITAL_GOODS_DIR, "manifest.json")
    DOWNLOAD_TTL_SECONDS = int(os.getenv("DOWNLOAD_TTL_SECONDS", "604800"))  # 7 days

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
            # Best-effort
            pass

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
        """
        Loads catalog from:
        - export_all/products.json (preferred, parsed from 1cart)
        - data/products.json (fallback demo)
        """
        items: List[Product] = []

        price_overrides = load_price_overrides()
        desc_overrides = load_description_overrides()

        # If DocuBeauty catalog exists on this machine (default C:\produkty), use it as the shop source.
        docu_products = build_docubeauty_products(app.root_path)
        if docu_products:
            prods = apply_price_overrides(docu_products, price_overrides)
            prods = apply_description_overrides(prods, desc_overrides)
            return prods


        if os.path.exists(EXPORT_PRODUCTS):
            with open(EXPORT_PRODUCTS, "r", encoding="utf-8") as f:
                raw = json.load(f)

            for x in raw:
                pid = str(x.get("product_id", "")).strip()
                title = str(x.get("title", "")).strip()
                if not pid or not title:
                    continue

                category = str(x.get("category_name", "Bez kategorii")).strip() or "Bez kategorii"
                category_url = str(x.get("category_url", "")).strip()
                description = str(x.get("description") or "").strip()

                # normalize image_files to export_all/images relative
                img_files = [str(p).replace("\\", "/") for p in (x.get("image_files") or [])]
                rel_imgs: List[str] = []
                for p in img_files:
                    p = p.lstrip("/")
                    if p.startswith("images/"):
                        p = p[len("images/"):]
                    if p:
                        rel_imgs.append(p)

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

            return items

        # Fallback demo
        if os.path.exists(FALLBACK_PRODUCTS):
            with open(FALLBACK_PRODUCTS, "r", encoding="utf-8") as f:
                raw = json.load(f)

            for x in raw:
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

        prods = apply_price_overrides(items, price_overrides)
        prods = apply_description_overrides(prods, desc_overrides)
        return prods

    def get_catalog() -> List[Product]:
        return load_products()

    def get_categories(catalog: List[Product]) -> List[str]:
        return sorted({p.category for p in catalog}, key=lambda x: x.lower())

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
        count = sum(cart.values())
        total = 0.0
        for pid, qty in cart.items():
            p = by_id.get(pid)
            if not p:
                continue
            total += p.unit_price_for_cart() * qty
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

        # DocuBeauty mode: show only category navigation cards on the main shop page.
        # Individual sellable files are displayed inside each category page.
        if any(p.docu_cat_slug for p in catalog):
            catalog = [p for p in catalog if p.docu_cat_slug and not p.docu_item_id]

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

        filtered = catalog

        if cat:
            filtered = [p for p in filtered if slugify(p.category) == cat]

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
        )

    @app.get("/api/search_suggest")
    def search_suggest():
        catalog = get_catalog()
        q = (request.args.get("q") or "").strip().lower()

        if len(q) < 2:
            return jsonify({"products": [], "categories": []})

        prod_matches = []
        for p in catalog:
            if q in p.title.lower():
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
        p = next((x for x in catalog if x.id == pid), None)
        if not p:
            return redirect(url_for("shop"))

        # DocuBeauty item-product: render a clean product page for a single file.
        if p.docu_cat_slug and p.docu_item_id:
            cat = get_docubeauty_category(app.root_path, p.docu_cat_slug)
            if not cat:
                return redirect(url_for("shop"))
            item = get_docubeauty_item_by_id(cat, p.docu_item_id)
            if not item:
                return redirect(url_for("shop"))

            thumb_rel = f"cards/items/{p.docu_cat_slug}/{p.docu_item_id}.png"
            if os.path.exists(os.path.join(app.static_folder, thumb_rel)):
                item = dict(item)
                item["thumb_rel"] = thumb_rel

            return render_template(
                "index.html",
                view="docu_item",
                title=p.title,
                item=item,
                p=p,
                docu_cat=cat,
            )

        # If this is a DocuBeauty category-product, load the included files to display on the page.
        docu_cat = None
        docu_items = []
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
                    thumb_rel = f"cards/items/{p.docu_cat_slug}/{it.get('id')}.png"
                    if os.path.exists(os.path.join(app.static_folder, thumb_rel)):
                        it["thumb_rel"] = thumb_rel

                    prod = item_product_by_id.get(str(it.get("id") or ""))
                    if prod:
                        it["product_id"] = prod.id
                        it["price"] = prod.display_price()
                    docu_items.append(it)

        return render_template(
            "index.html",
            view="product",
            title=p.title,
            p=p,
            docu_cat=docu_cat,
            docu_items=docu_items,
        )


    @app.get("/docu/<cat_slug>/<item_id>")
    def docu_item_detail(cat_slug: str, item_id: str):
        """Detail page for a single file inside a DocuBeauty package."""
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
        thumb_rel = f"cards/items/{cat_slug}/{item_id}.png"
        if os.path.exists(os.path.join(app.static_folder, thumb_rel)):
            item = dict(item)
            item["thumb_rel"] = thumb_rel

        return render_template(
            "index.html",
            view="docu_item",
            title=item.get("display", "").rsplit("/", 1)[-1],
            item=item,
            p=prod,
            docu_cat=cat,
        )


    @app.get("/open/<cat_slug>/<item_id>")
    def docu_open_item(cat_slug: str, item_id: str):
        """Direct download for DocuBeauty item (folder file or extracted from ZIP)."""
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
        is_admin = bool(session.get("is_admin"))
        if request.method == "POST":
            if not is_admin:
                username = (request.form.get("username") or "").strip()
                password = (request.form.get("password") or "").strip()
                if username == "sklep" and password == "sklep":
                    session["is_admin"] = True
                    return redirect(url_for("edit"))
                else:
                    return render_template(
                        "edit.html",
                        logged_in=False,
                        login_error="Nieprawidłowy login lub hasło.",
                    )
            else:
                # Save prices for all products visible on the page
                # Save prices and descriptions for all products visible on the page
                price_overrides = load_price_overrides()
                desc_overrides = load_description_overrides()
                catalog = get_catalog()
                changed_price = False
                changed_desc = False
                for p in catalog:
                    # --- price ---
                    field_price = f"price_{p.id}"
                    if field_price in request.form:
                        raw_price = (request.form.get(field_price) or "").strip()
                        if raw_price:
                            cleaned = (
                                raw_price.replace("zł", "")
                                .replace("ZŁ", "")
                                .replace(" ", "")
                                .replace(",", ".")
                            )
                            try:
                                val = float(cleaned)
                            except Exception:
                                val = None
                            if val is not None and val > 0:
                                if price_overrides.get(p.id) != val:
                                    price_overrides[p.id] = val
                                    changed_price = True

                    # --- description ---
                    field_desc = f"desc_{p.id}"
                    if field_desc in request.form:
                        raw_desc = (request.form.get(field_desc) or "").strip()
                        if not raw_desc:
                            if p.id in desc_overrides:
                                desc_overrides.pop(p.id)
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

        # GET: show login or editor
        is_admin = bool(session.get("is_admin"))
        if not is_admin:
            return render_template("edit.html", logged_in=False)

        catalog = get_catalog()
        # Group products by category for easier editing
        grouped: Dict[str, List[Product]] = {}
        for p in catalog:
            grouped.setdefault(p.category, []).append(p)
        # Sort categories and products
        groups = []
        for cat_name in sorted(grouped.keys(), key=lambda x: x.lower()):
            prods = sorted(grouped[cat_name], key=lambda p: p.title.lower())
            groups.append((cat_name, prods))

        return render_template("edit.html", logged_in=True, groups=groups, saved=(request.args.get("saved") == "1"))

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


        # Build download links for purchased items.
        # - DocuBeauty: products are categories (dbcat:<slug>), and we expose:
        #   * bundle ZIP (whole product)
        #   * individual files inside the category (watermarked previews elsewhere; downloads are originals)
        # - Legacy: use digital_goods/manifest.json mapping.
        catalog = get_catalog()
        by_id = {p.id: p for p in catalog}

        docu_cats: List[Product] = []
        docu_items: List[Product] = []
        legacy_product_ids: List[str] = []

        for pid in product_ids:
            p = by_id.get(pid)
            if p and p.docu_cat_slug and p.docu_item_id:
                docu_items.append(p)
            elif p and p.docu_cat_slug and not p.docu_item_id:
                docu_cats.append(p)
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
            if bundle_url is None and len(product_ids) == 1:
                bundle_url = this_url

        # DocuBeauty category bundles + individual files (kept for backward compatibility)
        for p in docu_cats:
            cat = get_docubeauty_category(app.root_path, p.docu_cat_slug)
            if not cat:
                continue

            # Bundle (one ZIP for the whole product)
            try:
                token = make_download_token(session_id, {"kind": "docu_bundle", "cat": p.docu_cat_slug})
                this_bundle_url = url_for("download_file", token=token)
                bundle_name = os.path.basename(cat.get("source_path") or "") or f"{p.docu_cat_slug}.zip"
                downloads.append({"name": f"{p.title} — {bundle_name}", "url": this_bundle_url})
                # Use the first bundle as the primary CTA when there is exactly one purchased product
                if bundle_url is None and len(product_ids) == 1:
                    bundle_url = this_bundle_url
            except Exception:
                pass

            # Individual files
            for it in list_docubeauty_items_for_category(cat):
                token = make_download_token(session_id, {"kind": "docu", "cat": p.docu_cat_slug, "item": it.get("id")})
                downloads.append({"name": f"{p.title} / {it.get('display')}", "url": url_for("download_file", token=token)})

        # Legacy digital_goods downloads (manifest-based)
        files: List[str] = []
        bundle_file: Optional[str] = None
        for pid in legacy_product_ids:
            f_list, b_file = load_manifest_files_for_product(pid)
            files.extend(f_list)
            if b_file and not bundle_file:
                bundle_file = b_file

        for rel in files:
            token = make_download_token(session_id, rel)
            downloads.append({"name": os.path.basename(rel), "url": url_for("download_file", token=token)})

        if bundle_file and bundle_url is None:
            token = make_download_token(session_id, bundle_file)
            bundle_url = url_for("download_file", token=token)
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

            expected_pid = f"dbcat:{cat_slug}"
            if expected_pid not in purchased_ids:
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
            item_id = str(data.get("item") or "").strip()
            if not item_id:
                abort(400, "Invalid link")

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

        # Legacy digital_goods file download (manifest-based)
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
        if prod and prod.docu_cat_slug and not prod.docu_item_id:
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
