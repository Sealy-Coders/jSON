from odwolania2json.classify import classify_document


def test_classify_odwolanie_keywords():
    text = "ODWOŁANIE do Krajowej Izby Odwoławczej. Wnoszę odwołanie. Zarzut pierwszy. Zamawiający."
    r = classify_document(text)
    assert r.label == "odwolanie"


def test_classify_przelew_keywords():
    text = "Potwierdzenie przelewu. Data operacji 2026-01-01. Kwota 17 PLN. Rachunek nadawcy."
    r = classify_document(text)
    assert r.label == "przelew"


def test_classify_administrative_decision_is_unknown():
    text = (
        "MINISTER SPORTU I TURYSTYKI\nDECYZJA Nr 4/PP/2011\nNa podstawie art. 104 Kodeksu postępowania "
        "administracyjnego postanawiam zatwierdzić statut.\nPouczenie:\nOd niniejszej decyzji nie służy "
        "odwołanie, jednak strona może zwrócić się z wnioskiem o ponowne rozpatrzenie sprawy."
    )
    assert classify_document(text).label == "unknown"


def test_classify_unknown():
    text = "Broszura JPK FA instrukcja wypełniania formularza podatkowego bez związku."
    r = classify_document(text)
    assert r.label == "unknown"
