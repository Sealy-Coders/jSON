from odwolania2json.pipeline import process_text

from samples import ODWOLANIE, PELNOMOCNICTWO, PRZELEW


def test_odwolanie_from_text():
    data, trace = process_text(ODWOLANIE)
    assert trace["document_type"] == "odwolanie"
    k = data["OdwolanieKIO"]
    assert (k["miejscowosc"], k["data"]) == ("Warszawa", "2026-05-12")
    assert k["czynnosc_powod_id"] == 1
    assert data["Odwolujacy"][0]["nip"] == "5260250995"
    assert data["Odwolujacy"][0]["pelnomocnik"]["imie_nazwisko"] == "Anna Przykładowa"
    assert data["ZamowieniePubliczne"]["numer_postepowania"] == "ZP.271.5.2026"
    assert data["ZamowieniePubliczne"]["numer_bzp"] == "2026/BZP00123456"


def test_pelnomocnictwo_signer_is_not_the_attorney():
    data, trace = process_text(PELNOMOCNICTWO)
    assert trace["document_type"] == "pelnomocnictwo"
    moc = data["mocodawca"][0]
    assert moc["data"]["nazwa"] == "Testowa Firma Budowlana sp. z o.o."
    assert moc["podpisujacy"] == [{"imie_nazwisko": "Jan Testowy"}]
    assert [p["imie_nazwisko"] for p in data["pelnomocnicy"]] == ["Anna Przykładowa"]


def test_przelew_from_text():
    data, trace = process_text(PRZELEW)
    assert trace["document_type"] == "przelew"
    p = data["przelew_bankowy"]
    assert p["kwota"] == 17.0
    assert p["data_operacji"] == "2026-05-11"
    assert p["numer_transakcji"] == "CEN2605110000001"
    assert p["z_rachunku"] == "61109010140000071219812874"
    assert p["tytul"].endswith("ZP.271.5.2026 CEN2605110000001")
    assert any(c["kind"] == "z_rachunku" and c["checksum_ok"] for c in trace["checks"])


def test_trace_keeps_page_rule_and_confidence():
    _, trace = process_text(PRZELEW)
    entry = next(f for f in trace["fields"] if f["path"] == "przelew_bankowy.kwota")
    assert entry["page"] == 1
    assert entry["rule_id"] and 0 <= entry["confidence"] <= 1
    assert "17,00" in entry["source_span"]
