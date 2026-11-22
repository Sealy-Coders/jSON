# Odwołania2json — uruchomienie oceny

Z katalogu `/opt/solution`:

```bash
sudo docker compose --profile batch run --rm batch
```

- Przetwarza rekurencyjnie wszystkie pliki PDF z `/opt/solution/input` (płasko lub w podkatalogach, np. `input/case1/*.pdf`).
- Dla każdego `input/<ścieżka>/<nazwa>.pdf` zapisuje `output/<ścieżka>/<nazwa>.json` (ta sama struktura katalogów i nazwa pliku).
- Dokument spoza obsługiwanych typów → `{}`. Uszkodzony PDF nie przerywa przetwarzania.
- Bez interakcji, kończy się sam po przetworzeniu wszystkich plików.

Obraz `odwolania2json:latest` (Python 3.12 + Tesseract z językiem `pol`) jest już zbudowany na serwerze — nie jest potrzebny internet ani żadna usługa działająca w tle.

## Usługi zewnętrzne

Brak. Rozwiązanie działa w 100% lokalnie na CPU (PyMuPDF, Tesseract OCR, reguły + TF-IDF). Nie korzysta z żadnych API ani kluczy — plik `.env` nie jest potrzebny.

## Opcjonalnie: interfejs WWW

```bash
sudo docker compose up -d web    # http://127.0.0.1:8000
```
