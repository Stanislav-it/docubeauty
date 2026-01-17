import os
import re
import hashlib
import zipfile
import shutil
import tempfile
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

CATALOG_ROOT = Path(r"C:\produkty")
PROJECT_ROOT = Path(r"C:\ex_8")

CARDS_ROOT = PROJECT_ROOT / "static" / "cards"
ITEMS_ROOT = CARDS_ROOT / "items"

ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt"}

OUT_W = 900
OUT_H = 560

def slugify(name: str) -> str:
    n = unicodedata.normalize("NFKD", name)
    out = []
    for ch in n:
        if unicodedata.category(ch) == "Mn":
            continue
        out.append(ch if ord(ch) < 128 else "-")
    s = "".join(out).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "item"

def md5_10(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:10]

def item_id_from_key(key: str) -> str:
    base = os.path.basename(key)
    return f"{slugify(base)}-{md5_10(key)}"

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def get_font(size: int):
    candidates = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()

def fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))

def render_pdf_first_page(pdf_path: Path) -> Image.Image:
    doc = fitz.open(str(pdf_path))
    try:
        page = doc.load_page(0)
        # масштаб для читабельности
        mat = fitz.Matrix(2.0, 2.0)  # ~144 dpi
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img
    finally:
        doc.close()

def render_image_file(img_path: Path) -> Image.Image:
    return Image.open(img_path).convert("RGB")

def render_txt_file(txt_path: Path) -> Image.Image:
    canvas = Image.new("RGB", (OUT_W, OUT_H), (245, 246, 248))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, OUT_W, 80], fill=(20, 26, 38))
    d.text((24, 24), "DocuBeauty — Preview", font=get_font(22), fill=(255, 255, 255))

    try:
        text = txt_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""

    lines = text.splitlines()[:18]
    y = 110
    font = get_font(18)
    for line in lines:
        if len(line) > 110:
            line = line[:107] + "…"
        d.text((24, y), line, font=font, fill=(20, 26, 38))
        y += 24

    return canvas

def save_preview_for_file(src_path: Path, out_png: Path):
    ext = src_path.suffix.lower()
    ensure_dir(out_png.parent)

    if ext == ".pdf":
        img = render_pdf_first_page(src_path)
        img = fit_cover(img, OUT_W, OUT_H)
        img.save(out_png, "PNG", optimize=True)
        return

    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        img = render_image_file(src_path)
        img = fit_cover(img, OUT_W, OUT_H)
        img.save(out_png, "PNG", optimize=True)
        return

    if ext == ".txt":
        img = render_txt_file(src_path)
        img.save(out_png, "PNG", optimize=True)
        return

def list_categories():
    cats = []
    for entry in CATALOG_ROOT.iterdir():
        if entry.is_dir():
            cats.append({"name": entry.name, "kind": "dir", "path": entry})
        elif entry.is_file() and entry.suffix.lower() == ".zip":
            cats.append({"name": entry.stem, "kind": "zip", "path": entry})
    cats.sort(key=lambda x: x["name"].upper())
    return cats

def iter_items_for_dir(cat_dir: Path):
    root = cat_dir
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in ALLOWED_EXT:
            continue
        rel_display = p.relative_to(root).as_posix()
        key = str(p)  # absolute для md5
        yield {"display": rel_display, "ext": ext, "key": key, "open_path": p}

def iter_items_for_zip(zip_path: Path):
    with zipfile.ZipFile(zip_path, "r") as z:
        for info in z.infolist():
            name = info.filename
            if not name or name.endswith("/"):
                continue
            ext = Path(name).suffix.lower()
            if ext not in ALLOWED_EXT:
                continue
            yield {"display": name, "ext": ext, "key": name, "zip_path": zip_path, "member": name}

def extract_zip_member(zip_path: Path, member: str, temp_dir: Path) -> Path:
    out_path = temp_dir / os.path.basename(member)
    with zipfile.ZipFile(zip_path, "r") as z:
        with z.open(member) as src, open(out_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return out_path

def main():
    if not CATALOG_ROOT.exists():
        raise SystemExit(f"Каталог не найден: {CATALOG_ROOT}")
    if not PROJECT_ROOT.exists():
        raise SystemExit(f"Проект не найден: {PROJECT_ROOT}")

    ensure_dir(CARDS_ROOT)
    ensure_dir(ITEMS_ROOT)

    categories = list_categories()
    if not categories:
        print("Категорий не найдено.")
        return

    tmp_base = Path(tempfile.mkdtemp(prefix="docubeauty_previews_"))
    try:
        for cat in categories:
            cat_name = cat["name"]
            cat_kind = cat["kind"]
            cat_slug = slugify(cat_name)

            print(f"\n=== CATEGORY: {cat_name} ({cat_kind}) -> {cat_slug} ===")

            items = list(iter_items_for_dir(cat["path"])) if cat_kind == "dir" else list(iter_items_for_zip(cat["path"]))
            items.sort(key=lambda x: x["display"].lower())

            if not items:
                print("  (нет файлов подходящих расширений)")
                continue

            first_item_png = None

            for it in items:
                item_id = item_id_from_key(it["key"])
                out_png = ITEMS_ROOT / cat_slug / f"{item_id}.png"

                if out_png.exists():
                    if first_item_png is None:
                        first_item_png = out_png
                    continue

                if cat_kind == "dir":
                    src_file = it["open_path"]
                else:
                    temp_dir = tmp_base / f"{cat_slug}_{item_id}"
                    ensure_dir(temp_dir)
                    src_file = extract_zip_member(it["zip_path"], it["member"], temp_dir)

                try:
                    print(f"  PREVIEW: {it['display']} -> {out_png.name}")
                    save_preview_for_file(src_file, out_png)
                except Exception as e:
                    print(f"  ERROR: {it['display']} ({e})")
                    continue

                if first_item_png is None and out_png.exists():
                    first_item_png = out_png

            cat_png = CARDS_ROOT / f"{cat_slug}.png"
            if first_item_png and not cat_png.exists():
                print(f"  CATEGORY IMG: {cat_png.name} <= {first_item_png.name}")
                shutil.copyfile(first_item_png, cat_png)

    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)

    print("\nDONE")

if __name__ == "__main__":
    main()
