from __future__ import annotations

import re
import unicodedata
from datetime import datetime
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
    s = fix_ocr_text(str(value)).strip()
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
    return s or None


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
