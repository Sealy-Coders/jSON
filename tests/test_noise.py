from odwolania2json.pipeline import process_text
from odwolania2json.synthetic import corrupt_text

from samples import PRZELEW


def test_corrupt_text_is_deterministic_and_changes_text():
    a = corrupt_text(PRZELEW, seed=1, rate=0.3)
    b = corrupt_text(PRZELEW, seed=1, rate=0.3)
    assert a == b
    assert a != PRZELEW


def test_przelew_survives_moderate_noise():
    hits = 0
    for seed in range(10):
        data, trace = process_text(corrupt_text(PRZELEW, seed=seed, rate=0.1))
        p = data.get("przelew_bankowy") or {}
        hits += p.get("kwota") == 17.0 and p.get("numer_transakcji") == "CEN2605110000001"
    assert hits >= 8
