import os
import re
import unicodedata
import hashlib
import zipfile
import posixpath
from io import BytesIO
from flask import Flask, render_template, send_file, abort, url_for

from PIL import Image, ImageDraw, ImageFont

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Каталог с продуктами на вашей машине
CATALOG_ROOT = r"C:\produkty"
# ---- katalog: metadane kategorii (ceny startowe i krótkie opisy) ----
# Uwaga: to są ceny "od" (orientacyjne) i krótkie opisy prezentowane w UI.
CATEGORY_META = {
    "autologiczny-wypelniacz-pakiet-dokumentacji": {"name_pl": "Autologiczny wypełniacz — pakiet dokumentacji", "price_from": 89, "short_desc": "Zestaw zgód, ankiet i kart zabiegowych do zabiegów z autologicznym wypełniaczem."},
    "beauty-plan-druk": {"name_pl": "Beauty Plan — druk (PDF)", "price_from": 29, "short_desc": "Gotowy szablon planu pielęgnacji/terapii do wydruku i przekazania klientce."},
    "certyfikaty": {"name_pl": "Certyfikaty — szablony", "price_from": 29, "short_desc": "Edytowalne szablony certyfikatów ukończenia zabiegu/szkolenia (PDF/Canva)."},
    "depilacja-laserowa-dokumenty-zabiegowe-pakiet": {"name_pl": "Depilacja laserowa — pakiet dokumentów zabiegowych", "price_from": 79, "short_desc": "Komplet dokumentów: wywiad, przeciwwskazania, zgody i karta zabiegowa."},
    "elektroepilacja-dokumenty-zabiegowe": {"name_pl": "Elektroepilacja — dokumenty zabiegowe", "price_from": 69, "short_desc": "Zgody, wywiad i karta zabiegowa do elektroepilacji."},
    "fizjoterapia-dokumentacja-pakiet": {"name_pl": "Fizjoterapia — pakiet dokumentacji", "price_from": 79, "short_desc": "Wywiad, zgody i karta wizyty do prowadzenia dokumentacji fizjoterapeutycznej."},
    "j-ang-przedluzanie-rzes-dokumenty": {"name_pl": "Przedłużanie rzęs — dokumenty (PL/EN)", "price_from": 69, "short_desc": "Dwujęzyczny zestaw formularzy: konsultacja, zgoda, zalecenia pozabiegowe."},
    "keratynowe-prostowanie-wlosow-dokumenty-zabiegowe-pakiet": {"name_pl": "Keratynowe prostowanie włosów — pakiet dokumentów", "price_from": 69, "short_desc": "Wywiad, zgoda, instrukcje pielęgnacji i karta zabiegowa."},
    "kosmetyczne-wybielanie-zebow-dokumentacja-zabiegowa": {"name_pl": "Kosmetyczne wybielanie zębów — dokumentacja zabiegowa", "price_from": 69, "short_desc": "Wywiad, przeciwwskazania, zgody i zalecenia po zabiegu."},
    "laminacja-brwi-dokumenty-canva": {"name_pl": "Laminacja brwi — dokumenty (Canva)", "price_from": 69, "short_desc": "Szablony do edycji w Canva: wywiad, zgoda, karta zabiegowa."},
    "laminacja-brwi": {"name_pl": "Laminacja brwi — dokumentacja zabiegowa", "price_from": 59, "short_desc": "Gotowe formularze PDF do laminacji brwi."},
    "laser-frakcyjny-co2-dokumentacja-zabiegowa": {"name_pl": "Laser frakcyjny CO2 — dokumentacja zabiegowa", "price_from": 99, "short_desc": "Komplet zgód i formularzy zgodnych z praktyką medycyny estetycznej."},
    "lifting-laminacja-rzes-dokumentacja-zabiegowa": {"name_pl": "Lifting i laminacja rzęs — dokumentacja", "price_from": 59, "short_desc": "Wywiad, zgoda i karta zabiegowa oraz zalecenia."},
    "lipoliza-iniekcyjna-dokumentacja-zabiegowa": {"name_pl": "Lipoliza iniekcyjna — dokumentacja zabiegowa", "price_from": 99, "short_desc": "Formularze: kwalifikacja, przeciwwskazania, zgoda i karta zabiegowa."},
    "makijaz-permanentny-pakiet-dokumentacji": {"name_pl": "Makijaż permanentny (PMU) — pakiet dokumentacji", "price_from": 99, "short_desc": "Komplet formularzy konsultacyjnych i zgód oraz zalecenia."},
    "manicure-dokumenty-zabiegowe-zestaw": {"name_pl": "Manicure — zestaw dokumentów zabiegowych", "price_from": 49, "short_desc": "Karta klienta, zgoda i zalecenia do usług manicure."},
    "masaz-dokumenty-zabiegowe": {"name_pl": "Masaż — dokumenty zabiegowe", "price_from": 49, "short_desc": "Wywiad, zgoda i karta zabiegowa do masażu."},
    "mezoterapia-beziglowa-dokumentacja-zabiegowa": {"name_pl": "Mezoterapia bezigłowa — dokumentacja zabiegowa", "price_from": 79, "short_desc": "Formularze kwalifikacji, zgody i zalecenia pozabiegowe."},
    "mezoterapia-iglowa-dokumentacja-zabiegowa": {"name_pl": "Mezoterapia igłowa — dokumentacja zabiegowa", "price_from": 99, "short_desc": "Wywiad medyczny, przeciwwskazania, zgoda i karta zabiegowa."},
    "mezoterapia-mikroiglowa-dokumentacja-zabiegowa-1": {"name_pl": "Mezoterapia mikroigłowa — dokumentacja zabiegowa", "price_from": 79, "short_desc": "Zestaw formularzy do terapii mikroigłowej (np. Dermapen)."},
    "miesnie-twarzy": {"name_pl": "Mięśnie twarzy — plansza/anatomia", "price_from": 19, "short_desc": "Pomocnicza plansza do konsultacji, edukacji i szkoleń."},
    "modelowanie-ust-dokumentacja-zabiegowa-pakiet": {"name_pl": "Modelowanie ust — pakiet dokumentacji", "price_from": 99, "short_desc": "Komplet formularzy kwalifikacji i zgód do zabiegów w obrębie ust."},
    "nici-pdo": {"name_pl": "Nici PDO — dokumentacja zabiegowa", "price_from": 99, "short_desc": "Wywiad, przeciwwskazania, zgoda i karta zabiegowa."},
    "oczyszczanie-wodorowe-1": {"name_pl": "Oczyszczanie wodorowe — dokumentacja", "price_from": 59, "short_desc": "Zgoda, karta zabiegowa i zalecenia po zabiegu."},
    "osocze-bogatoplytkowe": {"name_pl": "Osocze bogatopłytkowe (PRP) — dokumentacja", "price_from": 109, "short_desc": "Kwalifikacja, zgody i karta zabiegowa do terapii PRP."},
    "pakiet-dokumentacji-endermologia": {"name_pl": "Endermologia — pakiet dokumentacji", "price_from": 79, "short_desc": "Wywiad, zgoda, karta serii zabiegów i zalecenia."},
    "pedicure-dokumentacja-zabiegowa-zestaw": {"name_pl": "Pedicure — zestaw dokumentacji", "price_from": 49, "short_desc": "Formularze dla pedicure kosmetycznego: karta, zgoda i zalecenia."},
    "peeling-weglowy-dokumenty-zabiegowe-zestaw": {"name_pl": "Peeling węglowy — zestaw dokumentów", "price_from": 69, "short_desc": "Wywiad, zgoda i zalecenia do zabiegu peelingu węglowego."},
    "peelingi-chemiczne": {"name_pl": "Peelingi chemiczne — dokumentacja zabiegowa", "price_from": 79, "short_desc": "Kwalifikacja, przeciwwskazania, zgoda i zalecenia."},
    "permanent-makeup-consultation-forms": {"name_pl": "Permanent Makeup — formularze konsultacyjne (EN)", "price_from": 69, "short_desc": "Anglojęzyczne formularze konsultacji i zgody dla usług PMU."},
    "piercing": {"name_pl": "Piercing — dokumentacja zabiegowa", "price_from": 59, "short_desc": "Wywiad, zgoda, instrukcja pielęgnacji i karta zabiegu."},
    "pmu-canva": {"name_pl": "PMU — dokumenty (Canva)", "price_from": 89, "short_desc": "Szablony PMU do edycji w Canva: konsultacja, zgoda i zalecenia."},
    "podologia-dokumenty-zabiegowe": {"name_pl": "Podologia — dokumenty zabiegowe", "price_from": 79, "short_desc": "Wywiad, zgoda, karta zabiegowa i zalecenia pozabiegowe."},
    "przedluzanie-rzes": {"name_pl": "Przedłużanie rzęs — dokumentacja zabiegowa", "price_from": 59, "short_desc": "Wywiad, zgoda i zalecenia pielęgnacyjne po aplikacji."},
    "regulamin-salonu": {"name_pl": "Regulamin salonu — szablon", "price_from": 39, "short_desc": "Gotowy regulamin usług, zapisów i płatności do dopasowania."},
    "rf-mikroiglowa": {"name_pl": "RF mikroigłowa — dokumentacja zabiegowa", "price_from": 99, "short_desc": "Zestaw formularzy do zabiegów RF mikroigłowej."},
    "rodo": {"name_pl": "RODO/GDPR — pakiet dokumentów", "price_from": 69, "short_desc": "Klauzule informacyjne, zgody i podstawowe wzory do salonu."},
    "salon-fryzjerski-dokumentacja": {"name_pl": "Salon fryzjerski — dokumentacja i formularze", "price_from": 59, "short_desc": "Karta klienta, zgody i zalecenia do usług fryzjerskich."},
    "stymulatory-tkankowe": {"name_pl": "Stymulatory tkankowe — dokumentacja", "price_from": 109, "short_desc": "Kwalifikacja, przeciwwskazania, zgoda i karta zabiegowa."},
    "tatuaz": {"name_pl": "Tatuaż — dokumentacja zabiegowa", "price_from": 59, "short_desc": "Wywiad, zgoda, pielęgnacja i karta zabiegu."},
    "toksyna-botulinowa-botoks-pakiet-dokumentacji": {"name_pl": "Toksyna botulinowa (botoks) — pakiet dokumentacji", "price_from": 109, "short_desc": "Formularze med.-estetyczne: kwalifikacja, zgody i karta zabiegowa."},
    "tooth-gems-dokumentacja-zabiegowa-pakiet": {"name_pl": "Tooth Gems — pakiet dokumentacji zabiegowej", "price_from": 59, "short_desc": "Zgody, wywiad i zalecenia do aplikacji biżuterii nazębnej."},
    "unaczynienie-twarzy": {"name_pl": "Unaczynienie twarzy — plansza/anatomia", "price_from": 19, "short_desc": "Plansza poglądowa przydatna w konsultacjach i szkoleniach."},
    "unerwienie-twarzy": {"name_pl": "Unerwienie twarzy — plansza/anatomia", "price_from": 19, "short_desc": "Plansza poglądowa dotycząca unerwienia twarzy do edukacji."},
    "uniwersalne-karty-zabiegowe-1": {"name_pl": "Uniwersalne karty zabiegowe — zestaw", "price_from": 39, "short_desc": "Uniwersalne formularze do różnych usług: karta zabiegu i zalecenia."},
    "usuwanie-tatuazu-pmu-dokumenty-zabiegowe-zestaw": {"name_pl": "Usuwanie tatuażu/PMU — zestaw dokumentów", "price_from": 79, "short_desc": "Zgody, przeciwwskazania i zalecenia do laserowego usuwania."},
    "wolumetria": {"name_pl": "Wolumetria twarzy — dokumentacja zabiegowa", "price_from": 109, "short_desc": "Komplet formularzy do zabiegów wolumetrycznych (wypełniacze)."},
    "zgoda": {"name_pl": "Zgoda na zabieg — uniwersalny wzór", "price_from": 19, "short_desc": "Uniwersalny formularz zgody z miejscem na opis procedury."},
}

def enrich_category(cat: dict) -> dict:
    """Uzupełnia dane kategorii o pola UI: display_name, price_from, short_desc."""
    meta = CATEGORY_META.get(cat.get("slug"))
    if meta:
        cat["display_name"] = meta.get("name_pl") or cat.get("name")
        cat["price_from"] = meta.get("price_from")
        cat["short_desc"] = meta.get("short_desc")
    else:
        cat["display_name"] = cat.get("name")
        cat["price_from"] = None
        cat["short_desc"] = None
    return cat

CACHE_DIR = os.path.join(APP_DIR, "static", "cache")
CARDS_DIR = os.path.join(APP_DIR, "static", "cards")

WM_DIR = os.path.join(APP_DIR, "_wm_cache")
WATERMARK_TEXT = "docubeauty"

def ensure_watermarked_png(src_path: str) -> str:
    """
    Создаёт (или переиспользует) водяной знак на PNG и возвращает путь
    к закешированной водяной версии.
    """
    os.makedirs(WM_DIR, exist_ok=True)
    try:
        rel = os.path.relpath(src_path, APP_DIR)
    except Exception:
        rel = os.path.basename(src_path)

    out_path = os.path.join(WM_DIR, rel)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    try:
        if os.path.exists(out_path):
            if os.path.getmtime(out_path) >= os.path.getmtime(src_path):
                return out_path
    except Exception:
        pass

    # применяем watermark
    try:
        base = Image.open(src_path).convert("RGBA")
        w, h = base.size
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # размер шрифта адаптивно, но минималистично
        font_size = max(18, int(min(w, h) / 26))
        font = get_font(font_size)

        text = WATERMARK_TEXT
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        margin = max(14, int(min(w, h) / 40))
        x = w - tw - margin
        y = h - th - margin

        # легкая тень
        draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 70))
        # основной текст
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 90))

        out = Image.alpha_composite(base, overlay).convert("RGB")
        out.save(out_path, "PNG", optimize=True)
        return out_path
    except Exception:
        # если что-то пошло не так — отдаем оригинал
        return src_path

app = Flask(__name__, static_folder=None)

# -------- naming helpers --------
def slugify(name: str) -> str:
    norm = unicodedata.normalize("NFKD", name)
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
    return s or "item"

def item_id_from_path(rel_path: str) -> str:
    # rel_path: raw filename (zip internal) or absolute file path in folder category
    h = hashlib.md5(rel_path.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{slugify(os.path.basename(rel_path))}-{h}"

# -------- scanning categories & items --------
def scan_categories():
    if not os.path.isdir(CATALOG_ROOT):
        return []

    entries = []
    for name in os.listdir(CATALOG_ROOT):
        full = os.path.join(CATALOG_ROOT, name)
        if os.path.isdir(full):
            cat_name = name
            kind = "dir"
        elif name.lower().endswith(".zip"):
            cat_name = name[:-4]
            kind = "zip"
        else:
            continue

        slug = slugify(cat_name)
        entries.append({
            "name": cat_name,
            "slug": slug,
            "kind": kind,
            "source_path": full,
        })

    # Enrich with UI metadata (prices/descriptions) if known
    for c in entries:
        enrich_category(c)
    entries.sort(key=lambda x: x["name"].upper())
    return entries

def get_category(slug: str):
    cats = scan_categories()
    return next((c for c in cats if c["slug"] == slug), None)

def is_safe_zip_member(member: str) -> bool:
    # Only regular files; avoid traversal.
    if not member or member.endswith("/"):
        return False
    # Normalize POSIX path (zip always uses '/')
    norm = posixpath.normpath(member)
    if norm.startswith("../") or norm.startswith("..\\") or norm.startswith(".."):
        return False
    if norm.startswith("/") or norm.startswith("\\"):
        return False
    if "__macosx" in norm.lower():
        return False
    return True

def list_items_for_category(cat):
    items = []
    if cat["kind"] == "dir":
        # List files recursively? user asked "files of folder" — typically direct children.
        # We'll include files in the folder (recursively) but show relative path for clarity.
        root = cat["source_path"]
        for r, _, files in os.walk(root):
            for fn in files:
                full = os.path.join(r, fn)
                rel = os.path.relpath(full, root)
                items.append({
                    "display": rel.replace("\\", "/"),
                    "rel": rel.replace("\\", "/"),
                    "abs": full,
                    "id": item_id_from_path(full),
                    "ext": os.path.splitext(fn)[1].lower(),
                })
        items.sort(key=lambda x: x["display"].lower())
        return items

    # ZIP
    zp = cat["source_path"]
    try:
        with zipfile.ZipFile(zp, "r") as z:
            for info in z.infolist():
                member = info.filename
                if not is_safe_zip_member(member):
                    continue
                # skip huge binaries? no, list all
                items.append({
                    "display": member,
                    "rel": member,
                    "abs": None,
                    "id": item_id_from_path(member),
                    "ext": os.path.splitext(member)[1].lower(),
                })
    except Exception:
        return []
    items.sort(key=lambda x: x["display"].lower())
    return items

def get_item_by_id(cat, item_id: str):
    for it in list_items_for_category(cat):
        if it["id"] == item_id:
            return it
    return None

# -------- card image generation --------
def get_font(size: int):
    candidates = [
        os.path.join(APP_DIR, "fonts", "DejaVuSans.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def wrap_lines(draw, text, font, max_w):
    words = text.split()
    lines = []
    line = ""
    for w in words:
        test = (line + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_w:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines

def ensure_category_card(cat):
    os.makedirs(CARDS_DIR, exist_ok=True)
    path = os.path.join(CARDS_DIR, f"{cat['slug']}.png")
    if os.path.exists(path):
        return path

    W, H = 900, 560
    img = Image.new("RGB", (W, H), (245, 246, 248))
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 90], fill=(20, 26, 38))
    d.text((30, 28), "DocuBeauty — Katalog", font=get_font(22), fill=(255, 255, 255))

    title_font = get_font(44)
    lines = wrap_lines(d, cat.get("display_name", cat["name"]), title_font, W - 120)
    size = 44
    while len(lines) > 4 and size > 24:
        size -= 4
        title_font = get_font(size)
        lines = wrap_lines(d, cat.get("display_name", cat["name"]), title_font, W - 120)

    y = 140
    for line in lines[:5]:
        bbox = d.textbbox((0, 0), line, font=title_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((W - tw) / 2, y), line, font=title_font, fill=(20, 26, 38))
        y += th + 10

    d.rectangle([0, H - 80, W, H], fill=(255, 255, 255))
    d.text((30, H - 58), f"Slug: {cat['slug']}", font=get_font(22), fill=(80, 90, 105))
    # Price (if available)
    if cat.get('price_from'):
        d.text((30, H - 30), f"Od {cat['price_from']} zł", font=get_font(22), fill=(80, 90, 105))

    img.save(path, "PNG", optimize=True)
    return path

def ensure_item_card(cat, item):
    # cache item cards under static/cards/items/<cat_slug>/
    out_dir = os.path.join(CARDS_DIR, "items", cat["slug"])
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{item['id']}.png")
    if os.path.exists(path):
        return path

    W, H = 900, 560
    img = Image.new("RGB", (W, H), (245, 246, 248))
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 90], fill=(20, 26, 38))
    d.text((30, 28), f"DocuBeauty — {cat['name']}", font=get_font(22), fill=(255, 255, 255))

    # Big title: filename (use basename for readability)
    title = os.path.basename(item["display"])
    subtitle = item["display"] if item["display"] != title else ""

    title_font = get_font(44)
    lines = wrap_lines(d, title, title_font, W - 120)
    size = 44
    while len(lines) > 3 and size > 24:
        size -= 4
        title_font = get_font(size)
        lines = wrap_lines(d, title, title_font, W - 120)

    y = 150
    for line in lines[:4]:
        bbox = d.textbbox((0, 0), line, font=title_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((W - tw) / 2, y), line, font=title_font, fill=(20, 26, 38))
        y += th + 10

    if subtitle:
        sub_font = get_font(22)
        # show up to one line of path
        sub = subtitle if len(subtitle) <= 80 else (subtitle[:77] + "…")
        bbox = d.textbbox((0, 0), sub, font=sub_font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        d.text(((W - tw)/2, y+10), sub, font=sub_font, fill=(80, 90, 105))

    d.rectangle([0, H - 80, W, H], fill=(255, 255, 255))
    d.text((30, H - 58), f"ID: {item['id']}   EXT: {item['ext'] or '-'}", font=get_font(22), fill=(80, 90, 105))

    img.save(path, "PNG", optimize=True)
    return path

# -------- file serving (zip or folder) --------
def ensure_cached_zip_file(cat, item):
    # Extract a single member to cache path: static/cache/<cat_slug>/<id>/<basename>
    out_dir = os.path.join(CACHE_DIR, cat["slug"], item["id"])
    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.basename(item["rel"])
    out_path = os.path.join(out_dir, filename)
    if os.path.exists(out_path):
        return out_path

    zp = cat["source_path"]
    with zipfile.ZipFile(zp, "r") as z:
        member = item["rel"]
        if not member or not is_safe_zip_member(member):
            raise ValueError("Unsafe member")
        with z.open(member, "r") as src, open(out_path, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
    return out_path

# -------- routes --------
def get_first_item_preview_path(cat) -> str:
    """
    Category preview = preview of the FIRST file inside the category (sorted).
    Priority:
      1) prebuilt preview: static/cards/items/<cat_slug>/<item_id>.png
      2) fallback: generated item card (ensure_item_card)
      3) if no items: generated category card
    """
    items = list_items_for_category(cat)
    if not items:
        return ensure_category_card(cat)
    first = items[0]
    prebuilt = os.path.join(CARDS_DIR, "items", cat["slug"], f"{first['id']}.png")
    if os.path.exists(prebuilt):
        return prebuilt
    return ensure_item_card(cat, first)


@app.route("/")
def home():
    categories = scan_categories()
    return render_template("index.html", categories=categories)

@app.route("/category/<slug>")
def category_view(slug):
    cat = get_category(slug)
    if not cat:
        abort(404)
    items = list_items_for_category(cat)
    return render_template("category.html", category=cat, items=items)

@app.route("/card/<slug>.png")
def category_card(slug):
    cat = get_category(slug)
    if not cat:
        abort(404)

    # Category preview = FIRST file preview
    path = get_first_item_preview_path(cat)

    wm_path = ensure_watermarked_png(path)
    return send_file(wm_path, mimetype="image/png")


@app.route("/itemcard/<cat_slug>/<item_id>.png")
def item_card(cat_slug, item_id):
    cat = get_category(cat_slug)
    if not cat:
        abort(404)
    item = get_item_by_id(cat, item_id)
    if not item:
        abort(404)

    # Prefer prebuilt previews generated by your script
    prebuilt = os.path.join(CARDS_DIR, "items", cat["slug"], f"{item_id}.png")
    if os.path.exists(prebuilt):
        path = prebuilt
    else:
        path = ensure_item_card(cat, item)

    wm_path = ensure_watermarked_png(path)
    return send_file(wm_path, mimetype="image/png")


@app.route("/open/<cat_slug>/<item_id>")
def open_item(cat_slug, item_id):
    cat = get_category(cat_slug)
    if not cat:
        abort(404)
    item = get_item_by_id(cat, item_id)
    if not item:
        abort(404)

    try:
        if cat["kind"] == "dir":
            return send_file(item["abs"], as_attachment=True, download_name=os.path.basename(item["abs"]))
        # zip
        cached = ensure_cached_zip_file(cat, item)
        return send_file(cached, as_attachment=True, download_name=os.path.basename(cached))
    except Exception:
        abort(500)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)


def ensure_watermarked_png(src_path: str) -> str:
    """
    Watermark + lekka "cenzura" (czytelne jako podgląd, ale trudniej skopiować treść).
    - delikatna pikselizacja (mosaic) + lekki blur
    - lekki spadek kontrastu
    - diagonalny, półprzezroczysty watermark "docubeauty"
    Wynik jest кешowany w static/_wm_cache.
    """
    cache_name = _wm_cache_key(src_path) + ".png"
    out_path = os.path.join(WM_CACHE_DIR, cache_name)
    if os.path.exists(out_path):
        return out_path

    img = Image.open(src_path).convert("RGBA")
    w, h = img.size

    # --- soft censorship: mosaic + blur + slight contrast drop ---
    # Mosaic: downscale then upscale with nearest (reduces readability)
    scale = 0.38  # smaller = stronger mosaic; ~0.38 is "light but noticeable"
    mw = max(1, int(w * scale))
    mh = max(1, int(h * scale))
    mosaic = img.resize((mw, mh), resample=Image.BILINEAR).resize((w, h), resample=Image.NEAREST)

    # Blend mosaic with original so it's not fully destroyed
    img = Image.blend(img, mosaic, alpha=0.55)

    # Small blur to soften edges (especially text)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.6))

    # Slight contrast reduction
    img = ImageEnhance.Contrast(img).enhance(0.88)

    # --- watermark diagonal repeat ---
    font_size = max(18, int(min(w, h) * 0.045))
    font = _get_font_for_wm(font_size)
    text = "docubeauty"
    fill = (255, 255, 255, 75)

    step_x = max(240, int(w * 0.30))
    step_y = max(200, int(h * 0.28))

    big_w, big_h = int(w * 1.6), int(h * 1.6)
    big = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(big)

    for y in range(0, big_h, step_y):
        for x in range(0, big_w, step_x):
            bd.text((x, y), text, font=font, fill=fill)

    big = big.rotate(22, resample=Image.BICUBIC, expand=False)
    left = (big_w - w) // 2
    top = (big_h - h) // 2
    overlay = big.crop((left, top, left + w, top + h))

    out = Image.alpha_composite(img, overlay)

    # small footer mark
    d2 = ImageDraw.Draw(out)
    small = _get_font_for_wm(max(14, int(font_size * 0.45)))
    d2.text((16, h - 30), "docubeauty", font=small, fill=(255, 255, 255, 120))

    out.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path

