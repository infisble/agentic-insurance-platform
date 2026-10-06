import random
from datetime import date

from aip.core.policy.service import parse_risk
from aip.core.tariff import price
from aip.seed.generator import generate
from aip.seed.identifiers import iban_sk, is_valid_iban, is_valid_rodne_cislo, rodne_cislo


def test_rodne_cislo_is_checksum_valid():
    rng = random.Random(1)
    for year in (1955, 1980, 2004):
        for female in (False, True):
            rc = rodne_cislo(date(year, 7, 15), female, rng)
            assert is_valid_rodne_cislo(rc), rc


def test_rodne_cislo_encodes_gender_in_month():
    rc = rodne_cislo(date(1990, 3, 9), True, random.Random(1))
    assert rc.startswith("905309/")


def test_invalid_rodne_cislo_detected():
    assert not is_valid_rodne_cislo("900309/1235")


def test_generated_iban_is_valid():
    rng = random.Random(7)
    for _ in range(50):
        assert is_valid_iban(iban_sk(rng))


def test_known_valid_iban():
    # Example IBAN from the National Bank of Slovakia's public documentation format.
    assert is_valid_iban("SK31 1200 0000 1987 4263 7541")


def test_dataset_is_deterministic():
    assert generate(seed=3, n_parties=10) == generate(seed=3, n_parties=10)


def test_dataset_is_consistent():
    ds = generate(seed=42, n_parties=40)
    party_keys = {p["key"] for p in ds.parties}
    policy_keys = {p["key"] for p in ds.policies}
    assert all(p["holder"] in party_keys for p in ds.policies)
    assert all(c["policy"] in policy_keys for c in ds.claims)
    for p in ds.policies:
        # Every generated policy must be priceable on its start date (catches tariff gaps).
        price(parse_risk(p["risk"]), date.fromisoformat(p["start_date"]))
    sk = [p for p in ds.parties if p["country"] == "SK"]
    assert sk and all(is_valid_rodne_cislo(p["national_id"]) for p in sk)
    assert any(c["language"] == "de" for c in ds.claims)
