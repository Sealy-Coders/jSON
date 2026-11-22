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
RE_EMAIL = re.compile(r"[A-Z0-9ąćęłńóśźż._%+\-]+@[A-Z0-9ąćęłńóśźż.\-]+\.[A-Z]{2,}", re.I)
_PL_ASCII = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def fold_email(value: str) -> str:
    return value.translate(_PL_ASCII).lower()
RE_DATE = re.compile(r"\b(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}|\d{4}[.\-]\d{2}[.\-]\d{2})\b")
AMOUNT = r"(?:\d{1,3}(?:[ .]\d{3})+|\d+)(?:[,.]\d{2})?"
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
    r"(?i)(?:nr\s+)?(?:referencyjny\s+sprawy|(?<=nr\s)referencyjny|numer\s+referencyjny|"
    r"numer\s+postępowania|nr\s+postępowania|"
    r"znak\s+sprawy|numer\s+sprawy)\s*[:\-]?\s*([A-Z0-9][A-Z0-9./\-_]{3,40})"
)
RE_KWOTA_PLN = re.compile(
    r"(?i)\bkwo(?:ta|cie|tę)(?:\s+(?:przelewu|operacji|transakcji|zlecenia|płatności|obciążenia|uznania))?"
    rf"[\s.:…\-]*(?:(?:PLN|zł|zl)\s*)?({AMOUNT})\s*(?:PLN|zł|zl)?(?!\d)"
)
LEADER = r"[\s.:…\-]*"
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
    return fold_email(m.group(0)), m.group(0)


def extract_bzp(text: str) -> tuple[str | None, str | None]:
    val, span = find_first(RE_BZP, text)
    if not val:
        val, span = find_first(RE_BZP_ALT, text)
    return normalize_bzp(val), span


def extract_ted(text: str) -> tuple[str | None, str | None]:
    val, span = find_first(RE_TED, text)
    return normalize_ted(val), span


def _find_label(text: str, label: str, start: int = 0) -> re.Match | None:
    return re.compile(rf"(?i)(?<![\wąćęłńóśźż]){re.escape(label)}(?![\wąćęłńóśźż])").search(text, start)


def extract_date_near_labels(
    text: str, labels: list[str], fallback_any_date: bool = False, window: int = 60
) -> tuple[str | None, str | None]:
    """Date right after one of the labels (in label priority order).

    No label → None. The old "first date anywhere in the document" fallback is
    opt-in only (fallback_any_date) because it produced dates of letters /
    generation stamps instead of the operation date.
    """
    for lab in labels:
        m_lab = _find_label(text, lab)
        while m_lab:
            chunk = text[m_lab.end() : m_lab.end() + window]
            m = re.match(rf"{LEADER}(?:dnia\s+)?", chunk)
            rest = chunk[m.end() :] if m else chunk
            dm = RE_DATE.match(rest) or RE_PL_DATE.match(rest)
            if dm:
                return normalize_date(dm.group(1)), (m_lab.group(0) + chunk[: (m.end() if m else 0) + dm.end()])
            m_lab = _find_label(text, lab, m_lab.end())
    if fallback_any_date:
        m = RE_PL_DATE.search(text) or RE_DATE.search(text)
        if m:
            return normalize_date(m.group(1)), m.group(0)
    return None, None


def extract_amount_near_labels(text: str, labels: list[str]) -> tuple[float | None, str | None]:
    """Amount directly after a 'kwota…' label (same or next line).

    Fees and commissions ('opłata/prowizja 0,00 PLN') and the appeal fee ('wpis')
    are never read as the transfer amount, because only kwota-labels are accepted.
    """
    m = RE_KWOTA_PLN.search(text)
    if m:
        return normalize_amount(m.group(1)), m.group(0)
    for lab in labels:
        m_lab = _find_label(text, lab)
        if not m_lab:
            continue
        chunk = text[m_lab.end() : m_lab.end() + 80]
        am = re.match(
            rf"{LEADER}(?:(?:PLN|zł|zl)\s*)?({AMOUNT})(?:\s*(?:PLN|zł|zl)\b|[ \t]*(?:\n|$))", chunk, re.I
        )
        if am:
            return normalize_amount(am.group(1)), m_lab.group(0) + chunk[: am.end()]
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
    # Positional fallback only for the standard two-account layout (payer first,
    # recipient second). With one or 3+ accounts the role is ambiguous → None.
    accounts = RE_ACCOUNT.findall(text)
    if len(accounts) == 2:
        is_to = "beneficjent" in joined or "odbiorc" in joined or "na rachunek" in joined
        acc = accounts[1] if is_to else accounts[0]
        return normalize_account(acc), acc
    return None, None


def extract_block_after_label(
    text: str,
    labels: list[str],
    stop_labels: list[str],
    max_lines: int = 4,
) -> tuple[str | None, str | None]:
    """Value of a label that starts a line; continues over following lines until a stop label.

    Handles 'Tytułem: …', 'Opis\\n…\\n…', 'Tytuł przelewu: „…”.'
    """
    lines = text.splitlines()
    stops = [s.lower() for s in stop_labels]

    def _is_stop(line: str) -> bool:
        ll = line.strip().lower()
        return any(ll.startswith(s) for s in stops) or bool(re.match(r"^[A-ZĄĆĘŁŃÓŚŹŻ ]{6,}$", line.strip()))

    for lab in labels:
        rx = re.compile(rf"(?i)^\s*{re.escape(lab)}(?![\wąćęłńóśźż])\s*[:\-]?\s*(.*)$")
        for i, line in enumerate(lines):
            m = rx.match(line)
            if not m:
                continue
            parts = [m.group(1).strip()] if m.group(1).strip() else []
            for j in range(i + 1, min(i + 1 + max_lines, len(lines))):
                nxt = lines[j].strip()
                if not nxt or _is_stop(nxt):
                    break
                parts.append(nxt)
            val = " ".join(parts)
            inline_stop = re.search(
                r"(?i)\s(?:" + "|".join(re.escape(s) for s in stops) + r")\.?\s*:", val
            )
            if inline_stop:
                val = val[: inline_stop.start()]
            val = clean_name(val.strip(" „”\"'"))
            if val:
                val = val.rstrip(" .„”\"'") or None
            if val:
                return val, line.strip()
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


_DATE_ALT = (
    r"\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}|\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}\s+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|"
    r"października|pazdziernika|listopada|grudnia)\s+\d{4}"
)
_CITY_WORD = r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)?"
RE_HEADER_LINE = re.compile(
    rf"^\s*(?P<place>{_CITY_WORD}(?:\s+(?:nad|n\.|pod|k\.)?\s*{_CITY_WORD}){{0,2}})\s*,?\s+"
    rf"(?:(?i:dnia|dn\.)\s*)?(?P<date>(?i:{_DATE_ALT}))\s*(?:r\.?|roku)?\s*$"
)
RE_DATE_ONLY_LINE = re.compile(rf"^\s*(?:(?i:dnia|dn\.)\s*)?(?P<date>(?i:{_DATE_ALT}))\s*(?:r\.?|roku)?\s*$")
_NOT_PLACES = {
    "zamawiający", "odwołujący", "data", "dnia", "strona", "ul", "nr", "dotyczy", "sygn",
    "pełnomocnictwo", "pełnomocnik", "mocodawca", "w", "z", "termin",
}


def extract_header_place_date(text: str, max_lines: int = 25) -> tuple[str | None, str | None, str | None]:
    """Return miejscowosc, data_iso, source_span.

    Only a whole header line 'Miejscowość, [dnia] DATA [r.]' (or a bare date line)
    counts. Sentences like 'Zamawiający w dniu 20 marca 2026 …' are not headers —
    when no such line exists both values are None (no guessing).
    """
    all_lines = text.splitlines()
    lines = all_lines[:max_lines]
    # The header line may also sit right above the 'ODWOŁANIE' title, after the parties block.
    title = next((i for i, ln in enumerate(all_lines[:120]) if re.match(r"^\s*ODWOŁANIE\s*$", ln)), None)
    header_zone = all_lines[: max(max_lines, (title or 0) + 1)]
    for line in header_zone:
        m = RE_HEADER_LINE.match(line)
        if m and m.group("place").split()[0].lower() not in _NOT_PLACES:
            return clean_name(m.group("place")), normalize_date(m.group("date")), line.strip()
    for line in lines:
        m = RE_DATE_ONLY_LINE.match(line)
        if m:
            return None, normalize_date(m.group("date")), line.strip()
    return None, None, None
