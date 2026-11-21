from __future__ import annotations

from typing import Any

import regex as re

from odwolania2json.config_loader import load_czynnosc_powod, load_extractor_config
from odwolania2json.extract import patterns as P
from odwolania2json.extract.sections import build_sections
from odwolania2json.normalize import (
    clean_name,
    normalize_date,
    normalize_krs,
    normalize_nip,
    normalize_pesel,
    normalize_transaction_id,
)
from odwolania2json.pdf_text import DocumentText, page_for_span
from odwolania2json.trace import TraceCollector


def extract_fields(
    doc_type: str,
    doc_text: DocumentText,
    configs_dir: str | None = None,
    trace: TraceCollector | None = None,
) -> dict[str, Any]:
    cfg = load_extractor_config(doc_type, configs_dir)
    text = doc_text.plain_text
    sections = build_sections(text, cfg.get("sections"))
    trace = trace or TraceCollector()
    ctx = {
        "text": text,
        "sections": sections,
        "doc_text": doc_text,
        "configs_dir": configs_dir,
        "trace": trace,
        "czynnosc_id": None,
        "czynnosc_opis": None,
    }

    result: dict[str, Any] = {}
    for field in cfg.get("fields", []):
        method = field["method"]
        path = field["path"]
        handler = METHOD_HANDLERS.get(method)
        if not handler:
            continue
        value, meta = handler(field, ctx)
        _assign_path(result, path, value)
        if meta:
            trace.add(
                path=path,
                value=value,
                page=meta.get("page") or page_for_span(doc_text, meta.get("span")),
                rule_id=meta.get("rule_id", method),
                method=method,
                confidence=meta.get("confidence", 0.7),
                source_span=meta.get("span"),
            )
    return result


def _assign_path(obj: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = obj
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


def _meta(span: str | None = None, rule_id: str = "", confidence: float = 0.7, page: int | None = None) -> dict[str, Any]:
    return {"span": span, "rule_id": rule_id, "confidence": confidence, "page": page}


# ---- party helpers ----

_COMPANY_HINT = re.compile(
    r"(?i)\b(sp\.?\s*z\s*o\.?\s*o\.?|spółka|s\.?\s*a\.?|s\.?\s*j\.?|sp\.\s*k\.?|"
    r"sp\.\s*p\.?|p\.?\s*p\.?h\.?u\.?|firma|przedsiębiorstw|szpital|urząd|"
    r"gmina|miasto|powiat|zarząd|centrum|zakład|uczelnia|uniwersytet|"
    r"filharmonia|komenda|muzeum|teatr)\b"
)
_PERSON_NAME = re.compile(
    r"\b([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+){1,3})\b"
)


def _company_name_from_block(block: str) -> str | None:
    lines = [ln.strip(" \t,;:-") for ln in block.splitlines() if ln.strip()]
    for ln in lines[:8]:
        if re.search(r"(?i)^(odwołując|zamawiając|pełnomocnik|adres|ul\.|NIP|REGON|KRS|tel|e-?mail)", ln):
            continue
        if len(ln) < 3:
            continue
        # strip leading labels
        ln2 = re.sub(r"(?i)^(odwołujący|zamawiający)\s*[:\-]?\s*", "", ln).strip()
        if _COMPANY_HINT.search(ln2) or len(ln2) > 12:
            return clean_name(ln2)
    # fallback first substantial line
    for ln in lines[:5]:
        if len(ln) > 5 and not re.search(r"(?i)^(NIP|REGON|KRS|ul\.|adres)", ln):
            return clean_name(ln)
    return None


def _person_from_block(block: str) -> str | None:
    # Prefer labeled
    m = re.search(
        r"(?i)(?:pełnomocnik(?:a|iem)?|reprezentowan[yaei]|radc[ay]\s+prawn[yaei]|adwokat)\s*[:\-]?\s*"
        r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+){1,2})",
        block,
    )
    if m:
        return clean_name(m.group(1))
    for m in _PERSON_NAME.finditer(block):
        name = m.group(1)
        if _COMPANY_HINT.search(name):
            continue
        if name.lower() in {"krajowa izba", "izba odwoławcza"}:
            continue
        return clean_name(name)
    return None


def _kancelaria_from_block(block: str) -> str | None:
    m = re.search(
        r"(?i)((?:Kancelaria|Kancelarii)[^,\n]{5,80})",
        block,
    )
    if m:
        return clean_name(m.group(1))
    return None


def _parse_party_block(block: str, role: str) -> dict[str, Any]:
    nip, _ = P.extract_nip(block)
    regon, _ = P.extract_regon(block)
    krs, _ = P.extract_krs(block)
    nazwa = _company_name_from_block(block)
    return {
        "krs": krs,
        "nazwa": nazwa,
        "nip": nip,
        "regon": regon,
        "_block": block,
        "_role": role,
    }


def _split_party_blocks(section: str, role_word: str) -> list[str]:
    if not section.strip():
        return []
    # Split on repeated role headings or blank-line company starts
    parts = re.split(rf"(?i)(?={role_word})", section)
    blocks = [p.strip() for p in parts if p.strip() and len(p.strip()) > 20]
    if not blocks:
        blocks = [section.strip()]
    return blocks[:5]


# ---- method handlers ----

def method_header_place(field: dict, ctx: dict) -> tuple[Any, dict]:
    place, _, span = P.extract_header_place_date(ctx["text"])
    return place, _meta(span, "header_place", 0.85 if place else 0.2)


def method_header_date(field: dict, ctx: dict) -> tuple[Any, dict]:
    _, date, span = P.extract_header_place_date(ctx["text"])
    return date, _meta(span, "header_date", 0.85 if date else 0.2)


def method_czynnosc_date(field: dict, ctx: dict) -> tuple[Any, dict]:
    text = ctx["text"]
    # Prefer sentence describing the challenged act near first zarzut
    m_z = re.search(r"(?i)zarzut", text)
    focus = text[max(0, (m_z.start() if m_z else 400) - 500) : (m_z.start() if m_z else 0) + 200]
    labels = [
        "w dniu",
        "z dnia",
        "dnia",
        "czynność",
        "ogłoszono",
        "opublikowano",
        "dokonano",
        "unieważniono",
        "wykluczono",
        "odrzuceniu",
        "nie wykluczył",
        "nie odrzucił",
    ]
    date, span = P.extract_date_near_labels(focus or text[:2500], labels)
    if not date:
        date, span = P.extract_date_near_labels(text[:2500], ["w dniu", "z dnia"])
    # Avoid using document header place-date as czynnosc_dzien when identical and early
    return date, _meta(span, "czynnosc_date", 0.75 if date else 0.2)


def method_czynnosc_powod(field: dict, ctx: dict) -> tuple[Any, dict]:
    reasons = load_czynnosc_powod(ctx.get("configs_dir"))
    text = ctx["text"]
    # Prefer the lead-in before first "Zarzut" + first zarzut title (most signal)
    m_z = re.search(r"(?i)zarzut", text)
    if m_z:
        focus = text[max(0, m_z.start() - 500) : m_z.start() + 600]
    else:
        focus = text[:3500]
    # Extra patterns for "nie wykluczył / nie odrzucił / nie unieważnił"
    extra = [
        (8, "Zaniechanie wykluczenia wykonawcy", r"(?i)nie\s+wyklucz"),
        (7, "Zaniechanie odrzucenia oferty", r"(?i)nie\s+odrzuc"),
        (10, "Zaniechanie unieważnienia postępowania", r"(?i)nie\s+unieważn"),
        (8, "Zaniechanie wykluczenia wykonawcy", r"(?i)zaniechani\w*\s+wyklucz"),
        (7, "Zaniechanie odrzucenia oferty", r"(?i)zaniechani\w*\s+odrzuc"),
        (9, "Decyzja o unieważnieniu postępowania", r"(?i)unieważni(?:ł|ła|li|ono)\s+postępowanie"),
        (2, "Ogłoszenie wyboru oferty", r"(?i)(?:ogłosi(?:ł|ła)|wybra(?:ł|ła))\s+ofert"),
        (1, "Decyzja o odrzuceniu oferty", r"(?i)odrzuci(?:ł|ła|ono)\s+ofert"),
        (3, "Decyzja o wykluczeniu wykonawcy", r"(?i)wykluczy(?:ł|ła|ono)"),
        (4, "Publikacja specyfikacji warunków zamówienia (SWZ)", r"(?i)publikacj\w*\s+(?:swz|specyfikacj)"),
        (5, "Modyfikacja treści SWZ", r"(?i)modyfikacj\w*.{0,40}swz"),
        (6, "Odpowiedzi/wyjaśnienia do SWZ", r"(?i)wyjaśnieni\w*.{0,40}swz"),
        (11, "Opis przedmiotu zamówienia (OPZ)", r"(?i)zarzut.{0,80}op(?:is|z)\b"),
        (12, "Projektowane postanowienia umowy", r"(?i)projektowane\s+postanowienia"),
    ]
    best_id = None
    best_span = None
    best_score = -1
    best_opis = None

    def consider(rid, opis, span, pos, weight=1.0):
        nonlocal best_id, best_span, best_score, best_opis
        score = weight * (10000 - pos)
        # Penalize OPZ/PPU if they appear only as nested reference, not as main act
        if rid in (11, 12):
            score *= 0.35
        if score > best_score:
            best_score = score
            best_id = rid
            best_opis = opis
            best_span = span[:120] if span else None

    for rid, opis, pat in extra:
        m = re.search(pat, focus, flags=re.S)
        if m:
            consider(rid, opis, m.group(0), m.start(), weight=1.4)

    for r in reasons:
        for pat in r.get("patterns", []):
            m = re.search(pat, focus, flags=re.I | re.S)
            if m:
                consider(r["id"], r["opis"], m.group(0), m.start(), weight=1.0)

    ctx["czynnosc_id"] = best_id
    ctx["czynnosc_opis"] = best_opis
    return best_id, _meta(best_span, f"czynnosc_powod_{best_id}", 0.8 if best_id else 0.2)


def method_czynnosc_opis(field: dict, ctx: dict) -> tuple[Any, dict]:
    opis = ctx.get("czynnosc_opis")
    if opis is None and ctx.get("czynnosc_id"):
        for r in load_czynnosc_powod(ctx.get("configs_dir")):
            if r["id"] == ctx["czynnosc_id"]:
                opis = r["opis"]
                break
    return opis, _meta(opis, "czynnosc_opis", 0.9 if opis else 0.2)


def _extract_labeled_party(text: str, label: str) -> str:
    """Slice text from label until next major section header."""
    m = re.search(rf"(?im)^\s*{label}\s*:?\s*$", text)
    if not m:
        m = re.search(rf"(?i){label}\s*:", text)
    if not m:
        return ""
    rest = text[m.end() :]
    end = re.search(
        r"(?im)^\s*(?:Zamawiający|Odwołujący|O\s*D\s*W\s*O\s*Ł\s*A\s*N\s*I\s*E|ODWOŁANIE|"
        r"dotyczy|Zarzut|Pełnomocnik|Działając)\b",
        rest,
    )
    if end:
        return rest[: end.start()]
    return rest[:800]


def _party_from_section(section: str) -> dict[str, Any]:
    nip, _ = P.extract_nip(section)
    regon, _ = P.extract_regon(section)
    krs, _ = P.extract_krs(section)
    nazwa = None
    for ln in section.splitlines():
        ln = ln.strip().strip(",")
        if not ln:
            continue
        if re.search(r"(?i)^(KRS|NIP|REGON|ul\.|tel|kontakt|adres|reprezentowan|e-?mail)", ln):
            continue
        if "@" in ln:
            continue
        if len(ln) < 3:
            continue
        nazwa = clean_name(ln)
        break
    return {"krs": krs, "nazwa": nazwa, "nip": nip, "regon": regon}


def method_parties_odwolujacy(field: dict, ctx: dict) -> tuple[Any, dict]:
    section = _extract_labeled_party(ctx["text"], r"Odwołując[yaei]")
    if len(section) < 20:
        section = ctx["sections"].get("odwolujacy") or ctx["text"][:2000]
    p = _party_from_section(section)
    # pełnomocnik: "reprezentowana przez: adw. NAME"
    imie = None
    m = re.search(
        r"(?i)reprezentowan\w*\s+przez\s*:?\s*(?:adw\.?|r\.?\s*pr\.?|mec\.?)?\s*"
        r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+)",
        section + "\n" + ctx["text"][:2500],
    )
    if m:
        imie = clean_name(m.group(1))
    if not imie:
        m = re.search(
            r"(?i)(?:pełnomocnik(?:a|iem)?)\s*:?\s*(?:adw\.?|r\.?\s*pr\.?)?\s*"
            r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+)",
            ctx["text"][:3000],
        )
        if m:
            imie = clean_name(m.group(1))
    if imie:
        # drop trailing non-name tokens
        parts = imie.split()
        imie = clean_name(" ".join(p for p in parts[:3] if p[0].isupper()))
    kancelaria = None
    m = re.search(r"(?i)((?:Kancelaria|Kancelarii)[^,\n]{5,90})", section + "\n" + ctx["text"][:3000])
    if m:
        kancelaria = clean_name(m.group(1))
    mail = None
    # Prefer email in odwołujący block
    mail, _ = P.extract_email(section)
    if not mail:
        # emails after kancelaria / correspondence
        m = re.search(r"(?i)adres do korespondencji.{0,200}", ctx["text"], re.S)
        if m:
            mail, _ = P.extract_email(m.group(0))
    if not mail:
        emails = re.findall(P.RE_EMAIL.pattern, ctx["text"][:4000], flags=re.I)
        # skip zamawiający contact if two emails — take last in odwołujący area
        if emails:
            mail = emails[-1].lower() if len(emails) > 1 else emails[0].lower()
    przez = 1 if (imie or kancelaria or re.search(r"(?i)reprezentowan|pełnomocnik", section)) else 0
    pelnomocnik = {"imie_nazwisko": imie, "nazwa": kancelaria, "mail": mail} if przez else None
    parties = [
        {
            "krs": p["krs"],
            "nazwa": p["nazwa"],
            "nip": p["nip"],
            "regon": p["regon"],
            "przez-pelnomocnika": przez,
            "pelnomocnik": pelnomocnik,
        }
    ]
    return parties, _meta(section[:200], "parties_odwolujacy", 0.85)


def method_parties_zamawiajacy(field: dict, ctx: dict) -> tuple[Any, dict]:
    section = _extract_labeled_party(ctx["text"], r"Zamawiając[yaei]")
    if len(section) < 20:
        m = re.search(r"(?i)zamawiając.{0,900}", ctx["text"], re.S)
        section = m.group(0) if m else ""

    multi = bool(
        re.search(r"(?i)prowadząc\w*\s+postępowanie|lider\s+postępowania|wspólnie\s+z", section)
        or section.lower().count("nip:") > 1
        or section.lower().count("krs:") > 1
    )
    if multi:
        # split by company-like lines followed by identifiers
        chunks = re.split(r"\n(?=[A-ZĄĆĘŁŃÓŚŹŻ][^:\n]{6,}\n(?:.*\n)?(?:.*(?:KRS|NIP)))", section)
        chunks = [c.strip() for c in chunks if len(c.strip()) > 20]
        if len(chunks) < 2:
            chunks = [section]
    else:
        chunks = [section]

    parties = []
    for block in chunks:
        p = _party_from_section(block)
        if not p["nazwa"] and not p["nip"] and not p["krs"]:
            continue
        if p["nazwa"] and "@" in (p["nazwa"] or ""):
            continue
        flag = None
        if multi:
            flag = 1 if re.search(r"(?i)prowadząc\w*\s+postępowanie|lider", block) else 0
        parties.append(
            {
                "krs": p["krs"],
                "nazwa": p["nazwa"],
                "nip": p["nip"],
                "regon": p["regon"],
                "prowadzacy_postepowanie": flag,
            }
        )
    if not parties:
        p = _party_from_section(section)
        parties = [
            {
                "krs": p["krs"],
                "nazwa": p["nazwa"],
                "nip": p["nip"],
                "regon": p["regon"],
                "prowadzacy_postepowanie": None,
            }
        ]
    if multi and parties and all(x["prowadzacy_postepowanie"] == 0 for x in parties):
        parties[0]["prowadzacy_postepowanie"] = 1
    if not multi and parties:
        for x in parties:
            x["prowadzacy_postepowanie"] = None
        parties = parties[:1]
    return parties, _meta(section[:200], "parties_zamawiajacy", 0.85)


def method_zamowienie(field: dict, ctx: dict) -> tuple[Any, dict]:
    text = ctx["text"]
    bzp, bzp_span = P.extract_bzp(text)
    ted, ted_span = P.extract_ted(text)
    nr, nr_span = P.extract_postepowanie(text)
    tytul = None
    tytul_span = None
    # Prefer quoted title after pn. / „...”
    m = re.search(r"(?i)(?:pn\.|pt\.)\s*[„\"]([^”\"]{10,200})[”\"]", text)
    if m:
        tytul = clean_name(m.group(1))
        tytul_span = m.group(0)
    if not tytul:
        m = re.search(r"[„\"]([^”\"]{15,200})[”\"]", text)
        if m:
            tytul = clean_name(m.group(1))
            tytul_span = m.group(0)
    if not tytul:
        m = re.search(
            r"(?i)(?:przedmiot(?:em)?\s+zamówienia|nazwa\s+zamówienia)\s*[:\-]?\s*(.{15,200})",
            text,
        )
        if m:
            tytul = clean_name(m.group(1))
            tytul_span = m.group(0)
    data = {
        "numer_bzp": bzp,
        "numer_postepowania": nr,
        "numer_ted": ted,
        "tytul": tytul,
    }
    span = tytul_span or bzp_span or ted_span or nr_span
    return data, _meta(span, "zamowienie", 0.7)


def method_labeled_date(field: dict, ctx: dict) -> tuple[Any, dict]:
    text = ctx["text"]
    labels = field.get("labels", [])
    # Prefer explicit operation/execution date labels over letter header date
    for lab in ("data wykonania", "data operacji", "data przelewu", "data księgowania"):
        m = re.search(
            rf"(?i){re.escape(lab)}\s*[:\-]?\s*(\d{{1,2}}[.\-/]\d{{1,2}}[.\-/]\d{{4}}|\d{{1,2}}\s+[A-Za-ząćęłńóśźż]+\s+\d{{4}})",
            text,
        )
        if m:
            return normalize_date(m.group(1)), _meta(m.group(0), "labeled_date", 0.95)
    m = re.search(
        r"(?i)w\s+dniu\s+(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}|\d{1,2}\s+[A-Za-ząćęłńóśźż]+\s+\d{4})",
        text,
    )
    if m:
        return normalize_date(m.group(1)), _meta(m.group(0), "labeled_date", 0.9)
    date, span = P.extract_date_near_labels(text, labels)
    return date, _meta(span, "labeled_date", 0.8 if date else 0.2)


def method_labeled_amount(field: dict, ctx: dict) -> tuple[Any, dict]:
    amt, span = P.extract_amount_near_labels(ctx["text"], field.get("labels", []))
    return amt, _meta(span, "labeled_amount", 0.8 if amt is not None else 0.2)


def method_labeled_account(field: dict, ctx: dict) -> tuple[Any, dict]:
    acc, span = P.extract_account_near_labels(ctx["text"], field.get("labels", []))
    return acc, _meta(span, "labeled_account", 0.8 if acc else 0.2)


def method_labeled_text(field: dict, ctx: dict) -> tuple[Any, dict]:
    val, span = P.extract_labeled_line(ctx["text"], field.get("labels", []), multiline=False)
    norm = field.get("normalize")
    if norm == "transaction_id":
        # Also search CEN pattern globally
        if not val:
            m = re.search(r"(CEN\d{10,})", ctx["text"], re.I)
            if m:
                val, span = m.group(1), m.group(1)
        val = normalize_transaction_id(val)
    return val, _meta(span, "labeled_text", 0.75 if val else 0.2)


def method_labeled_multiline(field: dict, ctx: dict) -> tuple[Any, dict]:
    val, span = P.extract_labeled_line(ctx["text"], field.get("labels", []), multiline=True)
    if not val:
        m = re.search(
            r"(?i)(?:tytułem|tytuł\s+przelewu|tytul\s+przelewu|tytuł)\s*[:\-]?\s*[„\"]?([^”\"\n]{10,300})[”\"]?",
            ctx["text"],
        )
        if m:
            val, span = clean_name(m.group(1).strip().strip("„”\"")), m.group(0)
    if val:
        val = val.strip().strip("„”\"'.")
        val = re.sub(r"(?i)\s+Status$", "", val).strip()
        # drop leading artifacts like "em " from "Tytułem"
        val = re.sub(r"(?i)^em\s+", "", val)
    return val, _meta(span, "labeled_multiline", 0.75 if val else 0.2)


def method_pelnomocnictwo_mocodawca(field: dict, ctx: dict) -> tuple[Any, dict]:
    text = ctx["text"]
    # Spaced title cleanup
    text_work = re.sub(r"(?i)P\s+E\s+Ł\s+N\s+O\s+M\s+O\s+C\s+N\s+I\s+C\s+T\s+W\s+O", "Pełnomocnictwo", text)
    text = text_work
    # Block form: Mocodawca\nCOMPANY\n...\nKRS ...
    m_block = re.search(
        r"(?is)Mocodawc\w*\s*\n\s*([^\n]{5,120})\n.{0,200}?KRS\s*[:\-]?\s*(\d+).{0,40}?NIP\s*[:\-]?\s*([0-9\- ]+)",
        text,
    )
    if m_block:
        nazwa = clean_name(m_block.group(1))
        krs = normalize_krs(m_block.group(2))
        nip = normalize_nip(m_block.group(3))
        # signatures / podpisujący often later — handled below
        imie = None
        typ = "osoba_prawna"
        podpisujacy = [{"imie_nazwisko": None}]
        mocodawcy = [
            {
                "data": {
                    "imie_nazwisko": None,
                    "krs": krs,
                    "nazwa": nazwa,
                    "nip": nip,
                    "typ": typ,
                },
                "podpisujacy": podpisujacy,
            }
        ]
        # try find signer at end
        tail = "\n".join(text.splitlines()[-8:])
        for ln in reversed(tail.splitlines()):
            ln = ln.strip().strip(".")
            if not ln or set(ln) <= {"."}:
                continue
            if re.search(r"(?i)^(dyrektor|prezes|członek|prokurent|mocodawca|pełnomoc)", ln):
                continue
            pm = re.fullmatch(_PERSON_NAME.pattern, ln) or _PERSON_NAME.search(ln)
            if pm and not _COMPANY_HINT.search(pm.group(1)):
                mocodawcy[0]["podpisujacy"] = [{"imie_nazwisko": clean_name(pm.group(1))}]
                break
        return mocodawcy, _meta(nazwa, "pelnomocnictwo_mocodawca_block", 0.85)

    # Typical: "COMPANY z siedzibą ... (KRS ..., NIP ...) udzielam/ustanawiam"
    m = re.search(
        r"(?is)(?:Pełnomocnictwo\s+)?(.+?)\s+(?:z\s+siedzibą|z\s+siedziba).{0,80}?"
        r"(?:\(?(?:KRS\s*[:\-]?\s*(\d+))?.*?(?:NIP\s*[:\-]?\s*([0-9\- ]+))?.*?\)?)?"
        r".{0,60}?(?:udzielam\s+pełnomocnictwa|ustanawiam\s+pełnomocnikiem|upoważniam)",
        text,
    )
    nazwa = None
    krs = None
    nip = None
    if m:
        nazwa = clean_name(re.sub(r"(?i)^Pełnomocnictwo\s+", "", m.group(1)))
        krs = normalize_krs(m.group(2)) if m.lastindex and m.group(2) else None
        nip = normalize_nip(m.group(3)) if m.lastindex >= 3 and m.group(3) else None
    if not krs:
        krs, _ = P.extract_krs(text)
    if not nip:
        nip, _ = P.extract_nip(text)
    if not nazwa:
        # first substantial line after title
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for ln in lines[:5]:
            if re.search(r"(?i)^pełnomocnictwo$", ln):
                continue
            nazwa = clean_name(re.split(r"\s+z\s+siedzib", ln, flags=re.I)[0])
            break

    imie = None
    typ = "osoba_prawna"
    if nazwa and (re.search(r"[A-ZĄĆĘŁŃÓŚŹŻ]{2,}[-–]", nazwa) or (not krs and not _COMPANY_HINT.search(nazwa))):
        # sole trader style: DUDEK-TECH Jarosław Dudek
        pm = _PERSON_NAME.search(nazwa)
        if pm and not _COMPANY_HINT.search(nazwa):
            imie = clean_name(pm.group(1))
            typ = "osoba_fizyczna"
        elif re.search(r"(?i)\bsp\.\s*z|\bs\.a\b|\bsp\.\s*j\b|\bsp\.\s*k\b", nazwa or ""):
            typ = "osoba_prawna"
            imie = None
        elif krs:
            typ = "osoba_prawna"
            imie = None

    # Signature: last person-like lines before role titles
    podpisujacy = []
    tail = "\n".join(text.splitlines()[-8:])
    skip = {"dyrektor", "prezes", "członek", "zarządu", "prokurent", "właściciel"}
    for ln in reversed(tail.splitlines()):
        ln = ln.strip().strip(".")
        if not ln or set(ln) <= {"."}:
            continue
        if ln.lower() in skip or re.search(r"(?i)^(dyrektor|prezes|członek|prokurent)", ln):
            continue
        if re.search(r"\d{4}", ln):  # date line
            continue
        pm = re.fullmatch(_PERSON_NAME.pattern, ln) or _PERSON_NAME.search(ln)
        if pm and not _COMPANY_HINT.search(pm.group(1)):
            podpisujacy.append({"imie_nazwisko": clean_name(pm.group(1))})
            break
    if typ == "osoba_fizyczna" and imie and not podpisujacy:
        podpisujacy = [{"imie_nazwisko": imie}]
    if not podpisujacy:
        podpisujacy = [{"imie_nazwisko": None}]

    mocodawcy = [
        {
            "data": {
                "imie_nazwisko": imie if typ == "osoba_fizyczna" else None,
                "krs": krs,
                "nazwa": nazwa,
                "nip": nip,
                "typ": typ,
            },
            "podpisujacy": podpisujacy,
        }
    ]
    # Multiple mocodawcy (konsorcjum) — rare; detect repeated KRS blocks
    krs_all = re.findall(r"(?i)KRS\s*[:\-]?\s*(\d{6,10})", text)
    if len(set(krs_all)) > 1:
        mocodawcy = []
        for km in re.finditer(
            r"(?is)([A-ZĄĆĘŁŃÓŚŹŻ][^()]{5,80}?)\s*\((?=.*KRS)[^)]*KRS\s*[:\-]?\s*(\d+)[^)]*NIP\s*[:\-]?\s*([0-9\- ]+)[^)]*\)",
            text,
        ):
            mocodawcy.append(
                {
                    "data": {
                        "imie_nazwisko": None,
                        "krs": normalize_krs(km.group(2)),
                        "nazwa": clean_name(km.group(1)),
                        "nip": normalize_nip(km.group(3)),
                        "typ": "osoba_prawna",
                    },
                    "podpisujacy": podpisujacy,
                }
            )
        if not mocodawcy:
            mocodawcy = [
                {
                    "data": {
                        "imie_nazwisko": None,
                        "krs": normalize_krs(krs_all[0]),
                        "nazwa": nazwa,
                        "nip": nip,
                        "typ": "osoba_prawna",
                    },
                    "podpisujacy": podpisujacy,
                }
            ]
    return mocodawcy, _meta(nazwa, "pelnomocnictwo_mocodawca", 0.85)


def method_pelnomocnictwo_pelnomocnicy(field: dict, ctx: dict) -> tuple[Any, dict]:
    text = ctx["text"]
    people: list[dict[str, Any]] = []
    # "udzielam pełnomocnictwa adw. NAME" / "ustanawiam pełnomocnikiem adw. NAME"
    for m in re.finditer(
        r"(?is)(?:udzielam\s+pełnomocnictwa|ustanawiam\s+pełnomocnikiem)\s+(?:adw\.?|r\.?\s*pr\.?|mec\.?)?\s*"
        r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+)",
        text,
    ):
        people.append({"imie_nazwisko": clean_name(m.group(1)), "pesel": None})
    # Section Pełnomocnicy\nadw. A,\nadw. B
    msec = re.search(r"(?is)Pełnomocnicy\s*(.*?)(?:Zamawiając|Postępowanie|Zakres|Mocodawca\s+upoważ|$)", text)
    zone_extra = msec.group(1) if msec else ""
    for m in re.finditer(
        r"(?i)(?:adw\.?|r\.?\s*pr\.?|mec\.?)\s*"
        r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+)",
        zone_extra + "\n" + text[:1500],
    ):
        n = clean_name(m.group(1))
        if n and all(p["imie_nazwisko"] != n for p in people):
            people.append({"imie_nazwisko": n, "pesel": None})
    # "oraz adw. NAME" — require title abbreviation
    for m in re.finditer(
        r"(?i)(?:oraz|,)\s+(?:adw\.?|r\.?\s*pr\.?|mec\.?)\s+"
        r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+)",
        text,
    ):
        n = clean_name(m.group(1))
        if n and all(p["imie_nazwisko"] != n for p in people):
            people.append({"imie_nazwisko": n, "pesel": None})
    # PESEL-tagged
    for m in re.finditer(
        r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+){1,2})"
        r".{0,40}?PESEL\s*[:\-]?\s*(\d{11})",
        text,
        re.S,
    ):
        n = clean_name(m.group(1))
        pesel = normalize_pesel(m.group(2))
        found = False
        for p in people:
            if p["imie_nazwisko"] == n:
                p["pesel"] = pesel
                found = True
        if not found:
            people.append({"imie_nazwisko": n, "pesel": pesel})
    # Filter garbage
    cleaned = []
    for p in people:
        n = p["imie_nazwisko"] or ""
        if len(n.split()) < 2:
            continue
        if re.search(r"(?i)pełnomocnict|udzielam|spółki|postępowan|wpisu", n):
            continue
        cleaned.append(p)
    people = cleaned or [{"imie_nazwisko": None, "pesel": None}]
    return people, _meta(str(people[0].get("imie_nazwisko")), "pelnomocnictwo_pelnomocnicy", 0.8)


METHOD_HANDLERS = {
    "header_place": method_header_place,
    "header_date": method_header_date,
    "czynnosc_date": method_czynnosc_date,
    "czynnosc_powod": method_czynnosc_powod,
    "czynnosc_opis": method_czynnosc_opis,
    "parties_odwolujacy": method_parties_odwolujacy,
    "parties_zamawiajacy": method_parties_zamawiajacy,
    "zamowienie": method_zamowienie,
    "labeled_date": method_labeled_date,
    "labeled_amount": method_labeled_amount,
    "labeled_account": method_labeled_account,
    "labeled_text": method_labeled_text,
    "labeled_multiline": method_labeled_multiline,
    "pelnomocnictwo_mocodawca": method_pelnomocnictwo_mocodawca,
    "pelnomocnictwo_pelnomocnicy": method_pelnomocnictwo_pelnomocnicy,
}
