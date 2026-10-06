"""Rule-based baseline extractor.

Two jobs:
1. The comparison point in evals. An LLM extractor has to beat this to justify its cost.
2. Offline mode: the whole pipeline can run without an API key (tests, demos, CI).

It knows the label vocabulary of Slovak and German claim documents. On unfamiliar layouts
it degrades to nulls; it never invents values.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from aip.agents.extraction import Confidence, Evidence, ExtractedDocument, LineItem

_DATE = r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})"
_AMOUNT = r"(\d{1,3}(?:[ .]\d{3})*,\d{2})"


def _parse_date(m: re.Match[str] | None) -> date | None:
    if m is None:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _parse_amount(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(" ", "").replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _after(labels: list[str], text: str, value: str = r"(.+)") -> re.Match[str] | None:
    for label in labels:
        m = re.search(rf"{re.escape(label)}\s*:?\s*{value}", text)
        if m:
            return m
    return None


def extract(text: str) -> ExtractedDocument:
    t = text
    lower = t.lower()
    language = (
        "de"
        if any(w in t for w in ("Rechnung", "Schaden", "Kosten", "Polizze"))
        else (
            "sk"
            if any(w in lower for w in ("poist", "faktúra", "rozpočet", "hlásenie"))
            else "other"
        )
    )
    if re.search(r"rozpočet|cenová ponuka|kostenvoranschlag", lower):
        doc_type = "repair_estimate"
    elif re.search(r"hlásenie poistnej|oznámenie škody|schadenmeldung|schadensanzeige", lower):
        doc_type = "claim_form"
    elif re.search(r"faktúra|rechnung", lower):
        doc_type = "invoice"
    else:
        doc_type = "other"

    evidence: list[Evidence] = []

    def keep(field: str, m: re.Match[str] | None) -> re.Match[str] | None:
        if m is not None:
            evidence.append(
                Evidence(field=field, quote=m.group(0).strip(), confidence=Confidence.MEDIUM)
            )
        return m

    policy = keep(
        "policy_number",
        _after(
            [
                "Číslo poistnej zmluvy",
                "Poistná zmluva č.",
                "Polizzennummer",
                "Versicherungsvertrag Nr.",
            ],
            t,
            r"([A-Z]{3}-\d{4}-[0-9A-F]{8})",
        ),
    )
    name = keep("claimant_name", _after(["Poistník", "Versicherungsnehmer"], t, r"(.+)"))
    if name is None:
        m = re.search(r"(?:Odberateľ|Kunde):\s*\n(.+)", t)
        name = keep("claimant_name", m)
    event = keep(
        "event_date",
        _after(
            [
                "Dátum poistnej udalosti",
                "Dátum vzniku škody",
                "Schadendatum",
                "Datum des Schadenereignisses",
            ],
            t,
            _DATE,
        ),
    )
    issue = _after(
        ["Dátum vystavenia", "Rechnungsdatum", "Dátum hlásenia", "Datum der Meldung"], t, _DATE
    )
    total = keep(
        "total_amount",
        _after(
            [
                "Spolu s DPH",
                "Celková suma na úhradu",
                "Gesamtbetrag inkl. USt",
                "Zu zahlender Betrag",
            ],
            t,
            _AMOUNT,
        ),
    )
    iban = keep("iban", re.search(r"\b([A-Z]{2}\d{2}[A-Z0-9]{11,30})\b", t))
    number = re.search(
        r"(?:č\.|Nr\.|Číslo faktúry:|Číslo ponuky:|Číslo hlásenia:|"
        r"Rechnungsnummer:|Angebotsnummer:|Meldungsnummer:)\s*(\d{5,})",
        t,
    )
    items = [
        LineItem(description=m.group(1).strip(), amount=_parse_amount(m.group(2)) or Decimal(0))
        for m in re.finditer(rf"^(.+?)\s*\.{{3,}}\s*{_AMOUNT}\s*EUR", t, re.MULTILINE)
    ]
    first_line = t.strip().splitlines()[0].strip() if t.strip() else None
    vendor = first_line if doc_type in ("invoice", "repair_estimate") else None
    description = re.search(r"(?:Popis udalosti|Schadenhergang):\s*\n(.+)", t)

    return ExtractedDocument(
        doc_type=doc_type,  # type: ignore[arg-type]
        language=language,  # type: ignore[arg-type]
        policy_number=policy.group(1) if policy else None,
        claimant_name=name.group(1).strip() if name else None,
        event_date=_parse_date(event),
        issue_date=_parse_date(issue),
        vendor_name=vendor,
        document_number=number.group(1) if number else None,
        currency="EUR" if "EUR" in t else None,
        total_amount=_parse_amount(total.group(1)) if total else None,
        iban=iban.group(1) if iban else None,
        line_items=items,
        damage_description=description.group(1).strip() if description else None,
        evidence=evidence,
    )
