from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from dateutil import parser as date_parser

_OCR_MAP = str.maketrans(
    {
        "О": "O",
        "о": "o",
        "А": "A",
        "а": "a",
        "Е": "E",
        "е": "e",
        "Р": "P",
        "р": "p",
        "С": "C",
        "с": "c",
        "Т": "T",
        "В": "B",
        "Н": "H",
        "М": "M",
        "К": "K",
        "Х": "X",
        "|": "I",
        "¡": "i",
    }
)


def fix_ocr_text(text: str) -> str:
    if not text:
        return text
    text = text.translate(_OCR_MAP)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text


_DEFAULT_CONFUSABLES = {"O": "0", "o": "0", "Q": "0", "D": "0", "l": "1", "I": "1", "|": "1", "!": "1", "i": "1"}


@lru_cache(maxsize=4)
def load_ocr_lexicon(configs_dir: str | None = None) -> dict[str, Any]:
    from odwolania2json.config_loader import DEFAULT_CONFIGS, load_yaml

    base = Path(configs_dir) if configs_dir else DEFAULT_CONFIGS
    path = base / "ocr_lexicon.yaml"
    data = load_yaml(path) if path.exists() else {}
    words = {str(k).lower(): str(v) for k, v in (data.get("words") or {}).items()}
    conf = {str(k): str(v) for k, v in (data.get("digit_confusables") or _DEFAULT_CONFUSABLES).items()}
    return {"words": words, "digit_confusables": conf}


def repair_diacritics(text: str, words: dict[str, str]) -> str:
    """Replace whole words listed in the lexicon; keeps capitalisation of the first letter."""
    if not text or not words:
        return text
    alternation = "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True))
    pattern = re.compile(rf"(?<![\wąćęłńóśźż])({alternation})(?![\wąćęłńóśźż])", re.I)

    def _sub(m: re.Match) -> str:
        src = m.group(1)
        dst = words[src.lower()]
        if src.isupper():
            return dst.upper()
        if src[0].isupper():
            return dst[0].upper() + dst[1:]
        return dst

    return pattern.sub(_sub, text)


def _digitize_token(token: str, conf: dict[str, str], min_digit_ratio: float = 0.5) -> str:
    real = sum(ch.isdigit() for ch in token)
    alnum = sum(ch.isalnum() or ch in conf for ch in token)
    if real == 0 or alnum == 0 or real / alnum < min_digit_ratio:
        return token
    return "".join(conf.get(ch, ch) for ch in token)


def repair_digit_context(text: str, conf: dict[str, str] | None = None) -> str:
    """Fix letter/digit confusion only where digits are expected.

    Contexts: values after NIP/KRS/REGON/PESEL labels, date-like tokens and long
    account-number runs. Free text and alphanumeric case codes are left untouched.
    """
    if not text:
        return text
    conf = conf or _DEFAULT_CONFUSABLES
    cls = "0-9" + "".join(re.escape(c) for c in conf)

    def _id_value(m: re.Match) -> str:
        tokens = re.split(r"([\s\-]+)", m.group(2))
        return m.group(1) + "".join(_digitize_token(t, conf) if t.strip(" -") else t for t in tokens)

    text = re.sub(
        rf"(?i)(\b(?:NIP|KRS|REGON|PESEL)\b\s*[:\-]?\s*)([{cls}][{cls}\s\-]{{5,18}}[{cls}])",
        _id_value,
        text,
    )

    def _date(m: re.Match) -> str:
        tok = m.group(0)
        if sum(ch.isdigit() for ch in tok) < 5:
            return tok
        return "".join(conf.get(ch, ch) for ch in tok)

    text = re.sub(rf"(?<![\w])[{cls}]{{1,2}}[.\-/][{cls}]{{1,2}}[.\-/][{cls}]{{4}}(?![\w])", _date, text)

    def _account(m: re.Match) -> str:
        tok = m.group(0)
        if sum(ch.isdigit() for ch in tok) < 22:
            return tok
        prefix = "PL" if tok.upper().startswith("PL") else ""
        body = tok[len(prefix):]
        return prefix + "".join(conf.get(ch, ch) for ch in body)

    text = re.sub(rf"(?<![\w])(?:PL\s?)?[{cls}]{{2}}(?:\s?[{cls}]{{4}}){{6}}(?![\w])", _account, text)
    return text


def clean_ocr_page(text: str, configs_dir: str | None = None) -> str:
    """Full CPU-only cleanup applied to every page: char map, lexicon, digit context."""
    if not text:
        return text
    lex = load_ocr_lexicon(configs_dir)
    text = fix_ocr_text(text)
    text = repair_diacritics(text, lex["words"])
    text = repair_digit_context(text, lex["digit_confusables"])
    return text


def nip_checksum_ok(nip: str | None) -> bool | None:
    d = only_digits(nip)
    if not d or len(d) != 10:
        return None
    weights = (6, 5, 7, 2, 3, 4, 5, 6, 7)
    s = sum(int(a) * w for a, w in zip(d[:9], weights)) % 11
    return s != 10 and s == int(d[9])


def regon_checksum_ok(regon: str | None) -> bool | None:
    d = only_digits(regon)
    if not d or len(d) not in (9, 14):
        return None
    if len(d) == 9:
        weights = (8, 9, 2, 3, 4, 5, 6, 7)
    else:
        weights = (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8)
    s = sum(int(a) * w for a, w in zip(d[:-1], weights)) % 11
    return (0 if s == 10 else s) == int(d[-1])


def iban_pl_checksum_ok(account: str | None) -> bool | None:
    d = only_digits(account)
    if not d or len(d) != 26:
        return None
    rearranged = d[2:] + "2521" + d[:2]
    return int(rearranged) % 97 == 1


def pesel_checksum_ok(pesel: Any) -> bool | None:
    d = only_digits(str(pesel)) if pesel is not None else None
    if not d or len(d) != 11:
        return None
    weights = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    s = sum(int(a) * w for a, w in zip(d[:10], weights))
    return (10 - s % 10) % 10 == int(d[10])


CHECKSUMS = {
    "nip": nip_checksum_ok,
    "regon": regon_checksum_ok,
    "pesel": pesel_checksum_ok,
    "z_rachunku": iban_pl_checksum_ok,
    "na_rachunek": iban_pl_checksum_ok,
}


def only_digits(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits or None


def normalize_nip(value: str | None) -> str | None:
    d = only_digits(value)
    if not d:
        return None
    if len(d) == 10:
        return d
    # OCR often inserts extra digit — take last/first 10 if plausible
    if len(d) > 10:
        return d[:10]
    return d


def normalize_regon(value: str | None) -> str | None:
    d = only_digits(value)
    if not d:
        return None
    if len(d) in (9, 14):
        return d
    if len(d) > 14:
        return d[:14]
    if len(d) > 9:
        return d[:9]
    return d


def normalize_krs(value: str | None) -> str | None:
    d = only_digits(value)
    if not d:
        return None
    if len(d) < 10:
        d = d.zfill(10)
    return d[:10]


def normalize_pesel(value: str | None) -> int | None:
    d = only_digits(value)
    if not d or len(d) != 11:
        return None
    try:
        return int(d)
    except ValueError:
        return None


def normalize_account(value: str | None) -> str | None:
    if value is None:
        return None
    d = only_digits(value)
    if not d:
        return None
    # PL IBAN often 28 digits with country code stripped → 26
    if len(d) >= 26:
        return d[-26:]
    return d


def normalize_amount(value: str | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = fix_ocr_text(str(value))
    s = s.replace("PLN", "").replace("zł", "").replace("zl", "")
    s = s.strip().replace(" ", "")
    # 12.345,67 or 12345,67 or 12345.67
    if re.search(r",\d{1,2}$", s) and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


_PL_MONTHS = {
    "stycznia": 1,
    "lutego": 2,
    "marca": 3,
    "kwietnia": 4,
    "maja": 5,
    "czerwca": 6,
    "lipca": 7,
    "sierpnia": 8,
    "września": 9,
    "pazdziernika": 10,
    "października": 10,
    "listopada": 11,
    "grudnia": 12,
}


def normalize_date(value: str | None) -> str | None:
    if value is None:
        return None
    s = repair_digit_context(fix_ocr_text(str(value)).strip())
    if not s:
        return None
    # Already ISO
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return s
    # DD.MM.YYYY / DD-MM-YYYY / DD/MM/YYYY
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return None
    # YYYY.MM.DD
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return None
    # Polish: 20 lipca 2026 / 20 lipca 2026 roku
    m = re.search(
        r"(\d{1,2})\s+([A-Za-ząćęłńóśźż]+)\s+(\d{4})",
        s,
        flags=re.I,
    )
    if m:
        month = _PL_MONTHS.get(m.group(2).lower())
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(1))).strftime("%Y-%m-%d")
            except ValueError:
                return None
    try:
        dt = date_parser.parse(s, dayfirst=True, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError, TypeError):
        return None


def normalize_bzp(value: str | None) -> str | None:
    if not value:
        return None
    s = fix_ocr_text(value).upper()
    s = re.sub(r"\s+", "", s)
    # 2026/BZP 00999508 → 2026/BZP00999508
    m = re.search(r"(\d{4})/BZP0*(\d+)(?:/(\d+))?", s)
    if m:
        base = f"{m.group(1)}/BZP{m.group(2).zfill(8)}"
        if m.group(3):
            base += f"/{m.group(3).zfill(2)}"
        return base
    m = re.search(r"(\d{4})BZP0*(\d+)(?:/(\d+))?", s)
    if m:
        base = f"{m.group(1)}/BZP{m.group(2).zfill(8)}"
        if m.group(3):
            base += f"/{m.group(3).zfill(2)}"
        return base
    return s if "BZP" in s else None


def normalize_ted(value: str | None) -> str | None:
    if not value:
        return None
    s = fix_ocr_text(value).upper()
    s = re.sub(r"\s+", " ", s).strip()
    # NNNNNN-YYYY
    m = re.search(r"(\d{5,7})-(\d{4})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    # YYYY/S ###-NNNNNN or YYYY/S NNN-NNNNNN
    m = re.search(r"(\d{4})/S\s*\d+-(\d{5,7})", s)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    m = re.search(r"OJS\D*(\d+)\D+(\d{5,7})", s)
    if m:
        # weak fallback — keep digits-year if year present nearby
        return None
    return None


def normalize_transaction_id(value: str | None) -> str | None:
    if not value:
        return None
    s = fix_ocr_text(value).strip()
    s = re.sub(r"\s+", "", s)
    # Prefer CEN... style
    m = re.search(r"(CEN\d{10,})", s, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"([A-Z]{2,}\d{8,})", s, re.I)
    if m:
        return m.group(1).upper()
    s = s.strip(".…:-_ ")
    return s if re.search(r"\d{4,}", s) else None


def clean_name(value: str | None) -> str | None:
    if not value:
        return None
    s = fix_ocr_text(value).strip(" \t,;:-")
    s = re.sub(r"\s+", " ", s)
    return s or None


def apply_normalizer(name: str | None, value: Any) -> Any:
    if name is None or value is None:
        return value
    fn = {
        "nip": normalize_nip,
        "regon": normalize_regon,
        "krs": normalize_krs,
        "pesel": normalize_pesel,
        "account": normalize_account,
        "amount": normalize_amount,
        "date": normalize_date,
        "bzp": normalize_bzp,
        "ted": normalize_ted,
        "transaction_id": normalize_transaction_id,
        "name": clean_name,
    }.get(name)
    return fn(value) if fn else value
