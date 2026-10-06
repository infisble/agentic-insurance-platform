"""Synthetic claim documents (PDF) with ground-truth labels for the golden dataset.

Each seeded claim gets one document whose type depends on the peril:
repair estimate (motor property), invoice (household repairs) or claim form (theft, injury,
some household claims). Slovak and German, two layout variants each, local number and date
formats. A small share of documents carries deliberate anomalies (policy number typo,
total ≠ sum of items, event date differing from the claim) so validators and agents have
something real to catch.

Everything is fictional. Labels record exactly what is *written* in the document.
"""

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from faker import Faker
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from aip.core.products import Peril
from aip.seed.identifiers import make_iban

FONT_DIR = Path(__file__).resolve().parent / "fonts"  # DejaVu, see LICENSE-DejaVu.txt

VENDORS = {
    "sk": {
        "repair": ["AutoServis Novák s.r.o.", "Karosáreň Tatra s.r.o.", "AUTO-OPRAVY Kováč"],
        "household": ["Inštalatérstvo Horváth", "STAVBY Mráz s.r.o.", "Strechy Slovakia s.r.o."],
        "medical": ["Poliklinika Ružinov", "Nemocnica sv. Michala"],
    },
    "de": {
        "repair": ["Autohaus Gruber GmbH", "Karosserie Huber KG", "KFZ-Werkstatt Bauer"],
        "household": ["Installateur Wimmer GmbH", "Bau & Dach Steiner", "Hofer Haustechnik"],
        "medical": ["Ordination Dr. Mayer", "Klinik Donaustadt"],
    },
}

ITEMS = {
    Peril.MOTOR_TP_PROPERTY: {
        "sk": ["Výmena predného nárazníka", "Lakovanie dverí", "Oprava blatníka", "Práca technika"],
        "de": [
            "Stoßstange vorne ersetzen",
            "Lackierung Tür",
            "Kotflügel instand setzen",
            "Arbeitszeit",
        ],
    },
    Peril.MOTOR_TP_INJURY: {
        "sk": ["Ošetrenie na pohotovosti", "RTG vyšetrenie", "Rehabilitácia", "Lieky"],
        "de": ["Notfallbehandlung", "Röntgenuntersuchung", "Physiotherapie", "Medikamente"],
    },
    Peril.WATER_LEAK: {
        "sk": ["Oprava potrubia", "Vysúšanie podlahy", "Výmena laminátovej podlahy", "Maľovanie"],
        "de": ["Rohrreparatur", "Bautrocknung", "Laminatboden erneuern", "Malerarbeiten"],
    },
    Peril.STORM: {
        "sk": ["Oprava strešnej krytiny", "Výmena odkvapu", "Lešenie", "Práca"],
        "de": ["Dacheindeckung reparieren", "Dachrinne ersetzen", "Gerüst", "Arbeitszeit"],
    },
    Peril.FIRE: {
        "sk": ["Kuchynská linka", "Sporák", "Odstránenie sadzí", "Maľovanie"],
        "de": ["Küchenzeile", "Herd", "Rußentfernung", "Malerarbeiten"],
    },
    Peril.FLOOD: {
        "sk": ["Odčerpanie vody", "Vysúšanie pivnice", "Likvidácia poškodených vecí"],
        "de": ["Wasser abpumpen", "Kellertrocknung", "Entsorgung beschädigter Gegenstände"],
    },
    Peril.THEFT: {
        "sk": ["Notebook", "Šperky", "Fotoaparát", "Hotovosť"],
        "de": ["Laptop", "Schmuck", "Kamera", "Bargeld"],
    },
}

TEXT = {
    "sk": {
        "invoice": ("FAKTÚRA č. {n}", "Faktúra – daňový doklad", "Číslo faktúry: {n}"),
        "repair_estimate": ("ROZPOČET OPRAVY č. {n}", "Cenová ponuka opravy", "Číslo ponuky: {n}"),
        "claim_form": ("HLÁSENIE POISTNEJ UDALOSTI", "Oznámenie škody", "Číslo hlásenia: {n}"),
        "issue_date": "Dátum vystavenia",
        "report_date": "Dátum hlásenia",
        "customer": "Odberateľ",
        "claimant": "Poistník",
        "policy": ("Číslo poistnej zmluvy", "Poistná zmluva č."),
        "event_date": ("Dátum poistnej udalosti", "Dátum vzniku škody"),
        "items": "Položky",
        "total": ("Spolu s DPH", "Celková suma na úhradu"),
        "iban": ("IBAN", "Číslo účtu (IBAN)"),
        "payout_iban": "Plnenie prosím poukázať na účet",
        "description": "Popis udalosti",
        "third_party": "Poškodený",
        "plate": "EČV poškodeného vozidla",
        "national_id": "Rodné číslo",
        "contact": "Kontakt",
        "police": "Číslo záznamu polície",
        "signature": "Podpis",
    },
    "de": {
        "invoice": ("RECHNUNG Nr. {n}", "Rechnung", "Rechnungsnummer: {n}"),
        "repair_estimate": (
            "KOSTENVORANSCHLAG Nr. {n}",
            "Kostenvoranschlag Reparatur",
            "Angebotsnummer: {n}",
        ),
        "claim_form": ("SCHADENMELDUNG", "Schadensanzeige", "Meldungsnummer: {n}"),
        "issue_date": "Rechnungsdatum",
        "report_date": "Datum der Meldung",
        "customer": "Kunde",
        "claimant": "Versicherungsnehmer",
        "policy": ("Polizzennummer", "Versicherungsvertrag Nr."),
        "event_date": ("Schadendatum", "Datum des Schadenereignisses"),
        "items": "Positionen",
        "total": ("Gesamtbetrag inkl. USt", "Zu zahlender Betrag"),
        "iban": ("IBAN", "Bankverbindung (IBAN)"),
        "payout_iban": "Bitte überweisen Sie die Leistung auf",
        "description": "Schadenhergang",
        "third_party": "Geschädigter",
        "plate": "Kennzeichen des geschädigten Fahrzeugs",
        "national_id": "Geburtsnummer",
        "contact": "Kontakt",
        "police": "Polizeiliches Aktenzeichen",
        "signature": "Unterschrift",
    },
}


def fmt_amount(value: Decimal, lang: str) -> str:
    whole, frac = f"{value:.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    sep = " " if lang == "sk" else "."
    return f"{sep.join(groups)},{frac}"


def fmt_date(d: date, lang: str, variant: int) -> str:
    if lang == "sk" and variant == 1:
        return f"{d.day}. {d.month}. {d.year}"
    return d.strftime("%d.%m.%Y")


def split_amount(total: Decimal, n: int, rng: random.Random) -> list[Decimal]:
    cents = int(total * 100)
    if n == 1 or cents < n * 100:
        return [total]
    cuts = sorted(rng.sample(range(100, cents - 100), n - 1))
    parts = [b - a for a, b in zip([0, *cuts], [*cuts, cents], strict=True)]
    return [Decimal(p) / 100 for p in parts]


def doc_type_for(peril: Peril, rng: random.Random) -> str:
    if peril is Peril.MOTOR_TP_PROPERTY:
        return "repair_estimate"
    if peril in (Peril.THEFT, Peril.MOTOR_TP_INJURY):
        return "claim_form"
    return "claim_form" if rng.random() < 0.3 else "invoice"


MONTHS = {
    "sk": [
        "januára",
        "februára",
        "marca",
        "apríla",
        "mája",
        "júna",
        "júla",
        "augusta",
        "septembra",
        "októbra",
        "novembra",
        "decembra",
    ],
    "de": [
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
}


def email_lines(
    lang: str,
    sent: date,
    policy: str,
    event: date,
    description: str,
    items: list[tuple[str, Decimal]],
    total: Decimal,
    iban: str,
    holder: str,
    phone: str,
) -> list[tuple[str, str]]:
    when = f"{event.day}. {MONTHS[lang][event.month - 1]} {event.year}"
    sent_on = sent.strftime("%d.%m.%Y")
    if lang == "sk":
        listed = ", ".join(f"{d.lower()} za {fmt_amount(a, lang)} €" for d, a in items)
        header = [f"Od: {holder}", f"Dátum: {sent_on}", "Predmet: škoda"]
        body = [
            "Dobrý deň,",
            f"v zmysle mojej poistky {policy} Vám oznamujem škodu. Stalo sa to {when}. "
            f"{description}",
            f"Vzniknuté náklady: {listed}. Celkovo teda žiadam {fmt_amount(total, lang)} €.",
            f"Peniaze mi prosím pošlite na účet {iban}. V prípade otázok volajte na {phone}.",
            "Ďakujem a pekný deň",
            holder,
        ]
    else:
        listed = ", ".join(f"{d} um {fmt_amount(a, lang)} €" for d, a in items)
        header = [f"Von: {holder}", f"Datum: {sent_on}", "Betreff: Schaden"]
        body = [
            "Sehr geehrte Damen und Herren,",
            f"ich melde einen Schaden zu meinem Vertrag {policy}. Passiert ist es am {when}. "
            f"{description}",
            f"Die Kosten: {listed}. Insgesamt fordere ich daher {fmt_amount(total, lang)} €.",
            f"Bitte überweisen Sie das Geld auf mein Konto {iban}. Rückfragen gerne unter {phone}.",
            "Mit freundlichen Grüßen",
            holder,
        ]
    return [*[("", h) for h in header], ("gap", ""), *[("", b) for b in body]]


@dataclass
class GeneratedDocument:
    claim_key: str
    filename: str
    pdf: bytes
    label: dict[str, Any]
    anomalies: list[str] = field(default_factory=list)


def _pdf(lines: list[tuple[str, str]]) -> bytes:
    pdf = FPDF()
    pdf.set_creation_date(datetime(2026, 1, 1))
    pdf.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    for style, text in lines:
        if style == "h1":
            pdf.set_font("DejaVu", "B", 15)
            pdf.multi_cell(0, 9, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)
        elif style == "b":
            pdf.set_font("DejaVu", "B", 10)
            pdf.multi_cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif style == "gap":
            pdf.ln(4)
        else:
            pdf.set_font("DejaVu", "", 10)
            pdf.multi_cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())


def generate_document(
    claim: dict[str, Any],
    party: dict[str, Any],
    policy_number: str,
    rng: random.Random,
    faker: Faker,
) -> GeneratedDocument:
    lang = claim["language"]
    t = TEXT[lang]
    peril = Peril(claim["peril"])
    variant = rng.randint(0, 1)
    doc_type = doc_type_for(peril, rng)
    event = date.fromisoformat(claim["event_date"])
    reported = date.fromisoformat(claim["reported_date"])
    issue = min(reported + timedelta(days=rng.randint(0, 5)), date(2026, 10, 1))
    total = Decimal(claim["claimed_amount"])
    holder = f"{party['first_name']} {party['last_name']}"
    number = f"{rng.randint(2026000, 2026999)}"
    country = "SK" if lang == "sk" else "AT"
    anomalies: list[str] = []

    items_names = ITEMS[peril][lang]
    n_items = min(len(items_names), rng.randint(1, 3) if total < 300 else rng.randint(2, 4))
    amounts = split_amount(total, n_items, rng)
    items = list(zip(rng.sample(items_names, len(amounts)), amounts, strict=True))

    written_policy = policy_number
    if rng.random() < 0.08:
        pos = rng.randrange(len(policy_number) - 4, len(policy_number))
        swap = "7" if policy_number[pos] != "7" else "3"
        written_policy = policy_number[:pos] + swap + policy_number[pos + 1 :]
        anomalies.append("policy_number_mismatch")
    written_event = event
    if rng.random() < 0.06:
        written_event = event + timedelta(days=rng.choice([-9, -4, 3, 6]))
        anomalies.append("event_date_differs")
    if rng.random() < 0.06 and len(items) > 1:
        desc, amt = items[-1]
        items[-1] = (desc, amt - Decimal(rng.choice([50, 100, 150])))
        anomalies.append("total_mismatch")

    pii: list[str] = [holder]
    lines: list[tuple[str, str]] = []
    vendor = iban = None
    if doc_type in ("invoice", "repair_estimate"):
        kind = "repair" if doc_type == "repair_estimate" else "household"
        vendor = rng.choice(VENDORS[lang][kind])
        iban = make_iban(country, rng)
        title = t[doc_type][variant] if variant == 0 else t[doc_type][1]
        lines += [
            ("b", vendor),
            ("", f"{faker.street_address()}, {faker.postcode()} {faker.city()}"),
            ("gap", ""),
            ("h1", title.format(n=number)),
        ]
        if variant == 1:
            lines.append(("", t[doc_type][2].format(n=number)))
        lines += [
            ("", f"{t['issue_date']}: {fmt_date(issue, lang, variant)}"),
            ("gap", ""),
            ("b", f"{t['customer']}:"),
            ("", holder),
            ("", party["street"] or ""),
            ("", f"{party['postal_code']} {party['city']}"),
            ("gap", ""),
            ("", f"{t['policy'][variant]}: {written_policy}"),
            ("", f"{t['event_date'][variant]}: {fmt_date(written_event, lang, variant)}"),
        ]
        pii += [party["street"] or ""]
        if doc_type == "repair_estimate":
            third = f"{faker.first_name()} {faker.last_name()}"
            plate = f"{rng.choice(['BA', 'KE', 'ZA', 'NR', 'TT'])}{rng.randint(100, 999)}" + (
                f"{chr(65 + rng.randint(0, 25))}{chr(65 + rng.randint(0, 25))}"
            )
            lines += [("", f"{t['third_party']}: {third}"), ("", f"{t['plate']}: {plate}")]
            pii += [third, plate]
        lines += [("gap", ""), ("b", t["items"])]
        for desc, amt in items:
            lines.append(("", f"{desc} ............ {fmt_amount(amt, lang)} EUR"))
        lines += [
            ("gap", ""),
            ("b", f"{t['total'][variant]}: {fmt_amount(total, lang)} EUR"),
            ("", f"{t['iban'][variant]}: {iban}"),
        ]
    elif rng.random() < 0.6:
        # Hard variant: a free-text e-mail from the customer. No field labels, dates in words,
        # amounts inside sentences. Regexes fail here; this is where an LLM has to earn its cost.
        variant = 2
        iban = party["iban"]
        number = None
        pii += [party["phone"] or "", iban]
        lines += email_lines(
            lang,
            issue,
            written_policy,
            written_event,
            claim["description"],
            items,
            total,
            iban,
            holder,
            party["phone"] or "",
        )
    else:
        iban = party["iban"]
        title = t["claim_form"][variant]
        lines += [("h1", title), ("", t["claim_form"][2].format(n=number))]
        lines += [
            ("", f"{t['report_date']}: {fmt_date(issue, lang, variant)}"),
            ("gap", ""),
            ("b", f"{t['claimant']}: {holder}"),
            ("", f"{party['street']}, {party['postal_code']} {party['city']}"),
        ]
        pii += [party["street"] or "", party["email"] or "", party["phone"] or "", iban]
        if party.get("national_id"):
            lines.append(("", f"{t['national_id']}: {party['national_id']}"))
            pii.append(party["national_id"])
        lines += [
            ("", f"{t['contact']}: {party['email']}, {party['phone']}"),
            ("gap", ""),
            ("", f"{t['policy'][variant]}: {written_policy}"),
            ("", f"{t['event_date'][variant]}: {fmt_date(written_event, lang, variant)}"),
            ("gap", ""),
            ("b", f"{t['description']}:"),
            ("", claim["description"]),
        ]
        if peril is Peril.THEFT:
            lines.append(("", f"{t['police']}: ČVS:{rng.randint(100, 999)}/2026"))
        lines += [("gap", ""), ("b", t["items"])]
        for desc, amt in items:
            lines.append(("", f"{desc} ............ {fmt_amount(amt, lang)} EUR"))
        lines += [
            ("gap", ""),
            ("b", f"{t['total'][variant]}: {fmt_amount(total, lang)} EUR"),
            ("", f"{t['payout_iban']}: {iban}"),
            ("gap", ""),
            ("", f"{t['signature']}: {holder}"),
        ]

    label = {
        "claim_key": claim["key"],
        "doc_type": doc_type,
        "language": lang,
        "variant": variant,
        "fields": {
            "policy_number": written_policy,
            "claimant_name": holder,
            "event_date": written_event.isoformat(),
            "issue_date": issue.isoformat(),
            "vendor_name": vendor,
            "document_number": number,
            "currency": "EUR",
            "total_amount": str(total),
            "iban": iban,
            "line_items": [{"description": d, "amount": str(a)} for d, a in items],
        },
        "pii": [p for p in pii if p],
        "anomalies": anomalies,
    }
    filename = f"{claim['key']}.pdf"
    label["file"] = filename
    return GeneratedDocument(claim["key"], filename, _pdf(lines), label, anomalies)
