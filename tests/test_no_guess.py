"""'Don't guess when data is missing' — values without a reliable source must be null."""
from odwolania2json.extract.patterns import (
    extract_amount_near_labels,
    extract_block_after_label,
    extract_date_near_labels,
    extract_header_place_date,
)
from odwolania2json.pipeline import process_text

from samples import ODWOLANIE, PRZELEW


def test_header_requires_whole_line():
    text = "Prezes KIO\nOdwołujący:\nFirma\nZamawiający w dniu 20 marca 2026 roku unieważnił postępowanie."
    assert extract_header_place_date(text) == (None, None, None)
    place, date, _ = extract_header_place_date("Kraków, dnia 3 lipca 2026 r.\nODWOŁANIE")
    assert (place, date) == ("Kraków", "2026-07-03")


def test_no_fallback_to_any_date():
    text = "Wydrukowano: 07-07-2026\nKwota 50,00 PLN"
    assert extract_date_near_labels(text, ["data operacji", "data wykonania"]) == (None, None)


def test_date_label_order_and_next_line():
    text = "Data zlecenia\n2026-06-29\nData wykonania\n2026-06-30"
    date, _ = extract_date_near_labels(text, ["data wykonania", "data zlecenia"])
    assert date == "2026-06-30"


def test_fee_is_not_the_transfer_amount():
    text = "Opłata/prowizja\n0,00 PLN\nWpis od odwołania: 7 500,00 zł"
    assert extract_amount_near_labels(text, ["kwota"]) == (None, None)
    amount, _ = extract_amount_near_labels("KWOTA PRZELEWU ........ 50,00 PLN", ["kwota"])
    assert amount == 50.0
    amount, _ = extract_amount_near_labels("Wartość\n100,00\nData operacji", ["wartość"])
    assert amount == 100.0


def test_title_block_stops_at_next_label():
    text = "Tytuł\nopłata skarbowa\nw przetargu ZP.1.2026\nNumer referencyjny\nCEN1"
    val, _ = extract_block_after_label(text, ["tytuł"], ["numer referencyjny", "status"])
    assert val == "opłata skarbowa w przetargu ZP.1.2026"


def test_przelew_without_date_label_gives_null():
    text = PRZELEW.replace("Data operacji\n2026-05-11\n", "")
    data, trace = process_text(text)
    assert data["przelew_bankowy"]["data_operacji"] is None
    assert data["przelew_bankowy"]["kwota"] == 17.0


def test_odwolanie_without_header_gives_null_place_and_date():
    text = ODWOLANIE.replace("Warszawa, 12.05.2026 r.\n", "")
    data, _ = process_text(text)
    assert data["OdwolanieKIO"]["miejscowosc"] is None
    assert data["OdwolanieKIO"]["data"] is None
    assert data["OdwolanieKIO"]["czynnosc_dzien"] == "2026-05-08"
