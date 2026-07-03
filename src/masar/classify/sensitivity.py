"""Rule-based sensitivity detection (heuristic v0).

A request is classed ``SOVEREIGN`` when any high-precision PII, credential, or
explicit-confidential signal fires, and ``STANDARD`` otherwise. The design
choice here is precision over recall: transparent regular expressions with a
Luhn check on card candidates, so the router under-flags rather than misroutes
ordinary traffic. Every rule that fires is reported as a signal so a decision
can be explained. This is not a named-entity model — see the README limitations.
"""

from __future__ import annotations

import re

from masar.domain import SensitivityClass

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_INTL = re.compile(r"\+\d{7,15}\b")
_PHONE_KSA = re.compile(r"\b05\d{8}\b")
_NATIONAL_ID = re.compile(r"\b[12]\d{9}\b")  # Saudi national id / iqama shape
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_CARD_CANDIDATE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")

_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")
_AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")
_SECRET_ASSIGN = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*\S+"
)

_CONFIDENTIAL_EN = re.compile(
    r"(?i)\b(?:confidential|classified|internal[\s-]only|proprietary|do not share|nda)\b"
)
_CONFIDENTIAL_AR = re.compile(r"(?:سرّي|سري|سرية|محظور|لا تشارك)")


def _luhn_ok(digits: str) -> bool:
    """True when ``digits`` (13-19 chars) passes the Luhn checksum."""
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _has_card(text: str) -> bool:
    for match in _CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if _luhn_ok(digits):
            return True
    return False


def classify_sensitivity(text: str) -> tuple[SensitivityClass, list[str]]:
    """Classify data sensitivity, returning the class and the signals that fired."""
    signals: list[str] = []

    if _EMAIL.search(text):
        signals.append("pii:email")
    if _PHONE_INTL.search(text) or _PHONE_KSA.search(text):
        signals.append("pii:phone")
    if _has_card(text):
        signals.append("pii:card")
    if _IBAN.search(text):
        signals.append("pii:iban")
    if _NATIONAL_ID.search(text):
        signals.append("pii:national-id")

    if _OPENAI_KEY.search(text):
        signals.append("credential:api-key")
    if _AWS_KEY.search(text):
        signals.append("credential:aws-key")
    if _JWT.search(text):
        signals.append("credential:jwt")
    if _PRIVATE_KEY.search(text):
        signals.append("credential:private-key")
    if _SECRET_ASSIGN.search(text):
        signals.append("credential:secret-assignment")

    if _CONFIDENTIAL_EN.search(text):
        signals.append("confidential:keyword-en")
    if _CONFIDENTIAL_AR.search(text):
        signals.append("confidential:keyword-ar")

    if signals:
        return SensitivityClass.SOVEREIGN, signals
    return SensitivityClass.STANDARD, []
