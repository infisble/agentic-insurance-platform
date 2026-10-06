"""Deterministic synthetic dataset: parties, policies, claims (SK and AT customers).

Same seed → same dataset, so tests and evals can rely on it. Everything is fictional.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from faker import Faker

from aip.core.products import Peril, ProductCode, Region
from aip.core.tariff import PropertyType
from aip.seed.identifiers import make_iban, rodne_cislo

# Realistic claim descriptions per peril, in the customer's language.
DESCRIPTIONS: dict[Peril, dict[str, list[str]]] = {
    Peril.MOTOR_TP_PROPERTY: {
        "sk": [
            "Pri cúvaní na parkovisku som narazil do zaparkovaného vozidla, "
            "poškodený predný nárazník.",
            "Na križovatke som nedal prednosť a poškodil som bočné dvere druhého auta.",
        ],
        "de": [
            "Beim Ausparken habe ich ein stehendes Fahrzeug touchiert, Stoßstange beschädigt.",
            "An der Kreuzung habe ich die Vorfahrt missachtet, "
            "Seitentür des anderen Autos verbeult.",
        ],
    },
    Peril.MOTOR_TP_INJURY: {
        "sk": ["Pri zrážke bol zranený spolujazdec druhého vozidla, ošetrený v nemocnici."],
        "de": ["Bei dem Unfall wurde der Beifahrer des anderen Fahrzeugs verletzt."],
    },
    Peril.FIRE: {
        "sk": ["Požiar v kuchyni od sporáka, zničená kuchynská linka a spotrebiče."],
        "de": ["Küchenbrand durch den Herd, Küchenzeile und Geräte zerstört."],
    },
    Peril.WATER_LEAK: {
        "sk": [
            "Prasknuté potrubie v kúpeľni, vytopená podlaha a poškodený nábytok.",
            "Susedia zhora nás vytopili, poškodený strop a koberec v obývačke.",
        ],
        "de": ["Rohrbruch im Bad, Boden und Möbel durch Wasser beschädigt."],
    },
    Peril.FLOOD: {
        "sk": ["Po prívalových dažďoch zaplavená pivnica, zničené uskladnené veci."],
        "de": ["Nach Starkregen Keller überflutet, gelagerte Gegenstände zerstört."],
    },
    Peril.STORM: {
        "sk": ["Víchrica strhla časť strechy, zatieklo do spálne."],
        "de": ["Sturm hat Teile des Daches abgedeckt, Wasser im Schlafzimmer."],
    },
    Peril.THEFT: {
        "sk": ["Vlámanie do bytu počas dovolenky, ukradnutý notebook a šperky."],
        "de": ["Einbruch während des Urlaubs, Laptop und Schmuck gestohlen."],
    },
}

MOTOR_PERILS = [Peril.MOTOR_TP_PROPERTY] * 4 + [Peril.MOTOR_TP_INJURY]
HOUSEHOLD_PERILS = (
    [Peril.WATER_LEAK] * 4
    + [Peril.STORM] * 2
    + [
        Peril.THEFT,
        Peril.FIRE,
        Peril.FLOOD,
    ]
)
CLAIM_AMOUNTS: dict[Peril, tuple[int, int]] = {
    Peril.MOTOR_TP_PROPERTY: (300, 8000),
    Peril.MOTOR_TP_INJURY: (2000, 40000),
    Peril.FIRE: (1500, 30000),
    Peril.WATER_LEAK: (150, 6000),
    Peril.FLOOD: (500, 15000),
    Peril.STORM: (400, 9000),
    Peril.THEFT: (200, 5000),
}


@dataclass
class Dataset:
    parties: list[dict[str, Any]] = field(default_factory=list)
    policies: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)


def generate(seed: int = 42, n_parties: int = 40, today: date = date(2026, 10, 1)) -> Dataset:
    rng = random.Random(seed)
    fakers = {"sk": Faker("sk_SK"), "de": Faker("de_AT")}
    for f in fakers.values():
        f.seed_instance(seed)

    ds = Dataset()
    for i in range(n_parties):
        lang = "sk" if rng.random() < 0.7 else "de"
        fk = fakers[lang]
        female = rng.random() < 0.5
        birth = date(rng.randint(1955, 2005), rng.randint(1, 12), rng.randint(1, 28))
        party_key = f"P{i:03d}"
        ds.parties.append(
            {
                "key": party_key,
                "kind": "person",
                "first_name": fk.first_name_female() if female else fk.first_name_male(),
                "last_name": fk.last_name_female() if female else fk.last_name_male(),
                "birth_date": birth.isoformat(),
                "national_id": rodne_cislo(birth, female, rng) if lang == "sk" else None,
                "email": fk.free_email(),
                "phone": fk.phone_number(),
                "street": fk.street_address(),
                "city": fk.city(),
                "postal_code": fk.postcode(),
                "country": "SK" if lang == "sk" else "AT",
                "language": lang,
                "iban": make_iban("SK" if lang == "sk" else "AT", rng),
            }
        )
        age = today.year - birth.year

        for _ in range(rng.choice([1, 1, 2])):
            product = rng.choice([ProductCode.MOTOR_TPL, ProductCode.HOUSEHOLD])
            start = today - timedelta(days=rng.randint(30, 330))
            region = rng.choice(list(Region))
            if product is ProductCode.MOTOR_TPL:
                risk: dict[str, Any] = {
                    "product": product.value,
                    "engine_kw": rng.choice([44, 55, 66, 77, 85, 96, 110, 132, 160, 200]),
                    "holder_age": age,
                    "region": region.value,
                    "bonus_malus_level": rng.choice([-1, 0, 1, 2, 3, 4, 5, 6, 8, 10]),
                }
            else:
                risk = {
                    "product": product.value,
                    "sum_insured": str(rng.choice([15000, 30000, 50000, 80000, 120000])),
                    "property_type": rng.choice(list(PropertyType)).value,
                    "region": region.value,
                    "flood_zone": rng.choices([1, 2, 3, 4], weights=[60, 25, 10, 5])[0],
                    "deductible": str(rng.choice([50, 100, 200])),
                }
            policy_key = f"{party_key}-POL{len(ds.policies):03d}"
            prefix = "PZP" if product is ProductCode.MOTOR_TPL else "DOM"
            ds.policies.append(
                {
                    "key": policy_key,
                    "holder": party_key,
                    "number": f"{prefix}-{start.year}-{rng.getrandbits(32):08X}",
                    "start_date": start.isoformat(),
                    "risk": risk,
                }
            )

            if rng.random() < 0.6:
                perils = MOTOR_PERILS if product is ProductCode.MOTOR_TPL else HOUSEHOLD_PERILS
                peril = rng.choice(perils)
                event = start + timedelta(days=rng.randint(1, max(2, (today - start).days - 1)))
                # Mostly prompt reports; some late ones exercise the REFER rule.
                delay = rng.choice([0, 1, 2, 3, 5, 7, 10]) if rng.random() < 0.85 else 45
                reported = min(today, event + timedelta(days=delay))
                low, high = CLAIM_AMOUNTS[peril]
                if product is ProductCode.HOUSEHOLD and rng.random() < 0.15:
                    low, high = 20, 90  # edge case: at or below the deductible
                if rng.random() < 0.08:
                    # edge case: event before the policy started (e.g. pre-existing damage)
                    event = start - timedelta(days=rng.randint(3, 40))
                    reported = event + timedelta(days=rng.randint(1, 10))
                ds.claims.append(
                    {
                        "key": f"{policy_key}-CLM",
                        "policy": policy_key,
                        "peril": peril.value,
                        "event_date": event.isoformat(),
                        "reported_date": reported.isoformat(),
                        "claimed_amount": str(Decimal(rng.randint(low * 100, high * 100)) / 100),
                        "description": rng.choice(DESCRIPTIONS[peril][lang]),
                        "channel": rng.choice(["portal", "portal", "email", "phone"]),
                        "language": lang,
                    }
                )
    return ds
