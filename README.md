# DocuBeauty — kategorie i pliki z `C:\produkty`

## Co robi aplikacja
- Strona główna (`/`) pokazuje kategorie (ZIP-y i foldery) z `C:\produkty`.
- Przy każdej kategorii jest przycisk **Zobacz** → strona z plikami (`/category/<slug>`).
- Dla ZIP-ów aplikacja pobiera listę plików z archiwum.
- Dla folderów aplikacja pobiera listę plików (rekurencyjnie).
- Po kliknięciu **Otwórz / pobierz** plik jest serwowany do przeglądarki.
  - ZIP: wskazany plik jest wypakowywany do `static/cache/<cat_slug>/<item_id>/` i następnie udostępniany.

## Uruchomienie
```bash
pip install -r requirements.txt
python app.py
```

Otwórz: http://127.0.0.1:5050/

Jeżeli Twoja lokalizacja katalogu jest inna niż `C:\produkty`, zmień `CATALOG_ROOT` w `app.py`.

## Podglądy i znak wodny
- Jeżeli w projekcie istnieją gotowe podglądy PNG (np. wygenerowane wcześniej) w `static/cards/...`, aplikacja będzie ich używać.
- Na wszystkie karty kategorii i plików nakładany jest minimalistyczny watermark `docubeauty`.
- Statyczne serwowanie `/static/...` jest wyłączone; obrazy są podawane przez trasy `/card/...` i `/itemcard/...`.

## Update
- Category card now uses preview of the first file inside the category.
- Watermark now applies soft mosaic+blur censorship plus diagonal docubeauty.
