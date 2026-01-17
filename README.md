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
