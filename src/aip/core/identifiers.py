"""Checksum validation for identifiers. Used by PII recognisers and extraction validators."""


def is_valid_rodne_cislo(value: str) -> bool:
    """Slovak/Czech birth number (10 digits, from 1954): YYMMDD/SSSC, divisible by 11."""
    digits = value.replace("/", "")
    if len(digits) != 10 or not digits.isdigit():
        return False
    month = int(digits[2:4])
    if month > 50:
        month -= 50
    if not 1 <= month <= 12:
        return False
    return int(digits) % 11 == 0


def is_valid_iban(value: str) -> bool:
    """ISO 13616 mod-97 check."""
    s = value.replace(" ", "").upper()
    if len(s) < 15 or not s[:2].isalpha() or not s[2:4].isdigit() or not s.isalnum():
        return False
    rearranged = s[4:] + s[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1
