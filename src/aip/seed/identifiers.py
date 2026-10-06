"""Synthetic but checksum-valid identifiers, so PII-masking tests see realistic shapes."""

import random
from datetime import date

from aip.core.identifiers import is_valid_iban, is_valid_rodne_cislo

__all__ = ["iban_sk", "is_valid_iban", "is_valid_rodne_cislo", "rodne_cislo"]


def rodne_cislo(birth: date, female: bool, rng: random.Random) -> str:
    """Slovak/Czech birth number for people born 1954 or later: YYMMDD/SSSC.

    Women have 50 added to the month. The 10-digit number must be divisible by 11.
    For the first nine digits N, the check digit is N mod 11 (because 10 ≡ -1 mod 11);
    a remainder of 10 has no valid digit, so that serial is skipped.
    """
    if birth.year < 1954:
        raise ValueError("10-digit rodné číslo exists only for births from 1954")
    month = birth.month + (50 if female else 0)
    prefix = f"{birth.year % 100:02d}{month:02d}{birth.day:02d}"
    while True:
        serial = rng.randint(0, 999)
        check = int(f"{prefix}{serial:03d}") % 11
        if check != 10:
            return f"{prefix}/{serial:03d}{check}"


def make_iban(country: str, rng: random.Random) -> str:
    """Checksum-valid IBAN for SK (4-digit bank + 16-digit account) or AT (5 + 11)."""
    if country == "SK":
        bank = rng.choice(["0200", "0900", "1100", "7500", "5600"])
        bban = f"{bank}{rng.randint(0, 10**16 - 1):016d}"
    elif country == "AT":
        bank = rng.choice(["12000", "20111", "32000", "14000", "60000"])
        bban = f"{bank}{rng.randint(0, 10**11 - 1):011d}"
    else:
        raise ValueError(country)
    letters = "".join(str(int(ch, 36)) for ch in country)
    check = 98 - int(f"{bban}{letters}00") % 97
    return f"{country}{check:02d}{bban}"


def iban_sk(rng: random.Random) -> str:
    """Slovak IBAN: SKkk + 4-digit bank code + 16-digit account, with valid ISO 13616 check."""
    bank = rng.choice(["0200", "0900", "1100", "7500", "5600"])
    bban = f"{bank}{rng.randint(0, 10**16 - 1):016d}"
    # Move "SK00" to the end, letters to numbers (S=28, K=20), mod 97.
    numeric = int(f"{bban}2820" + "00")
    check = 98 - numeric % 97
    return f"SK{check:02d}{bban}"
