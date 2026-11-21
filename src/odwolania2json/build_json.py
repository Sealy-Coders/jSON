from __future__ import annotations

from copy import deepcopy
from typing import Any


def empty_odwolanie() -> dict[str, Any]:
    return {
        "OdwolanieKIO": {
            "data": None,
            "czynnosc_dzien": None,
            "czynnosc_powod_id": None,
            "czynnosc_opis": None,
            "miejscowosc": None,
        },
        "Odwolujacy": [
            {
                "krs": None,
                "nazwa": None,
                "nip": None,
                "regon": None,
                "przez-pelnomocnika": 0,
                "pelnomocnik": None,
            }
        ],
        "Zamawiajacy": [
            {
                "krs": None,
                "nazwa": None,
                "nip": None,
                "regon": None,
                "prowadzacy_postepowanie": None,
            }
        ],
        "ZamowieniePubliczne": {
            "numer_bzp": None,
            "numer_postepowania": None,
            "numer_ted": None,
            "tytul": None,
        },
    }


def empty_pelnomocnictwo() -> dict[str, Any]:
    return {
        "mocodawca": [
            {
                "data": {
                    "imie_nazwisko": None,
                    "krs": None,
                    "nazwa": None,
                    "nip": None,
                    "typ": "osoba_prawna",
                },
                "podpisujacy": [{"imie_nazwisko": None}],
            }
        ],
        "pelnomocnicy": [{"imie_nazwisko": None, "pesel": None}],
    }


def empty_przelew() -> dict[str, Any]:
    return {
        "przelew_bankowy": {
            "data_operacji": None,
            "kwota": None,
            "na_rachunek": None,
            "numer_transakcji": None,
            "tytul": None,
            "z_rachunku": None,
        }
    }


TEMPLATES = {
    "odwolanie": empty_odwolanie,
    "pelnomocnictwo": empty_pelnomocnictwo,
    "przelew": empty_przelew,
}


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def build_canonical(doc_type: str, extracted: dict[str, Any]) -> dict[str, Any]:
    if doc_type not in TEMPLATES:
        return {}
    base = TEMPLATES[doc_type]()
    # For list-valued top fields, prefer extracted wholesale
    if doc_type == "odwolanie":
        out = deep_merge(base, {k: v for k, v in extracted.items() if k == "OdwolanieKIO"})
        if "Odwolujacy" in extracted and extracted["Odwolujacy"]:
            out["Odwolujacy"] = extracted["Odwolujacy"]
        if "Zamawiajacy" in extracted and extracted["Zamawiajacy"]:
            out["Zamawiajacy"] = extracted["Zamawiajacy"]
        if "ZamowieniePubliczne" in extracted:
            out["ZamowieniePubliczne"] = deep_merge(
                base["ZamowieniePubliczne"], extracted["ZamowieniePubliczne"]
            )
        # Ensure pelnomocnik shape
        for od in out.get("Odwolujacy", []):
            if od.get("przez-pelnomocnika") == 1 and not od.get("pelnomocnik"):
                od["pelnomocnik"] = {"imie_nazwisko": None, "nazwa": None, "mail": None}
            if od.get("przez-pelnomocnika") == 0:
                od["pelnomocnik"] = None
        return out
    if doc_type == "pelnomocnictwo":
        out = deepcopy(base)
        if extracted.get("mocodawca"):
            out["mocodawca"] = extracted["mocodawca"]
        if extracted.get("pelnomocnicy"):
            out["pelnomocnicy"] = extracted["pelnomocnicy"]
        return out
    if doc_type == "przelew":
        out = deepcopy(base)
        pb = extracted.get("przelew_bankowy") or extracted
        out["przelew_bankowy"] = deep_merge(base["przelew_bankowy"], pb)
        return out
    return deep_merge(base, extracted)
