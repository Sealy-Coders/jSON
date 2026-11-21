from odwolania2json.normalize import (
    normalize_account,
    normalize_amount,
    normalize_bzp,
    normalize_date,
    normalize_krs,
    normalize_nip,
    normalize_ted,
    normalize_transaction_id,
)


def test_normalize_date():
    assert normalize_date("13.10.2025") == "2025-10-13"
    assert normalize_date("2025-10-13") == "2025-10-13"
    assert normalize_date("20 lipca 2026") == "2026-07-20"
    assert normalize_date("8 lipca 2026 roku") == "2026-07-08"


def test_normalize_ids():
    assert normalize_nip("999-039-64-94") == "9990396494"
    assert normalize_krs("243") == "0000000243"
    assert normalize_account("60 1010 1010 0081 3622 3100 0000") == "60101010100081362231000000"


def test_normalize_bzp_ted_amount():
    assert normalize_bzp("2026/BZP 00999508") == "2026/BZP00999508"
    assert normalize_ted("641651-2025") == "641651-2025"
    assert normalize_ted("2025/S 188-641009") == "641009-2025"
    assert normalize_amount("10 000,50 PLN") == 10000.50
    assert normalize_transaction_id("CEN2608111315943") == "CEN2608111315943"
