"""Rule-based language and dialect detection (heuristic v0).

Language is decided by script: any Arabic-range character makes the request
Arabic (Arabic dominates for sovereignty and handling, even in mixed text);
otherwise Latin letters make it English; text with neither is ``UNKNOWN`` and
falls through to the catch-all route rather than being assumed English.

The dialect signal is a small, transparent Gulf-marker lexicon. It is recorded
for observability but is deliberately **not** a routing dimension in this
milestone: dialect-aware routing needs measured capability data (mizan-evals M2).
Absence of a Gulf marker yields a labelled ``msa-default``, not a positive MSA
detection - see the README limitations.
"""

from __future__ import annotations

import re

from masar.domain import Dialect, LanguageClass

# Arabic (U+0600-U+06FF) plus Arabic Supplement (U+0750-U+077F).
_ARABIC = re.compile(r"[؀-ۿݐ-ݿ]")
_LATIN = re.compile(r"[A-Za-z]")

# Distinctive Gulf-dialect markers, matched as whole words (word boundaries) to
# avoid firing on common MSA words that merely contain a marker as a substring
# (e.g. "مو" inside "موعد", "ابي" inside "كتابي"). This is precision-first: it
# misses clitic-prefixed forms ("والحين") and is a soft signal only. Ambiguous
# short tokens (e.g. "مو", "ابي") are intentionally excluded.
_GULF_MARKERS = (
    "وش",
    "شلون",
    "وين",
    "أبغى",
    "ابغى",
    "شفيك",
    "كيفك",
    "الحين",
    "دحين",
    "شنو",
    "وياك",
    "زين",
)
_GULF_MARKER_RES = tuple((marker, re.compile(rf"\b{marker}\b")) for marker in _GULF_MARKERS)


def _detect_dialect(text: str) -> tuple[Dialect, list[str]]:
    hits = [marker for marker, pattern in _GULF_MARKER_RES if pattern.search(text)]
    if hits:
        return Dialect.GULF, [f"dialect:gulf-marker:{marker}" for marker in hits]
    return Dialect.MSA, ["dialect:msa-default"]


def classify_language(text: str) -> tuple[LanguageClass, Dialect | None, list[str]]:
    """Classify language and (for Arabic) a soft dialect signal.

    Returns the language class, an optional dialect signal (only for Arabic), and
    the signals that fired.
    """
    if _ARABIC.search(text):
        dialect, dialect_signals = _detect_dialect(text)
        return LanguageClass.AR, dialect, ["lang:arabic-script", *dialect_signals]
    if _LATIN.search(text):
        return LanguageClass.EN, None, ["lang:latin-script"]
    return LanguageClass.UNKNOWN, None, ["lang:no-letters"]
