"""Pseudonymisation before any text reaches a model (ADR 0012).

Two sources of detection:
1. Known values: the policyholder's own data from the core (names, rodné číslo, e-mail,
   phone, street). Exact and high-recall for the person we know about.
2. Pattern recognisers with checksums for structured identifiers anywhere in the text
   (rodné číslo, IBAN, e-mail, phone, licence plate).

Known gap: names of *unknown* people (the other driver, a witness) are not detected yet;
that needs an NER model (Presidio + multilingual transformer, roadmap). The masking eval
measures this gap instead of hiding it.

Pseudonymised data is still personal data (GDPR Recital 26). This reduces exposure; it
does not anonymise.
"""

import re
from collections.abc import Iterable
from typing import Any

from aip.core.identifiers import is_valid_iban, is_valid_rodne_cislo

TOKEN_RE = re.compile(r"<([A-Z_]+)_(\d+)>")

_PATTERNS: list[tuple[str, re.Pattern[str], Any]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), None),
    (
        "IBAN",
        re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,3})?\b"),
        is_valid_iban,
    ),
    ("NATIONAL_ID", re.compile(r"\b\d{6}/\d{3,4}\b"), is_valid_rodne_cislo),
    ("PHONE", re.compile(r"(?<![\w/])(?:\+\d{2,3}[ ]?|0)\d{2,4}(?:[ /-]?\d{2,4}){2,4}\b"), None),
    ("PLATE", re.compile(r"\b[A-Z]{2}[- ]?\d{3}[A-Z]{2}\b"), None),
]


class Masker:
    """Consistent per-case pseudonyms: the same value always maps to the same token within
    one Masker, so the model can still reason about "the same person" across documents."""

    def __init__(self, known: dict[str, Iterable[str | None]] | None = None) -> None:
        self._value_to_token: dict[str, str] = {}
        self._token_to_value: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        self._known: list[tuple[str, str]] = []
        for label, values in (known or {}).items():
            for v in values:
                if v and len(v.strip()) >= 3:
                    self._known.append((label, v.strip()))
        # Longest first, so "Jana Kováčová" is replaced before "Jana".
        self._known.sort(key=lambda kv: len(kv[1]), reverse=True)

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self._token_to_value)

    def _token(self, label: str, value: str) -> str:
        key = f"{label}:{value}"
        token = self._value_to_token.get(key)
        if token is None:
            self._counters[label] = self._counters.get(label, 0) + 1
            token = f"<{label}_{self._counters[label]}>"
            self._value_to_token[key] = token
            self._token_to_value[token] = value
        return token

    def mask(self, text: str) -> str:
        for label, value in self._known:
            pattern = re.compile(rf"(?<!\w){re.escape(value)}(?!\w)", re.IGNORECASE)
            text = pattern.sub(lambda m, lb=label: self._token(lb, m.group(0)), text)
        for label, pattern, validator in _PATTERNS:

            def repl(m: re.Match[str], lb: str = label, check: Any = validator) -> str:
                value = m.group(0)
                if TOKEN_RE.fullmatch(value) or (check is not None and not check(value)):
                    return value
                return self._token(lb, value)

            text = pattern.sub(repl, text)
        return text

    def unmask(self, value: Any) -> Any:
        """Replace tokens with original values, recursively through dicts and lists."""
        if isinstance(value, str):
            return TOKEN_RE.sub(lambda m: self._token_to_value.get(m.group(0), m.group(0)), value)
        if isinstance(value, dict):
            return {k: self.unmask(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.unmask(v) for v in value]
        return value
