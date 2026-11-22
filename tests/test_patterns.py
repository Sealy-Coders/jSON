from odwolania2json.extract import patterns as P
from odwolania2json.extract.engine import method_czynnosc_date


def test_amount_with_currency_before_number():
    assert P.extract_amount_near_labels("Kwota operacji\nPLN 200.00\n", ["kwota operacji"])[0] == 200.0
    text = "KWOTA PRZELEWU ........................ PLN 34.00\nOPŁATA ........ 0,00 PLN"
    assert P.extract_amount_near_labels(text, ["kwota przelewu"])[0] == 34.0


def test_email_with_polish_letters_is_folded():
    assert P.extract_email("e-mail: zamówienia@kjp-legal.example")[0] == "zamowienia@kjp-legal.example"


def test_czynnosc_date_from_act_sentence_not_side_mention():
    text = (
        "wnoszę odwołanie wobec czynności Zamawiającego, polegających na:\n"
        "1) zaniechaniu wezwania wykonawcy do wyjaśnień, mimo że Zamawiający w dniu 18 września 2026 r. "
        "wzywał tego wykonawcę do wyjaśnień ceny.\n"
        "Zamawiający w dniu 9 października 2026 roku ogłosił wybór oferty najkorzystniejszej.\n"
        "Zaskarżonym czynnościom zarzucam naruszenie:\nZarzut nr 1 – naruszenie art. 239 Pzp."
    )
    assert method_czynnosc_date({}, {"text": text})[0] == "2026-10-09"
