from odwolania2json.normalize import (
    clean_ocr_page,
    iban_pl_checksum_ok,
    nip_checksum_ok,
    normalize_date,
    regon_checksum_ok,
    repair_diacritics,
    repair_digit_context,
)


def test_digit_confusion_after_id_labels():
    assert repair_digit_context("NIP: 526O25O995") == "NIP: 5260250995"
    assert repair_digit_context("KRS 00OO1234l6") == "KRS 0000123416"


def test_digit_confusion_in_dates_and_accounts():
    assert repair_digit_context("Data: l2.O5.2026") == "Data: 12.05.2026"
    acc = "PL61 1O90 1014 0000 0712 l981 2874"
    assert repair_digit_context(acc) == "PL61 1090 1014 0000 0712 1981 2874"


def test_case_codes_and_words_untouched():
    text = "numer postępowania: ZS.791.2026 oraz NIP Odwołującego"
    assert repair_digit_context(text) == text
    assert repair_digit_context("Opis Przedmiotu Zamówienia") == "Opis Przedmiotu Zamówienia"


def test_lexicon_restores_diacritics_keeping_case():
    words = {"odwolujacy": "odwołujący", "pelnomocnictwo": "pełnomocnictwo"}
    assert repair_diacritics("Odwolujacy oraz PELNOMOCNICTWO", words) == "Odwołujący oraz PEŁNOMOCNICTWO"
    assert repair_diacritics("Kowalski", words) == "Kowalski"


def test_clean_page_uses_yaml_lexicon():
    out = clean_ocr_page("Zamawiajacy: Gmina\nNIP: l23456321B")
    assert out.startswith("Zamawiający:")


def test_normalize_date_with_ocr_noise():
    assert normalize_date("l1.O5.2026") == "2026-05-11"
    assert normalize_date("2026-05-11") == "2026-05-11"
    assert normalize_date("8 maja 2026 roku") == "2026-05-08"


def test_checksums_are_informational():
    assert nip_checksum_ok("5260250995") is True
    assert nip_checksum_ok("5260250994") is False
    assert nip_checksum_ok("123") is None
    assert regon_checksum_ok("123456785") is True
    assert iban_pl_checksum_ok("61109010140000071219812874") is True
    assert iban_pl_checksum_ok("61109010140000071219812875") is False
