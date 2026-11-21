"""Demo mode: a built-in fictional case processed without PDFs and without OCR.

Lets anyone check the whole pipeline (classification → extraction → case
consistency → checksum warnings) right after installation, optionally with
simulated OCR noise (synthetic.corrupt_text) to show CPU-only robustness.
All names and numbers are fictional.
"""
from __future__ import annotations

from typing import Any

ODWOLANIE = """Warszawa, 12.05.2026 r.
Prezes Krajowej Izby Odwoławczej
ul. Postępu 17A
02-676 Warszawa
Odwołujący:
Testowa Firma Budowlana sp. z o.o.
ul. Próbna 1, 00-001 Warszawa
KRS: 0000123456, NIP: 5260250995, REGON: 012345675
reprezentowana przez: adw. Anna Przykładowa
adres do korespondencji: Kancelaria Adwokacka Anna Przykładowa, ul. Wzorcowa 2, 00-002 Warszawa
tel. 000 000 000, biuro@kancelaria.example
Zamawiający:
Gmina Przykładowo
ul. Urzędowa 3, 00-003 Przykładowo
NIP: 1234563218, REGON: 123456785
ODWOŁANIE
dotyczy: postępowania o udzielenie zamówienia pn. „Budowa drogi gminnej w Przykładowie”,
nr referencyjny: ZP.271.5.2026, ogłoszenie o zamówieniu nr 2026/BZP 00123456
Działając w imieniu wykonawcy Testowa Firma Budowlana sp. z o.o., wnoszę o:
Zamawiający w dniu 8 maja 2026 roku odrzucił ofertę Odwołującego.
Zarzut nr 1 naruszenia art. 226 ust. 1 Pzp:
"""

PELNOMOCNICTWO = """Warszawa, 10 maja 2026 r.
PEŁNOMOCNICTWO
Testowa Firma Budowlana sp. z o.o., ul. Próbna 1, 00-001 Warszawa, KRS 0000123456, NIP 5260250995,
REGON 012345675 (dalej: „Mocodawca”), reprezentowana przez osoby podpisane poniżej,
udziela pełnomocnictwa: adw. Anna Przykładowa (nr wpisu na listę: WA/Adw/1).
Pełnomocnictwo udzielone zostaje do reprezentowania Mocodawcy w postępowaniu, numer
postępowania: ZP.271.5.2026, prowadzonym przez Gmina Przykładowo.
Mocodawca:
............................................
Jan Testowy
Prezes Zarządu
Pełnomocnictwo przyjmuję:
............................................
adw. Anna Przykładowa
"""

PRZELEW = """POTWIERDZENIE WYKONANIA PRZELEWU
Bank Przykładowy S.A. · wygenerowano 13.05.2026
Zleceniodawca
Testowa Firma Budowlana sp. z o.o.
Rachunek zleceniodawcy
PL61 1090 1014 0000 0712 1981 2874
Odbiorca
Gmina Przykładowo
Rachunek odbiorcy
PL27 1140 2004 0000 3002 0135 5388
KWOTA PRZELEWU ................ 17,00 PLN
Data operacji
2026-05-11
Tytuł przelewu
opłata skarbowa od pełnomocnictwa dla Anna Przykładowa w postępowaniu
przed KIO w przetargu ZP.271.5.2026 CEN2605110000001
Numer referencyjny
CEN2605110000001
Status
ZREALIZOWANO
Opłata/prowizja
0,00 PLN
"""

DEMO_DOCS = {
    "demo_odwolanie.txt": ODWOLANIE,
    "demo_pelnomocnictwo.txt": PELNOMOCNICTWO,
    "demo_potwierdzenie_przelewu.txt": PRZELEW,
}


def run_demo(noise: float = 0.0, seed: int = 0, configs_dir: str | None = None) -> dict[str, Any]:
    """Process the built-in case; noise > 0 corrupts the texts like a poor scan would."""
    from odwolania2json.case import build_case
    from odwolania2json.pipeline import process_text
    from odwolania2json.synthetic import corrupt_text

    docs = []
    for i, (name, text) in enumerate(DEMO_DOCS.items()):
        if noise > 0:
            text = corrupt_text(text, seed=seed + i, rate=noise)
        data, trace = process_text(text, name=name, configs_dir=configs_dir)
        trace.setdefault("warnings", []).insert(
            0,
            {
                "code": "demo",
                "severity": "info",
                "message": "Tryb demonstracyjny: fikcyjny tekst wbudowany"
                + (f", symulowany szum OCR {noise:.0%}" if noise > 0 else "")
                + ".",
            },
        )
        docs.append({"filename": name, "result": data, "trace": trace, "text": text})
    case = build_case(docs, case_id="DEMO", configs_dir=configs_dir)
    case["demo"] = {"noise": noise, "seed": seed}
    return case
