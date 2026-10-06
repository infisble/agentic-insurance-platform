from aip.llm.masking import Masker

TEXT = (
    "Poistník: Jana Kováčová, Hlavná 12, 811 01 Bratislava\n"
    "Rodné číslo: 865412/1234\n"
    "Kontakt: jana.k@example.sk, +421 905 123 456\n"
    "IBAN: SK3112000000198742637541\n"
    "EČV: BA123XY\n"
    "Číslo poistnej zmluvy: DOM-2026-1A2B3C4D\n"
    "Spolu s DPH: 1 234,50 EUR"
)


def masker() -> Masker:
    return Masker({"PERSON": ["Jana Kováčová", "Kováčová"], "ADDRESS": ["Hlavná 12"]})


def test_masks_known_and_pattern_pii():
    m = masker()
    out = m.mask(TEXT)
    for secret in (
        "Jana Kováčová",
        "Hlavná 12",
        "865412/1234",
        "jana.k@example.sk",
        "+421 905 123 456",
        "SK3112000000198742637541",
        "BA123XY",
    ):
        assert secret not in out, secret
    assert "<PERSON_1>" in out and "<IBAN_1>" in out and "<NATIONAL_ID_1>" in out


def test_keeps_business_data():
    out = masker().mask(TEXT)
    assert "DOM-2026-1A2B3C4D" in out  # policy numbers are needed for matching
    assert "1 234,50 EUR" in out


def test_invalid_checksums_are_not_treated_as_identifiers():
    out = Masker().mask("Faktúra 900309/1235, účet SK0012000000198742637541")
    assert "900309/1235" in out  # fails mod-11, so it is not a rodné číslo
    assert "SK0012000000198742637541" in out  # fails mod-97


def test_tokens_are_consistent_and_reversible():
    m = masker()
    a = m.mask("Jana Kováčová volala.")
    b = m.mask("Opäť volala Jana Kováčová.")
    assert a.split()[0] == b.split()[-1].rstrip(".")
    assert m.unmask({"name": a, "items": [b]}) == {
        "name": "Jana Kováčová volala.",
        "items": ["Opäť volala Jana Kováčová."],
    }


def test_masking_is_idempotent_on_tokens():
    m = masker()
    once = m.mask(TEXT)
    assert m.mask(once) == once


def test_unknown_token_is_left_alone():
    assert Masker().unmask("<PERSON_9>") == "<PERSON_9>"
