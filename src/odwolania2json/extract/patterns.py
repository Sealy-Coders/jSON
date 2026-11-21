from __future__ import annotations

import regex as re

from odwolania2json.normalize import (
    clean_name,
    normalize_account,
    normalize_amount,
    normalize_bzp,
    normalize_date,
    normalize_krs,
    normalize_nip,
    normalize_regon,
    normalize_ted,
)

RE_NIP = re.compile(
    r"(?i)(?:NIP\s*[:\-]?\s*)((?:\d[\s\-]*){10})"
)
RE_REGON = re.compile(
    r"(?i)(?:REGON\s*[:\-]?\s*)((?:\d[\s\-]*){9,14})"
)
RE_KRS = re.compile(
    r"(?i)(?:KRS\s*[:\-]?\s*)((?:\d[\s\-]*){6,10})"
)
RE_EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
RE_DATE = re.compile(r"\b(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})\b")
RE_BZP = re.compile(
    r"(?i)(?:nr\s*)?(?:ogłoszenia\s*)?(?:w\s*)?BZP\s*[:\-]?\s*"
    r"(\d{4}\s*/\s*BZP\s*\d+(?:\s*/\s*\d+)?|\d{4}/BZP\d+(?:/\d+)?)"
)
RE_BZP_ALT = re.compile(r"(?i)(\d{4}\s*/\s*BZP\s*\d+(?:\s*/\s*\d+)?)")
RE_TED = re.compile(
    r"(?i)(?:TED|OJ\s*S|OJS)?\s*[:\-]?\s*"
    r"((?:\d{5,7}-\d{4})|(?:\d{4}/S\s*\d+-\d{5,7}))"
)
RE_ACCOUNT = re.compile(r"(?:\d[\s]?){24,28}")
RE_AMOUNT = re.compile(
    r"(?i)(?:kwota\s*[:\-]?\s*)?((?:\d{1,3}(?:[ .]\d{3})*|\d+)(?:[,.]\d{2})?)\s*(?:PLN|zł|zl)?"
)
RE_POSTEPOWANIE = re.compile(
    r"(?i)(?:numer(?:em)?\s+(?:referencyjny|postępowania|sprawy)|"
    r"nr\s+(?:ref\.?|postępowania|sprawy)|znak\s+sprawy)\s*[:\-]?\s*"
    r"([A-Z0-9./\-_]{4,40})"
)
RE_POSTEPOWANIE_ALT = re.compile(
    r"\b([A-Z]{1,6}[./][A-Z0-9./\-_]{3,30}\d)\b"
)
RE_HEADER_PLACE_DATE = re.compile(
    r"(?im)^\s*([A-ZĄĆĘŁŃÓŚŹŻ][A-Za-ząćęłńóśźż\- ]{1,40}),?\s+"
    r"(?:dnia\s+)?(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}|\d{1,2}\s+[A-Za-ząćęłńóśźż]+\s+\d{4})"
)
RE_HEADER_PLACE_DATE2 = re.compile(
    r"(?i)\b([A-ZĄĆĘŁŃÓŚŹŻ][A-Za-ząćęłńóśźż\- ]{1,40}),?\s+"
    r"(?:dnia\s+)?(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}|\d{1,2}\s+[A-Za-ząćęłńóśźż]+\s+\d{4})"
)
RE_PL_DATE = re.compile(
    r"\b(\d{1,2}\s+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|pazdziernika|listopada|grudnia)\s+\d{4})\b",
    re.I,
)
RE_POST_REF = re.compile(
    r"(?i)(?:nr\s+)?(?:referencyjny\s+sprawy|numer\s+postępowania|nr\s+postępowania|"
    r"znak\s+sprawy|numer\s+sprawy)\s*[:\-]?\s*([A-Z0-9][A-Z0-9./\-_]{3,40})"
)
RE_KWOTA_PLN = re.compile(
    r"(?i)(?:kwocie|kwota)\s*[:\-]?\s*((?:\d{1,3}(?:[ .]\d{3})*|\d+)(?:[,.]\d{2})?)\s*(?:PLN|zł)?"
)
RE_Z_RACH = re.compile(
    r"(?i)z\s+rachunku\s*(?:nr\s*)?[:\-]?\s*(?:PL)?\s*((?:\d[\s]?){24,28})"
)
RE_NA_RACH = re.compile(
    r"(?i)(?:na\s+rachunek|rachunek\s+beneficjenta|rachunek\s+odbiorcy)\s*(?:nr\s*)?[:\-]?\s*(?:PL)?\s*((?:\d[\s]?){24,28})"
)
RE_ACCOUNT_LINE = re.compile(r"(?i)(?:PL)?\s*((?:\d[\s]?){24,28})")


def find_first(pattern: re.Pattern, text: str, group: int = 1) -> tuple[str | None, str | None]:
    m = pattern.search(text)
    if not m:
        return None, None
    return m.group(group), m.group(0)


def extract_nip(text: str) -> tuple[str | None, str | None]:
    val, span = find_first(RE_NIP, text)
    return normalize_nip(val), span


def extract_regon(text: str) -> tuple[str | None, str | None]:
    val, span = find_first(RE_REGON, text)
    return normalize_regon(val), span


def extract_krs(text: str) -> tuple[str | None, str | None]:
    val, span = find_first(RE_KRS, text)
    return normalize_krs(val), span


def extract_email(text: str) -> tuple[str | None, str | None]:
    m = RE_EMAIL.search(text)
    if not m:
        return None, None
    return m.group(0).lower(), m.group(0)


def extract_bzp(text: str) -> tuple[str | None, str | None]:
    val, span = find_first(RE_BZP, text)
    if not val:
        val, span = find_first(RE_BZP_ALT, text)
    return normalize_bzp(val), span


def extract_ted(text: str) -> tuple[str | None, str | None]:
    val, span = find_first(RE_TED, text)
    return normalize_ted(val), span


def extract_date_near_labels(text: str, labels: list[str]) -> tuple[str | None, str | None]:
    lower = text.lower()
    for lab in labels:
        idx = lower.find(lab.lower())
        if idx < 0:
            continue
        window = text[idx : idx + 160]
        m = RE_DATE.search(window) or RE_PL_DATE.search(window)
        if m:
            return normalize_date(m.group(1)), m.group(0)
    m = RE_PL_DATE.search(text) or RE_DATE.search(text)
    if m:
        return normalize_date(m.group(1)), m.group(0)
    return None, None


def extract_amount_near_labels(text: str, labels: list[str]) -> tuple[float | None, str | None]:
    m = RE_KWOTA_PLN.search(text)
    if m:
        return normalize_amount(m.group(1)), m.group(0)
    lower = text.lower()
    for lab in labels:
        idx = lower.find(lab.lower())
        if idx < 0:
            continue
        window = text[idx : idx + 120]
        m = re.search(
            r"(?i)(?:kwocie|kwota(?:\s+przelewu)?)\s*[:\-]?\s*((?:\d{1,3}(?:[ .]\d{3})*|\d+)(?:[,.]\d{2})?)",
            window,
        )
        if not m:
            # label on its own line, value on next
            m = re.search(
                r"(?i)(?:kwota(?:\s+przelewu)?)\s*[:\-]?\s*(?:\n|\r)\s*((?:\d{1,3}(?:[ .]\d{3})*|\d+)(?:[,.]\d{2})?)",
                text[idx : idx + 80],
            )
        if m:
            return normalize_amount(m.group(1)), m.group(0)
    return None, None


def extract_account_near_labels(text: str, labels: list[str]) -> tuple[str | None, str | None]:
    joined = " ".join(l.lower() for l in labels)
    if "beneficjent" in joined or "odbiorc" in joined or "na rachunek" in joined or "uznaw" in joined:
        m = RE_NA_RACH.search(text)
        if m:
            return normalize_account(m.group(1)), m.group(0)
    if "nadawc" in joined or "z rachunk" in joined or "obciąż" in joined or "płatnik" in joined:
        m = RE_Z_RACH.search(text)
        if m:
            return normalize_account(m.group(1)), m.group(0)
    lower = text.lower()
    for lab in labels:
        idx = lower.find(lab.lower())
        if idx < 0:
            continue
        window = text[idx : idx + 200]
        m = RE_ACCOUNT_LINE.search(window) or RE_ACCOUNT.search(window)
        if m:
            return normalize_account(m.group(1) if m.lastindex else m.group(0)), m.group(0)
    # Ordered fallback: first = from, second = to
    accounts = RE_ACCOUNT.findall(text)
    if "beneficjent" in joined or "odbiorc" in joined or "na rachunek" in joined:
        if len(accounts) >= 2:
            return normalize_account(accounts[1]), accounts[1]
    if accounts:
        return normalize_account(accounts[0]), accounts[0]
    return None, None


def extract_labeled_line(text: str, labels: list[str], multiline: bool = False) -> tuple[str | None, str | None]:
    lines = text.splitlines()
    lower_labels = [l.lower() for l in labels]
    for i, line in enumerate(lines):
        ll = line.lower()
        for lab in lower_labels:
            if lab in ll:
                # value after colon or rest of line
                after = line
                if ":" in line:
                    after = line.split(":", 1)[1]
                else:
                    # strip label
                    idx = ll.find(lab)
                    after = line[idx + len(lab) :]
                after = after.strip(" \t:-")
                if multiline:
                    parts = [after] if after else []
                    for j in range(i + 1, min(i + 4, len(lines))):
                        nxt = lines[j].strip()
                        if not nxt:
                            break
                        if any(x in nxt.lower() for x in ("rachunek", "kwota", "data ", "numer ")):
                            break
                        parts.append(nxt)
                    val = clean_name(" ".join(parts))
                else:
                    val = clean_name(after) if after else None
                    if not val and i + 1 < len(lines):
                        val = clean_name(lines[i + 1])
                if val:
                    return val, line
    return None, None


def extract_postepowanie(text: str) -> tuple[str | None, str | None]:
    m = RE_POST_REF.search(text)
    if m:
        val = clean_name(m.group(1).rstrip(".,;"))
        if val and "erencyjny" not in val.lower():
            return val, m.group(0)
    val, span = find_first(RE_POSTEPOWANIE, text)
    if val and "erencyjny" not in val.lower() and len(val) > 3:
        return clean_name(val), span
    candidates = RE_POSTEPOWANIE_ALT.findall(text)
    for c in candidates:
        if re.search(r"\d{4}", c) or c.count(".") >= 2 or "/" in c:
            return clean_name(c), c
    return None, None


def extract_header_place_date(text: str) -> tuple[str | None, str | None, str | None]:
    """Return miejscowosc, data_iso, source_span."""
    head = "\n".join(text.splitlines()[:30])
    m = RE_HEADER_PLACE_DATE.search(head)
    if not m:
        m = RE_HEADER_PLACE_DATE2.search(head)
    if not m:
        dm = RE_PL_DATE.search(head) or RE_DATE.search(head)
        if dm:
            return None, normalize_date(dm.group(1)), dm.group(0)
        return None, None, None
    place = clean_name(m.group(1))
    if place and place.lower() in {"dnia", "w", "ul", "ul.", "nr", "warszawa"} and "dnia" in m.group(0).lower():
        # keep real city names including Warszawa
        pass
    if place and place.lower() in {"dnia", "w", "ul", "ul.", "nr"}:
        place = None
    return place, normalize_date(m.group(2)), m.group(0)
