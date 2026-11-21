import copy

from odwolania2json.case import build_case, person_matches, resolve_path
from odwolania2json.pipeline import process_text

from samples import ODWOLANIE, PELNOMOCNICTWO, PRZELEW


def _docs(**overrides):
    docs = []
    for name, text in (("odwolanie.pdf", ODWOLANIE), ("pelnomocnictwo.pdf", PELNOMOCNICTWO), ("przelew.pdf", PRZELEW)):
        data, trace = process_text(text, name=name)
        docs.append({"filename": name, "result": data, "trace": trace, "text": text})
    for d in docs:
        if d["filename"] in overrides:
            overrides[d["filename"]](d)
    return docs


def test_resolve_path_with_wildcards():
    data = {"a": [{"b": 1}, {"b": None}, {"b": 3}]}
    assert resolve_path(data, "a[*].b") == [1, 3]
    assert resolve_path(data, "a[0].b") == [1]
    assert resolve_path(data, "a[5].b") == []


def test_person_matching_tolerates_declension():
    assert person_matches("Anna Przykładowa", "pełnomocnictwo dla Anny Przykładowej")
    assert not person_matches("Anna Przykładowa", "dla Jana Testowego")


def test_consistent_case_is_ok():
    report = build_case(_docs())
    assert report["status"] == "ok"
    assert report["case_id"] == "ZP-271-5-2026"
    assert report["numer_postepowania"] == "ZP.271.5.2026"
    assert all(c["status"] == "ok" for c in report["consistency"]), report["consistency"]
    assert report["unified"]["wykonawca_nip"] == {**report["unified"]["wykonawca_nip"], "status": "agree", "value": "5260250995"}


def test_conflicting_nip_is_reported_not_resolved():
    def break_nip(d):
        d["result"]["mocodawca"][0]["data"]["nip"] = "1111111111"

    report = build_case(_docs(**{"pelnomocnictwo.pdf": break_nip}))
    assert report["status"] == "conflict"
    nip_check = next(c for c in report["consistency"] if c["id"] == "wykonawca_nip")
    assert nip_check["status"] == "conflict"
    u = report["unified"]["wykonawca_nip"]
    assert u["status"] == "conflict" and u["value"] is None
    assert set(u["candidates"]) == {"5260250995", "1111111111"}


def test_missing_data_is_missing_not_conflict_and_not_filled():
    def drop_krs(d):
        d["result"]["mocodawca"][0]["data"]["krs"] = None

    docs = _docs(**{"pelnomocnictwo.pdf": drop_krs})
    before = copy.deepcopy(docs[1]["result"])
    report = build_case(docs)
    krs = next(c for c in report["consistency"] if c["id"] == "wykonawca_krs")
    assert krs["status"] == "missing"
    sug = [s for s in report["suggestions"] if s["path"] == "mocodawca[0].data.krs"]
    assert sug and sug[0]["suggested_value"] == "0000123456" and sug[0]["applied"] is False
    pel = next(d for d in report["documents"] if d["filename"] == "pelnomocnictwo.pdf")
    assert pel["result"] == before


def test_missing_document_type():
    docs = [d for d in _docs() if d["filename"] != "przelew.pdf"]
    report = build_case(docs)
    assert report["status"] == "incomplete"
    assert report["summary"]["missing_types"] == ["przelew"]
    assert next(c for c in report["consistency"] if c["id"] == "postepowanie_w_przelewie")["status"] == "missing"
