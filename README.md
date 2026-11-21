# Odwołania2json (jSON)

**Od dokumentów do danych.** Lokalny, open-source pipeline, który zamienia PDF-y ze spraw odwoławczych KIO w kanoniczny JSON gotowy dla systemów UZP.

HackNation 2026 · wyzwanie Urzędu Zamówień Publicznych · działa **w 100% on-premise na CPU** (bez GPU, bez płatnych API LLM).

---

## Spis treści

1. [Po co to jest](#1-po-co-to-jest)
2. [Jak to działa (potok)](#2-jak-to-działa-potok)
3. [Co jest w repozytorium](#3-co-jest-w-repozytorium)
4. [Dlaczego takie decyzje](#4-dlaczego-takie-decyzje)
5. [Instalacja](#5-instalacja)
6. [Uruchomienie](#6-uruchomienie)
7. [Frontend (GUI)](#7-frontend-gui)
8. [Konfiguracja i rozszerzanie](#8-konfiguracja-i-rozszerzanie)
9. [Transparentność](#9-transparentność)
10. [Ewaluacja F1](#10-ewaluacja-f1)
11. [Dostosowanie do danych treningowych](#11-dostosowanie-do-danych-treningowych)
12. [Kontrakt JSON](#12-kontrakt-json)

---

## 1. Po co to jest

Sprawa odwoławcza to zwykle **wiele PDF-ów** (odwołanie, pełnomocnictwo, potwierdzenie przelewu, czasem „śmieciowe” dokumenty). Informacje biznesowe są rozproszone i zapisane różnie — dla człowieka czytelne, dla systemów nie.

Rozwiązanie realizuje przejście:

```text
wiele PDF → tekst (+ OCR gdy trzeba) → typ dokumentu → pola → JSON kanoniczny
```

Zgodność z modelem:  
[hacknation-2026 / oczekiwane-json](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/main/oczekiwane-json)

Ocena organizatora: drzewo `input/caseN/*.pdf` → `output/caseN/<ta_sama_nazwa>.json`.  
**Nazwa pliku nie jest używana do klasyfikacji** (tylko treść). Dokument spoza 3 klas → pusty `{}`.

---

## 2. Jak to działa (potok)

Każdy PDF przechodzi te same etapy:

```text
┌─────────────┐   ┌──────────────┐   ┌─────────────┐   ┌──────────────┐
│ 1. Ingest   │ → │ 2. Tekst PDF │ → │ 3. OCR?     │ → │ 4. Klasyfik. │
│  plik/batch │   │  str. 1–3    │   │  tylko skan │   │  typ / {}    │
└─────────────┘   └──────────────┘   └─────────────┘   └──────┬───────┘
                                                              │
                    unknown ──────────────────────────────────┤→ {}
                                                              │
                                                              ▼
┌──────────────┐   ┌──────────────┐   ┌─────────────┐   ┌──────────────┐
│ 8. Zapis     │ ← │ 7. Walidacja │ ← │ 6. Build    │ ← │ 5. Ekstrakcja│
│ JSON + trace │   │  JSON Schema │   │  kanoniczny │   │  YAML+norm.  │
└──────────────┘   └──────────────┘   └─────────────┘   └──────────────┘
```

| Etap | Co robi | Po co |
|------|---------|--------|
| **Ingest** | Bierze pojedynczy PDF albo całe `input/**/*.pdf` | Batch jak u organizatora + upload z GUI |
| **Tekst** | `pymupdf` czyta warstwę tekstową, priorytet **strony 1–3** | Tam są kluczowe dane; szybciej na CPU |
| **OCR** | Jeśli strona ma za mało znaków → render + Tesseract `pol` | Skany bez tekstu; nie OCR-ujemy zbędnie |
| **Klasyfikacja** | Reguły YAML (słowa kluczowe) + lekki TF‑IDF/LogReg | Rozpoznanie typu **bez nazwy pliku**; `unknown` → `{}` |
| **Ekstrakcja** | Silnik napędzany YAML: regex, sekcje, etykiety | Pola biznesowe per typ dokumentu |
| **Normalizacja** | Daty PL, NIP/KRS/REGON, rachunki, TED/BZP, kwoty, OCR | Odporność na formaty i błędy OCR |
| **Build + schema** | Szablon kanoniczny + `jsonschema` | Stabilny kształt pod systemy UZP |
| **Trace** | Osobny `*.trace.json` | Transparentność bez psucia wynikowego JSON |

Orkiestracja: [`src/odwolania2json/pipeline.py`](src/odwolania2json/pipeline.py).

---

## 3. Co jest w repozytorium

```text
jSON/
├── README.md                 ← ten dokument
├── requirements.txt          ← zależności pip
├── pyproject.toml            ← pakiet instalowalny
├── start.sh / start.bat      ← batch input → output
├── start-web.sh              ← frontend FastAPI (GUI)
├── input/                    ← PDF-y do przetworzenia (case*/)
├── output/                   ← wynikowe JSON (+ opcjonalnie *.trace.json)
├── configs/                  ← cała konfiguracja typów i pól (bez zmiany kodu)
│   ├── pipeline.yaml         ← progi OCR, max stron, ścieżka modelu
│   ├── document_types.yaml   ← rejestr typów + keywords klasyfikacji
│   ├── schemas/              ← JSON Schema wyjścia
│   └── extractors/           ← reguły pól per typ (+ EXAMPLE_nowy_typ.yaml)
├── src/odwolania2json/       ← kod pipeline’u
│   ├── cli.py                ← process-input / process-file / eval
│   ├── pipeline.py           ← orkiestracja
│   ├── pdf_text.py / ocr.py  ← tekst + selektywny OCR
│   ├── classify.py           ← reguły + sklearn
│   ├── extract/              ← silnik YAML + wzorce PL
│   ├── normalize.py          ← normalizacja encji
│   ├── build_json.py         ← kanoniczny kształt
│   ├── validate.py           ← JSON Schema
│   ├── trace.py              ← ślad ekstrakcji
│   └── evaluate.py           ← Precision / Recall / F1
├── frontend/                 ← GUI (HTML/CSS/JS)
├── app/
│   ├── api.py                ← FastAPI (upload + serwowanie UI)
│   └── streamlit_app.py      ← alternatywne GUI Streamlit
├── models/doc_classifier.joblib  ← wytrenowany lekki klasyfikator
├── scripts/
│   ├── prepare_eval_split.py ← dane/ → input/ + gold/
│   └── train_classifier.py   ← trening TF‑IDF + LogReg
└── tests/                    ← testy jednostkowe
```

### Moduły — co robi który plik

| Moduł | Rola |
|-------|------|
| `config_loader.py` | Ładuje YAML/JSON z `configs/` |
| `pdf_text.py` | Tekst ze stron 1–3, decyzja „czy OCR” |
| `ocr.py` | Preprocessing obrazu + Tesseract `pol` (gdy zainstalowany) |
| `classify.py` | Keywords + boosty strukturalne + model sklearn |
| `extract/engine.py` | Interpreter metod z YAML (header, partie, przelew, …) |
| `extract/patterns.py` | Regexy NIP/KRS/BZP/TED/rachunki/daty PL |
| `normalize.py` | ISO daty, cyfry ID, kwoty `12.345,67`, TED/BZP |
| `build_json.py` | Wypełnia szablon zgodny z `oczekiwane-json` |
| `validate.py` | Walidacja struktury |
| `evaluate.py` | F1 na spłaszczonych ścieżkach pól |
| `cli.py` | Interfejs wiersza poleceń |

---

## 4. Dlaczego takie decyzje

| Decyzja | Dlaczego |
|--------|----------|
| **Bez LLM API** | Wymaganie lokalności; na laptopie i7/16 GB stabilniej i taniej; w punktacji premiowane „lżejsze” modele |
| **Reguły YAML + lekki sklearn** | Wysoka transparentność, łatwa rozbudowa typów, szybkość CPU |
| **Tylko strony 1–3** | Organizator: kluczowe dane zwykle na początku; mniej pracy OCR/tekstu |
| **Selektywny OCR** | Pełny OCR wszystkich stron zabija czas na CPU; robimy go tylko przy ubogiej warstwie tekstu |
| **Klasyfikacja ≠ nazwa pliku** | Wymaganie UZP; w testach nazwy bywają mylące |
| **Ślad osobno (`*.trace.json`)** | Transparentność bez ryzyka, że metadanymi „zepsuje się” oceniany JSON |
| **Konfiguracja zewnętrzna** | Nowe klasy dokumentów bez przebudowy kodu (kryterium elastyczności) |

---

## 5. Instalacja

### Wymagania

- **Python 3.13+** (działa też 3.15)
- Opcjonalnie: **Tesseract** + język `pol` (tylko skany)

```bash
# macOS
brew install tesseract tesseract-lang

# Debian/Ubuntu
sudo apt install tesseract-ocr tesseract-ocr-pol
```

### Środowisko Python

```bash
cd jSON
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

---

## 6. Uruchomienie

### A) Batch jak u organizatora (najważniejsze do oceny)

1. Włóż PDF-y:

```text
input/
  case1/
    odwolanie_nr_1.pdf
    pelnomocnictwo_nr_1.pdf
    przelew_nr_1.pdf
  case2/
    ...
```

2. Uruchom:

```bash
./start.sh
# albo:
python -m odwolania2json process-input -i ./input -o ./output
```

3. Odbierz wyniki o **tych samych nazwach**:

```text
output/case1/odwolanie_nr_1.json
output/case1/pelnomocnictwo_nr_1.json
...
```

### B) Pojedynczy plik (CLI)

```bash
python -m odwolania2json process-file dokument.pdf \
  -o wynik.json \
  --trace wynik.trace.json
```

### C) Frontend (GUI) — zalecane do demo

```bash
chmod +x start-web.sh
./start-web.sh
# otwórz http://127.0.0.1:8000
```

### D) Alternatywa Streamlit

```bash
PYTHONPATH=src streamlit run app/streamlit_app.py
```

---

## 7. Frontend (GUI)

Dedykowany interfejs w [`frontend/`](frontend/) serwowany przez FastAPI [`app/api.py`](app/api.py).

**Co robi UI**

- drag & drop / wybór PDF
- wywołanie `POST /api/extract`
- podgląd **typu dokumentu**, metody klasyfikacji i pewności
- podgląd **kanonicznego JSON** + przycisk pobrania
- przełącznik **śladu ekstrakcji** (transparentność)

**Endpointy**

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| `GET` | `/` | Strona UI |
| `GET` | `/api/health` | Healthcheck |
| `POST` | `/api/extract` | Upload PDF → `{ result, trace, document_type }` |

Pliki UI: `frontend/index.html`, `styles.css`, `app.js` (bez bundlera — proste uruchomienie na hackathonie).

---

## 8. Konfiguracja i rozszerzanie

### Parametry pipeline’u — `configs/pipeline.yaml`

- `max_pages` — ile stron czytać (domyślnie 3)
- `min_chars_per_page` — próg „za mało tekstu → OCR”
- `ocr_lang` — `pol`
- `classifier_model` — ścieżka do `joblib`

### Typy dokumentów — `configs/document_types.yaml`

Rejestr typów: słowa kluczowe, ścieżka extractora, JSON Schema.  
To tu „uczymy” klasyfikator regułowy **bez ruszania Pythona**.

### Pola — `configs/extractors/*.yaml`

Opisują **jakie metody** wywołać (np. `labeled_date`, `parties_odwolujacy`, `czynnosc_powod`).  
Słownik powodów odwołania 1–12: `configs/extractors/czynnosc_powod.yaml`.

### Jak dodać nowy typ **bez zmiany kodu**

1. Skopiuj [`configs/extractors/EXAMPLE_nowy_typ.yaml`](configs/extractors/EXAMPLE_nowy_typ.yaml) → `moj_typ.yaml`.
2. Dopisz wpis w `document_types.yaml` (`keywords`, `extractor`, `output_schema`).
3. (Opcjonalnie) dodaj `configs/schemas/moj_typ.schema.json`.
4. Uruchom ponownie CLI/GUI — nowy typ jest w rejestrze.

Jeśli potrzebujesz **zupełnie nowej logiki** (nie da się złożyć z istniejących `method`), dopiero wtedy dopisz handler w `extract/engine.py` i odwołaj się do niego z YAML.

---

## 9. Transparentność

Dla każdego PDF (CLI z domyślnymi opcjami) powstaje obok wyniku plik:

```text
nazwa.json          ← oceniany wynik
nazwa.trace.json    ← diagnostyka (opcjonalnie wyłącz: --no-trace)
```

Ślad zawiera m.in.:

- klasyfikację (`label`, `method`, `confidence`, `scores`)
- per strona: czy użyto OCR, liczba znaków
- per pole: `path`, `value`, `page`, `rule_id`, `method`, `confidence`, `source_span`
- wynik walidacji schematu

W GUI ślad włączasz przyciskiem **„Pokaż ślad”**.

---

## 10. Ewaluacja F1

Skrypt porównuje predykcje z gold po **spłaszczeniu ścieżek** (`Odwolujacy.0.nip`, `przelew_bankowy.kwota`, …), z normalizacją przed porównaniem (daty, ID, kwoty, nazwy).

```bash
python -m odwolania2json process-input -i ./input -o ./output
python -m odwolania2json eval --pred ./output --gold ./gold --report ./output/f1_report.json
```

Raport: micro P/R/F1, per typ dokumentu, per pole.

### Orientacyjna jakość na zbiorze treningowym UZP

| Typ | F1 |
|-----|-----|
| odwołanie | ~0.90 |
| przelew | ~0.88 |
| pełnomocnictwo | ~0.68 |
| **micro** | **~0.85** |

---

## 11. Dostosowanie do danych treningowych

Gdy masz lokalnie [hacknation-2026](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026):

```bash
# 1) Zmapuj dane/ → input/ + gold/
python scripts/prepare_eval_split.py \
  --dane ../hacknation-2026/dane \
  --input ./input \
  --gold ./gold \
  --include-negatives

# 2) (opcjonalnie) dotrenuj klasyfikator
python scripts/train_classifier.py \
  --dane ../hacknation-2026/dane \
  --out models/doc_classifier.joblib

# 3) Przetwórz i zmierz F1
./start.sh
python -m odwolania2json eval --pred ./output --gold ./gold
```

Strojenie jakości **najpierw w YAML** (`configs/extractors/`, `document_types.yaml`), nie w kodzie — tak projekt jest oceniany pod kątem elastyczności.

---

## 12. Kontrakt JSON

### Odwołanie

`OdwolanieKIO` (data, czynność, powód 1–12, miejscowość), `Odwolujacy[]` (+ pełnomocnik), `Zamawiajacy[]`, `ZamowieniePubliczne` (BZP / nr postępowania / TED / tytuł).

### Pełnomocnictwo

`mocodawca[]` (`data` + `podpisujacy[]`), `pelnomocnicy[]`.

### Przelew

`przelew_bankowy`: data, kwota, rachunki, numer transakcji, tytuł.

### Negatyw / nieznany typ

```json
{}
```

Szczegóły pól i komentarze domenowe: katalog `oczekiwane-json` w repozytorium organizatora.

---

## Szybka ściąga komend

```bash
# instalacja
pip install -r requirements.txt && pip install -e .

# GUI
./start-web.sh                          # http://127.0.0.1:8000

# batch oceny
./start.sh

# F1
python -m odwolania2json eval --pred ./output --gold ./gold

# testy
PYTHONPATH=src python -m pytest tests/ -q
```

---

## Licencja i stack

Wyłącznie komponenty open source: **PyMuPDF**, **Tesseract**, **scikit-learn**, **FastAPI**, **Streamlit**, **jsonschema**, **OpenCV/Pillow**, …

Projekt: **Odwołania2json (jSON)** · HackNation 2026.
