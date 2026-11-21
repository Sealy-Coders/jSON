from odwolania2json.build_json import build_canonical
from odwolania2json.validate import validate_document


def test_build_and_validate_templates():
    for dtype in ("odwolanie", "pelnomocnictwo", "przelew"):
        data = build_canonical(dtype, {})
        res = validate_document(dtype, data)
        assert res["ok"], res["errors"]


def test_empty_unknown_valid():
    assert validate_document("unknown", {})["ok"]
