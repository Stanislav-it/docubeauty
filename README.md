# Flask Shop Template (beż / bordo / biel)

Szablon sklepu na Flasku (lista produktów, wyszukiwarka, kategorie, sortowanie, koszyk w sesji) z dopracowaną wersją mobilną
(menu „hamburger” jak na referencji) i stroną szczegółów produktu.

## Uruchomienie
```bash
python -m venv .venv
# Windows (PowerShell):
# .venv\Scripts\Activate.ps1
# Windows (CMD):
# .venv\Scripts\activate.bat
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Otwórz: http://127.0.0.1:5000/shop

## Dane produktów (integracja z parserem 1cart)

Aplikacja automatycznie wczyta katalog z:
- `export_all/products.json` (jeżeli plik istnieje) – to jest wynik działania parsera `scrape_1cart.py`,
- w przeciwnym razie użyje wersji demonstracyjnej z `data/products.json`.

Zdjęcia pobrane przez parser są serwowane z katalogu:
`export_all/images/` pod adresem:
`/media/<ścieżka-do-pliku>`

Przykład:
`/media/dokumenty-zabiegowe/nazwa-pliku.jpg`

## Struktura
- `app.py` – aplikacja Flask
- `templates/` – szablony HTML (lista, produkt, koszyk)
- `static/` – CSS/JS + logo
- `export_all/` – eksport z parsera (produkty + zdjęcia)

## Deploy on Render (persist DATA + UPLOADS across deploy)

Render wipes the deploy image on each deploy (ephemeral filesystem). To keep admin edits and uploaded images,
use a Persistent Disk and point the app to it.

### 1) Create a Disk
- Render Dashboard -> your service -> **Disks** -> **Add Disk**
- Mount path (recommended): `/var/data`

### 2) Set Environment Variables (key/value)
In Render -> **Environment**:
- `PERSIST_ROOT` = `/var/data` (optional helper)
- `DATA_DIR` = `/var/data/data`
- `UPLOADS_DIR` = `/var/data/uploads`
- `CUSTOM_DIGITAL_DIR` = `/var/data/digital_custom_uploads` (paid files uploaded in admin)
- `STRIPE_PUBLISHABLE_KEY` = `pk_test_...` (or live key in production)
- `STRIPE_SECRET_KEY` = `sk_test_...` (or live key in production)
- `SECRET_KEY` = long random string

After first boot, the app will create folders and (if needed) create a symlink:
`static/uploads -> /var/data/uploads` so URLs stay compatible.

### 3) Manual deploy
Manual deploys will not erase the Disk. Any files written into `DATA_DIR`, `UPLOADS_DIR` and `CUSTOM_DIGITAL_DIR`
will persist automatically.
