# Flask Shop Template (beż / bordo / biel)

Szablon sklepu na Flasku (lista produktów, wyszukiwarka, kategorie, sortowanie, koszyk w sesji) z dopracowaną wersją mobilną
(menu „hamburger” jak na referencji) i stroną szczegółów produktu.

## Uruchomienie (lokalnie)
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

Otwórz: http://127.0.0.1:5050/shop

## Dane produktów (integracja z parserem 1cart)

Aplikacja automatycznie wczyta katalog z:
- `export_all/products.json` (jeżeli plik istnieje) – to jest wynik działania parsera `scrape_1cart.py`,
- w przeciwnym razie użyje wersji demonstracyjnej z `data/products.json`.

Zdjęcia pobrane przez parser są serwowane z katalogu:
`export_all/images/` pod adresem:
`/media/<ścieżka-do-pliku>`

Przykład:
`/media/dokumenty-zabiegowe/nazwa-pliku.jpg`

## Render: trwałe przechowywanie (data + uploads)

Na Render system plików usługi jest efemeryczny (po deploy/restart pliki zapisane w repo/na dysku usługi mogą zniknąć).
Jeżeli chcesz zachować edycje z panelu `/edit` oraz wgrane zdjęcia, musisz użyć **Persistent Disk**.

### 1) Dodaj dysk
W Render Dashboard → Twój Web Service → **Disks** → **Add Disk**:
- **Mount Path:** `/var/data`
- rozmiar według potrzeb

### 2) Ustaw zmienne środowiskowe (Key / Value)
W Render Dashboard → Twój Web Service → **Environment** dodaj:
- `PERSIST_ROOT` = `/var/data`

To automatycznie ustawi:
- `DATA_DIR` → `/var/data/data`
- `UPLOADS_DIR` → `/var/data/uploads`

Alternatywnie możesz ustawić je jawnie:
- `DATA_DIR` = `/var/data/data`
- `UPLOADS_DIR` = `/var/data/uploads`

### 3) Start command
Zalecane (Render Web Service):
```bash
gunicorn app:app
```

## Struktura
- `app.py` – aplikacja Flask
- `templates/` – szablony HTML (lista, produkt, koszyk)
- `static/` – CSS/JS + logo + `/static/uploads` (w prod może być mapowane na dysk)
- `data/` – domyślne pliki JSON (w prod zalecany mount na dysku)
- `export_all/` – eksport z parsera (produkty + zdjęcia)
