import argparse
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


PRICE_RE = re.compile(r"Cena:\s*([\d\s.,]+)\s*zł", re.IGNORECASE)


def slugify(s: str, max_len: int = 80) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s, flags=re.UNICODE).strip("-")
    return s[:max_len] if len(s) > max_len else s


def normspace(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def parse_price_pln(text: str) -> Optional[float]:
    text = (text or "").replace("\xa0", " ")
    m = PRICE_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    raw = raw.replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def same_host(a: str, b: str) -> bool:
    return urlparse(a).netloc == urlparse(b).netloc


@dataclass
class Product:
    product_id: str
    url: str
    title: str
    category_name: str
    category_url: str
    price_pln: Optional[float]
    description: str
    image_urls: List[str]
    image_files: List[str]


class OneCartScraper:
    def __init__(self, base_url: str, out_dir: Path, delay: float = 0.8, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.out_dir = out_dir
        self.delay = delay
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; OneCartScraper/1.0; +https://example.com)",
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.7",
            }
        )

    def fetch_html(self, url: str) -> str:
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        time.sleep(self.delay)
        return r.text

    def discover_categories(self, homepage_url: str) -> List[Dict[str, str]]:
        html = self.fetch_html(homepage_url)
        soup = BeautifulSoup(html, "lxml")

        cats: Dict[str, str] = {}
        for a in soup.select('a[href*="/pl/category/"]'):
            href = a.get("href")
            name = normspace(a.get_text())
            if not href or not name:
                continue
            full = urljoin(homepage_url, href)
            if not same_host(full, self.base_url):
                continue
            cats[full] = name

        # Уникальные категории
        out = [{"name": cats[u], "url": u} for u in sorted(cats.keys())]
        return out

    def discover_products_from_offers(self, max_pages: int = 200) -> List[str]:
        """
        Сканирует "Oferta sprzedawcy" по страницам:
        https://.../?catalog[max_results]=24&catalog[page]=N
        """
        product_urls: Set[str] = set()

        for page in range(1, max_pages + 1):
            url = f"{self.base_url}/?catalog%5Bmax_results%5D=24&catalog%5Bpage%5D={page}"
            html = self.fetch_html(url)
            soup = BeautifulSoup(html, "lxml")

            page_links = set()
            for a in soup.select('a[href*="/pl/product/"]'):
                href = a.get("href")
                if not href:
                    continue
                full = urljoin(url, href)
                if same_host(full, self.base_url):
                    page_links.add(full)

            # Если на странице нет товаров — считаем, что пагинация закончилась
            if not page_links:
                break

            before = len(product_urls)
            product_urls |= page_links

            # Если новых ссылок не появилось — тоже можно остановиться (защита от циклов)
            if len(product_urls) == before and page > 3:
                break

        return sorted(product_urls)

    def discover_products_from_category(self, category_url: str, max_pages: int = 200) -> List[str]:
        """
        Сканирует конкретную категорию и её пагинацию (если есть).
        В 1cart часто пагинация идет параметрами catalog[page], но может отличаться —
        поэтому используем BFS по ссылкам "page" внутри категории.
        """
        visited: Set[str] = set()
        queue: List[str] = [category_url]
        product_urls: Set[str] = set()

        def looks_like_pagination_link(href: str) -> bool:
            h = href.lower()
            return ("page" in h) or ("catalog%5bpage%5d" in h) or ("catalog[page]" in h)

        while queue and len(visited) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            html = self.fetch_html(url)
            soup = BeautifulSoup(html, "lxml")

            for a in soup.select('a[href*="/pl/product/"]'):
                href = a.get("href")
                if href:
                    full = urljoin(url, href)
                    if same_host(full, self.base_url):
                        product_urls.add(full)

            # пагинация
            for a in soup.select("a[href]"):
                href = a.get("href")
                if not href:
                    continue
                full = urljoin(url, href)
                if not same_host(full, self.base_url):
                    continue
                # ограничим только этой категорией
                if "/pl/category/" in full and looks_like_pagination_link(href):
                    if full not in visited and full not in queue:
                        queue.append(full)

        return sorted(product_urls)

    def parse_product(self, product_url: str) -> Product:
        html = self.fetch_html(product_url)
        soup = BeautifulSoup(html, "lxml")

        # product_id из URL: /pl/product/<ID>/...
        parts = urlparse(product_url).path.strip("/").split("/")
        product_id = "unknown"
        try:
            idx = parts.index("product")
            product_id = parts[idx + 1]
        except Exception:
            pass

        h1 = soup.find("h1")
        title = normspace(h1.get_text()) if h1 else ""

        # Категория: ближайшая ссылка /pl/category/ перед h1
        category_name = ""
        category_url = ""
        if h1:
            prev_cat = h1.find_previous("a", href=re.compile(r"/pl/category/", re.IGNORECASE))
            if prev_cat and prev_cat.get("href"):
                category_name = normspace(prev_cat.get_text())
                category_url = urljoin(product_url, prev_cat.get("href"))

        # Цена: ищем первый блок после h1, где есть "Cena:" и "zł"
        price_pln = None
        price_tag = None
        if h1:
            for tag in h1.find_all_next():
                if not hasattr(tag, "get_text"):
                    continue
                t = normspace(tag.get_text(" "))
                if "cena:" in t.lower() and "zł" in t.lower():
                    price_pln = parse_price_pln(t)
                    price_tag = tag
                    break

        # Описание: собираем текст между h1 и price_tag (параграфы/списки),
        # плюс фильтруем системные строки
        desc_lines: List[str] = []
        if h1:
            stop_re = re.compile(r"^cena:|^dodaj do koszyka|^dostępność:|^produkt:", re.IGNORECASE)

            for el in h1.find_all_next():
                if el == price_tag:
                    break
                if not getattr(el, "name", None):
                    continue
                if el.name in ("script", "style", "nav", "footer"):
                    continue

                txt = normspace(el.get_text(" "))
                if not txt:
                    continue
                if stop_re.search(txt):
                    continue
                # избегаем дублей заголовка
                if title and txt == title:
                    continue
                # короткие «шумы» тоже пропустим
                if len(txt) < 3:
                    continue

                # берем наиболее полезные блоки
                if el.name in ("p", "li", "h2", "h3", "h4"):
                    desc_lines.append(txt)

            # дедупликация по порядку
            seen = set()
            cleaned = []
            for x in desc_lines:
                if x not in seen:
                    cleaned.append(x)
                    seen.add(x)
            desc_lines = cleaned[:200]

        description = "\n".join(desc_lines).strip()

        # Картинки: стараемся взять из ближайшего контейнера к h1, иначе — эвристика по alt/title
        image_urls: List[str] = []
        scope = None
        if h1:
            scope = h1
            for _ in range(8):
                if scope and len(scope.find_all("img")) >= 1:
                    break
                scope = scope.parent

        img_candidates = (scope.find_all("img") if scope else soup.find_all("img"))
        for img in img_candidates:
            src = img.get("data-src") or img.get("src")
            if not src:
                continue
            full = urljoin(product_url, src)
            # отфильтруем типичные лого/иконки
            alt = (img.get("alt") or "").lower()
            if "1koszyk" in alt or "logo" in alt:
                continue
            if full not in image_urls:
                image_urls.append(full)

        # если нашли слишком много (меню/иконки) — оставим только наиболее релевантные по alt
        if len(image_urls) > 10 and title:
            t = title.lower()
            prioritized = []
            for img in img_candidates:
                src = img.get("data-src") or img.get("src")
                if not src:
                    continue
                full = urljoin(product_url, src)
                alt = (img.get("alt") or "").lower()
                if t and t[:20] in alt:
                    prioritized.append(full)
            image_urls = prioritized[:5] if prioritized else image_urls[:5]

        # скачивание изображений
        cat_slug = slugify(category_name or "bez-kategorii")
        prod_slug = slugify(title or product_id)

        img_dir = self.out_dir / "images" / cat_slug
        img_dir.mkdir(parents=True, exist_ok=True)

        image_files: List[str] = []
        for i, iu in enumerate(image_urls, start=1):
            try:
                ext = os.path.splitext(urlparse(iu).path)[1].lower()
                if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                    ext = ".jpg"
                fname = f"{prod_slug}-{product_id}-{i}{ext}"
                fpath = img_dir / fname
                if not fpath.exists():
                    self.download_file(iu, fpath)
                image_files.append(str(fpath.relative_to(self.out_dir)))
            except Exception:
                # не падаем из-за одного изображения
                continue

        return Product(
            product_id=product_id,
            url=product_url,
            title=title,
            category_name=category_name or "Bez kategorii",
            category_url=category_url,
            price_pln=price_pln,
            description=description,
            image_urls=image_urls,
            image_files=image_files,
        )

    def download_file(self, url: str, out_path: Path) -> None:
        r = self.session.get(url, stream=True, timeout=self.timeout)
        r.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)
        time.sleep(self.delay)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="Напр. https://grafikareklamowa-miakienko.v.1cart.eu")
    ap.add_argument("--out", default="export_1cart", help="Папка вывода")
    ap.add_argument("--mode", choices=["all", "category"], default="all",
                    help="all = весь магазин через 'Oferta sprzedawcy'; category = только одна категория")
    ap.add_argument("--category-url", default="", help="URL категории для mode=category")
    ap.add_argument("--delay", type=float, default=0.8, help="Задержка между запросами (сек)")
    ap.add_argument("--limit", type=int, default=0, help="Ограничить кол-во товаров (0 = без лимита)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    scraper = OneCartScraper(base_url=args.base, out_dir=out_dir, delay=args.delay)

    # категории (берем с главной "Oferta sprzedawcy")
    homepage = args.base.rstrip("/") + "/"
    categories = scraper.discover_categories(homepage)
    save_json(out_dir / "categories.json", categories)

    # товары
    if args.mode == "category":
        if not args.category_url:
            raise SystemExit("Для --mode category нужно указать --category-url")
        product_urls = scraper.discover_products_from_category(args.category_url)
    else:
        product_urls = scraper.discover_products_from_offers()

    if args.limit and args.limit > 0:
        product_urls = product_urls[: args.limit]

    products: List[Dict] = []
    per_cat: Dict[str, List[Dict]] = {}

    for idx, url in enumerate(product_urls, start=1):
        print(f"[{idx}/{len(product_urls)}] {url}")
        try:
            p = scraper.parse_product(url)
            pd = asdict(p)
            products.append(pd)

            cat_slug = slugify(p.category_name or "bez-kategorii")
            per_cat.setdefault(cat_slug, []).append(pd)

        except Exception as e:
            print(f"  ERROR: {e}")

    save_json(out_dir / "products.json", products)

    # отдельно по категориям
    for cat_slug, items in per_cat.items():
        save_json(out_dir / "by_category" / cat_slug / "products.json", items)

    print("DONE")
    print(f"Категории: {len(categories)}")
    print(f"Товары: {len(products)}")
    print(f"Вывод: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
