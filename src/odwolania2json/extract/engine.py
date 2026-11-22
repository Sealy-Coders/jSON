from __future__ import annotations

from typing import Any

import regex as re

from odwolania2json.config_loader import load_czynnosc_powod, load_extractor_config, load_pipeline_config
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
    min_confidence: float | None = None,
) -> dict[str, Any]:
    cfg = load_extractor_config(doc_type, configs_dir)
    if min_confidence is None:
        min_confidence = float(load_pipeline_config(configs_dir).get("min_field_confidence", 0.0))
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
        confidence = (meta or {}).get("confidence", 0.7)
        threshold = float(field.get("min_confidence", min_confidence))
        suppressed = None
        if value is not None and not isinstance(value, (dict, list)) and confidence < threshold:
            suppressed = {"value": value, "reason": f"confidence {confidence:.2f} < {threshold:.2f}"}
            value = None
        _assign_path(result, path, value)
        if meta:
            trace.add(
                path=path,
                value=value,
                page=meta.get("page") or page_for_span(doc_text, meta.get("span")),
                rule_id=meta.get("rule_id", method),
                method=method,
                confidence=confidence,
                source_span=meta.get("span"),
                suppressed=suppressed,
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
    act = _act_sentence(text)
    if act:
        date, span = P.extract_date_near_labels(act, ["w dniu", "dnia"])
        if date:
            return date, _meta(span, "czynnosc_date", 0.8)
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


_SENTENCE_END = re.compile(r"(?<!\br)(?<!\bnr)(?<!\bust)(?<!\bart)(?<!\bpkt)(?<!\bo)\.\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])")


def _act_sentence(text: str) -> str | None:
    """Sentence 'Zamawiający [zawiadomił] w dniu … <czynność>.' preceding the first allegation."""
    m_z = re.search(r"(?i)\bzarzut", text)
    head = text[: m_z.start()] if m_z else text[:4000]
    flat = re.sub(r"\s+", " ", head)
    cands = list(re.finditer(r"Zamawiający\b(?=[^.]{0,60}?\b(?:w dniu|dnia|zawiadomi))", flat))
    if not cands:
        return None
    sent = flat[cands[-1].start() : cands[-1].start() + 400]
    end = _SENTENCE_END.search(sent)
    return sent[: end.start() + 1] if end else sent


def method_czynnosc_powod(field: dict, ctx: dict) -> tuple[Any, dict]:
    reasons = load_czynnosc_powod(ctx.get("configs_dir"))
    text = ctx["text"]
    act = _act_sentence(text)
    if act:
        ranked = sorted(reasons, key=lambda r: -int(r.get("priority", 0)))
        for r in ranked:
            for pat in r.get("act_patterns", []):
                m = re.search(pat, act, flags=re.I)
                if m:
                    ctx["czynnosc_id"] = r["id"]
                    ctx["czynnosc_opis"] = r["opis"]
                    return r["id"], _meta(act[:200], f"czynnosc_powod_{r['id']}_act ({m.group(0)})", 0.9)
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
    return best_id, _meta(best_span, f"czynnosc_powod_{best_id}_fallback", 0.6 if best_id else 0.2)


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
        r"dotyczy|Zarzut|Pełnomocnik|Działając|Wykonawc\w*\s+wybran\w*|Przystępując\w*|Uczestnik\w*)\b",
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
    # Consortium: '1) Lider Konsorcjum:' … '2) Partner Konsorcjum:' → the first member is the appellant.
    m_first = re.search(r"(?m)^\s*1\s*\)[^\n]*:\s*$", section)
    if m_first:
        m_next = re.search(r"(?m)^\s*2\s*\)", section[m_first.end() :])
        member = section[m_first.end() : m_first.end() + m_next.start()] if m_next else section[m_first.end() :]
        p = _party_from_section(member)
    else:
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
    m = re.search(
        r"(?i)adres\w*\s+do\s+korespondencji\s*:\s*([^,\n]*Kancelari[^,\n]*(?:\n(?!\s*(?:ul\.|tel|e-?mail|al\.|pl\.|\d))[^,\n]{3,60})?)",
        section + "\n" + ctx["text"][:3000],
    ) or re.search(
        r"(?i)((?:Kancelaria|Kancelarii)[^,\n]{5,90}(?:\n(?!\s*(?:ul\.|tel|e-?mail|al\.|pl\.|\d))[^,\n]{3,60})?)",
        section + "\n" + ctx["text"][:3000],
    )
    if m:
        kancelaria = clean_name(m.group(1).replace("\n", " "))
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
            mail = P.fold_email(emails[-1] if len(emails) > 1 else emails[0])
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


_NUMBERED_ZAMAWIAJACY = re.compile(r"(?m)^\s*\d{1,2}\s*[\).]\s*Zamawiający\b[^\n]*$")


def _numbered_zamawiajacy(text: str) -> list[dict[str, Any]] | None:
    """'1) Zamawiający – Lider, prowadzący postępowanie:' / '2) Zamawiający – Partner:' blocks."""
    head = text[:6000]
    stop = re.search(r"(?im)^\s*(?:dotyczy|ODWOŁANIE|Działając)\b", head)
    hdrs = [h for h in _NUMBERED_ZAMAWIAJACY.finditer(head) if not stop or h.start() < stop.start()]
    if len(hdrs) < 2:
        return None
    parties = []
    for i, h in enumerate(hdrs):
        end = hdrs[i + 1].start() if i + 1 < len(hdrs) else (stop.start() if stop else h.end() + 600)
        block = head[h.end() : end]
        p = _party_from_section(block)
        lead = bool(re.search(r"(?i)lider|prowadząc\w*\s+postępowanie|pełnomocnik\s+zamawiających", h.group(0)))
        parties.append(
            {
                "krs": p["krs"],
                "nazwa": p["nazwa"],
                "nip": p["nip"],
                "regon": p["regon"],
                "prowadzacy_postepowanie": 1 if lead else 0,
            }
        )
    if parties and not any(x["prowadzacy_postepowanie"] for x in parties):
        return [dict(x, prowadzacy_postepowanie=None) for x in parties]
    return parties


def method_parties_zamawiajacy(field: dict, ctx: dict) -> tuple[Any, dict]:
    numbered = _numbered_zamawiajacy(ctx["text"])
    if numbered:
        return numbered, _meta(None, "parties_zamawiajacy_numbered", 0.85)
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
    # Labels are tried in YAML order — put operation/execution labels before
    # order/generation dates ('data zlecenia', 'wygenerowano') in the config.
    date, span = P.extract_date_near_labels(text, labels)
    if date:
        return date, _meta(span, "labeled_date", 0.9)
    return None, _meta(None, "labeled_date_not_found", 0.0)


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
        val = normalize_transaction_id(val)
        if not val:
            m = re.search(r"(CEN\d{10,})", ctx["text"], re.I)
            if m:
                val, span = normalize_transaction_id(m.group(1)), m.group(0)
    return val, _meta(span, "labeled_text", 0.75 if val else 0.2)


def method_labeled_multiline(field: dict, ctx: dict) -> tuple[Any, dict]:
    stop_labels = field.get("stop_labels") or []
    if stop_labels:
        val, span = P.extract_block_after_label(
            ctx["text"], field.get("labels", []), stop_labels, int(field.get("max_lines", 4))
        )
        if val:
            return val, _meta(span, "labeled_block", 0.85)
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


_ROLE_LINE = re.compile(
    r"(?i)^(?:wice)?(?:prezes|dyrektor|członek|członkini|prokurent|właściciel|wspólnik|pełnomocnik|"
    r"zarząd|kierownik|główn|skarbnik|burmistrz|wójt|starosta|komplementariusz|przewodnicząc|"
    r"mocodawca|podpis|data|miejscowość)"
)
_NAME_LINE = re.compile(
    r"^([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)?"
    r"(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)?){1,2})"
    r"\s*(?:[,–\-]\s*.*)?$"
)
_TITLE_PREFIX = re.compile(
    r"(?i)^\s*(?:PEŁNOMOCNICTWO|PEŁNOMOCNICTWA)(?:\s+(?:PROCESOWE|SZCZEGÓLNE|OGÓLNE|DO\s+REPREZENTOWANIA))?\s*[:\-]?\s*"
)
_NAME_END = (
    r"(?=\s*\(|\s*,\s*(?:ul\.|al\.|z\s+siedzib|KRS|NIP|REGON|adres|wpisan|posiadając|zarejestrowan|\d{2}-\d{3})"
    r"|\s+z\s+siedzib|\s+niniejszym|\s+udzielam|\s+ustanawiam|\s+upoważniam|\s*$)"
)
_MOCODAWCA_NAME_PATTERNS = [
    ("mocodawca_jest", re.compile(rf"(?im)Mocodawc\w*\s+jest\s+([^\n(]{{3,150}}?){_NAME_END}")),
    ("dzialajac_w_imieniu", re.compile(
        rf"(?im)Działając\s+w\s+imieniu\s+(?:i\s+na\s+rzecz\s+)?([^\n(]{{3,150}}?){_NAME_END}"
    )),
    ("po_tytule", re.compile(rf"(?m)^\s*PEŁNOMOCNICTWO[^\n]*\n\s*([^\n(]{{3,150}}?){_NAME_END}")),
    ("line_z_siedziba", re.compile(rf"(?m)^([^\n(]{{3,150}}?)\s+z\s+siedzib")),
    ("mocodawca_block", re.compile(r"(?im)^\s*Mocodawc\w*\s*:?\s*\n\s*([^\n]{3,150})$")),
]


def _valid_party_name(name: str | None) -> bool:
    if not name or len(name) < 3:
        return False
    if P.RE_DATE.search(name) or P.RE_PL_DATE.search(name):
        return False
    if re.search(r"(?i)^(?:§|\d|mocodawc|pełnomocni|niniejszym|działając|ul\.|ja\b|my\b|niżej|wykonawc)", name):
        return False
    if sum(ch.isalpha() for ch in name) < 3:
        return False
    return sum(ch.isdigit() for ch in name) <= 3


_FLAT_NAME = r"[^;()]{3,120}?"
_CONSORTIUM_MEMBER = re.compile(
    rf"(?<![\w.])\d\s*\)\s*({_FLAT_NAME}),\s*(?:ul\.|al\.|pl\.|os\.)[^;]*?KRS\s*[:\-]?\s*(\d{{10}})[^;]*?NIP\s*[:\-]?\s*(\d{{10}})"
)
_SOLE_TRADER = re.compile(
    rf"pod\s+firmą\s+({_FLAT_NAME}),\s*(?:ul\.|al\.|pl\.|NIP|z\s+siedzib|\d{{2}}-\d{{3}})"
)
_SIGNED_PERSON = re.compile(
    r"niżej\s+podpisan\w*\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+)"
)


def _consortium_members(text: str) -> list[dict[str, Any]]:
    flat = re.sub(r"\s+", " ", text[:4000])
    members = []
    for m in _CONSORTIUM_MEMBER.finditer(flat):
        name = clean_name(m.group(1))
        if _valid_party_name(name):
            members.append({"nazwa": name, "krs": normalize_krs(m.group(2)), "nip": normalize_nip(m.group(3))})
    return members if len(members) >= 2 else []


def _sole_trader(text: str) -> dict[str, Any] | None:
    flat = re.sub(r"\s+", " ", text[:3000])
    m = _SOLE_TRADER.search(flat)
    if not m:
        return None
    firm = clean_name(m.group(1))
    person = _SIGNED_PERSON.search(flat)
    imie = person.group(1) if person else None
    if not imie:
        pm = _PERSON_NAME.search(firm or "")
        imie = pm.group(1) if pm else None
    return {"nazwa": firm, "imie_nazwisko": clean_name(imie) if imie else None}


def _mocodawca_name(text: str) -> tuple[str | None, str | None]:
    for rule, rx in _MOCODAWCA_NAME_PATTERNS:
        for m in rx.finditer(text):
            name = clean_name(_TITLE_PREFIX.sub("", m.group(1)))
            if name:
                name = re.sub(r"\s*\(dalej.*$", "", name).strip(" ,;")
            if _valid_party_name(name):
                return name, rule
    return None, None


def _attorney_names(text: str) -> set[str]:
    names = set()
    for m in re.finditer(
        r"(?:adw\.?|r\.\s*pr\.?|radc\w*\s+prawn\w*|adwokat\w*|mec\.)\s+"
        r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+)",
        text,
    ):
        names.add(m.group(1))
    return names


def _signers(text: str, grouped: bool = False) -> Any:
    """Names printed under dotted signature lines of the grantor.

    Signatures after 'Pełnomocnictwo przyjmuję' and attorney signatures
    (r. pr./adw.) are skipped — those are the representatives, not the signer.
    grouped=True returns [(group_label | None, name)], where group_label comes
    from 'W imieniu <firma>:' lines (consortium documents).
    """
    lines = [ln.strip() for ln in text.splitlines()]
    attorneys = _attorney_names(text)
    out: list[str] = []
    groups: list[tuple[str | None, str]] = []
    group: str | None = None
    grantor_zone = True
    for i, ln in enumerate(lines):
        if re.search(r"(?i)przyjmuję|podpis\s+pełnomocnik", ln):
            grantor_zone = False
        gm = re.match(r"(?i)^(?:w\s+imieniu|za)\s+(.+?):?\s*$", ln)
        if gm and not re.fullmatch(r"[.…_\s]{5,}", ln):
            group = clean_name(gm.group(1))
        if not grantor_zone or not re.fullmatch(r"[.…_\s]{5,}", ln):
            continue
        for j in range(i + 1, min(i + 4, len(lines))):
            cand = lines[j]
            if not cand or re.match(r"(?i)^za\s+", cand) or _ROLE_LINE.match(cand):
                continue
            if re.match(r"(?i)^(?:r\.\s*pr\.|adw\.|radca|adwokat|mec\.)", cand):
                break
            m = _NAME_LINE.match(cand)
            if m and not _COMPANY_HINT.search(m.group(1)) and m.group(1) not in attorneys:
                if m.group(1) not in out:
                    out.append(m.group(1))
                    groups.append((group, m.group(1)))
            break
    return groups if grouped else out


def _norm_company(s: str | None) -> str:
    return re.sub(r"[^a-ząćęłńóśźż0-9]", "", (s or "").lower())


def method_pelnomocnictwo_mocodawca(field: dict, ctx: dict) -> tuple[Any, dict]:
    text = ctx["text"]
    members = _consortium_members(text)
    if members:
        grouped = _signers(text, grouped=True)
        result = []
        for mem in members:
            key = _norm_company(mem["nazwa"])
            own = [n for g, n in grouped if g and (_norm_company(g) in key or key in _norm_company(g))]
            result.append(
                {
                    "data": {"imie_nazwisko": None, "krs": mem["krs"], "nazwa": mem["nazwa"], "nip": mem["nip"], "typ": "osoba_prawna"},
                    "podpisujacy": [{"imie_nazwisko": n} for n in own] or [{"imie_nazwisko": None}],
                }
            )
        return result, _meta(members[0]["nazwa"], "pelnomocnictwo_mocodawca_konsorcjum", 0.85)

    trader = _sole_trader(text)
    if trader and trader["nazwa"]:
        nip, _ = P.extract_nip(text)
        signers = _signers(text) or ([trader["imie_nazwisko"]] if trader["imie_nazwisko"] else [])
        result = [
            {
                "data": {
                    "imie_nazwisko": trader["imie_nazwisko"],
                    "krs": None,
                    "nazwa": trader["nazwa"],
                    "nip": nip,
                    "typ": "osoba_fizyczna",
                },
                "podpisujacy": [{"imie_nazwisko": s} for s in signers] or [{"imie_nazwisko": None}],
            }
        ]
        return result, _meta(trader["nazwa"], "pelnomocnictwo_mocodawca_jdg", 0.85)

    result, meta = _mocodawca_legacy(field, ctx)
    name, rule = _mocodawca_name(text)
    signers = _signers(text)
    attorneys = _attorney_names(text)
    for moc in result:
        data = moc["data"]
        if len(result) == 1 and name:
            data["nazwa"] = name
            meta["rule_id"] = f"pelnomocnictwo_mocodawca_{rule}"
        elif data.get("nazwa"):
            cleaned = clean_name(_TITLE_PREFIX.sub("", data["nazwa"]))
            data["nazwa"] = cleaned if _valid_party_name(cleaned) else None
        if signers:
            moc["podpisujacy"] = [{"imie_nazwisko": s} for s in signers]
        else:
            moc["podpisujacy"] = [
                p for p in moc.get("podpisujacy", [])
                if p.get("imie_nazwisko") and p["imie_nazwisko"] not in attorneys
                and not _ROLE_LINE.match(p["imie_nazwisko"])
            ] or [{"imie_nazwisko": None}]
    return result, meta


def _mocodawca_legacy(field: dict, ctx: dict) -> tuple[Any, dict]:
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
        if not all(tok[:1].isupper() for tok in n.split()):
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
