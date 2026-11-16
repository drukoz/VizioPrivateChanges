"""Which TV settings are tracking or ads, and what their private value is."""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

# A pattern is a tuple of word patterns that must match consecutive words.
# A word pattern ending in "*" matches any word that starts with the rest;
# any other word pattern must equal the word.
Pattern = Tuple[str, ...]

# (pattern, why). Checked in order; the first match gives the reason.
PRIVACY_KEYWORDS: List[Tuple[Pattern, str]] = [
    (("viewing", "data"), "Viewing Data: ACR / Inscape content recognition"),
    (("smart", "interactiv*"), "Smart Interactivity: ACR (older label)"),
    (("interactiv*",), "interactive content / ACR triggers"),
    (("inscape",), "Inscape: ACR vendor"),
    (("acr",), "automatic content recognition"),
    (("content", "recogn*"), "automatic content recognition"),
    (("interest*",), "interest-based ads"),
    (("advertis*",), "advertising"),
    (("ads",), "advertising"),
    (("ad", "track*"), "ad tracking"),
    (("ad", "personaliz*"), "ad personalization"),
    (("ad", "target*"), "ad targeting"),
    (("personaliz*",), "personalized content and ads"),
    (("tailored",), "tailored recommendations"),
    (("recommend*",), "recommendations"),
    (("do", "not", "track*"), "Do Not Track"),
    (("tracking",), "tracking"),
    (("analytic*",), "analytics"),
    (("telemetr*",), "telemetry"),
    (("usage", "data"), "usage data"),
]

# Labels that limit or block tracking: their private value is "on".
PROTECTIVE: List[Pattern] = [
    ("limit*",), ("do", "not"), ("don", "t"), ("dont",), ("opt", "out"), ("optout",),
    ("block*",), ("restrict*",), ("prevent*",), ("disabl*",),
]

# Items whose value is an identifier: never print the value.
IDENTIFIERS: List[Pattern] = [
    ("serial*",), ("mac",), ("esn",), ("tvad*",), ("uma*",), ("uuid",), ("udid",),
    ("ad", "id"), ("advertis*", "id"), ("device", "id"), ("client", "id"), ("token",),
]

# Menus a settings walk never opens: System Information holds the identifiers,
# and the channel list is long and has nothing to do with privacy.
SKIP_MENUS: List[Pattern] = [("info*",), ("channel*",)]

OFF_VALUES = ["off", "disable", "disabled", "no", "opt out", "opt-out", "none", "never"]
ON_VALUES = ["on", "enable", "enabled", "yes"]

HIDDEN = "<hidden>"


def words(text: Optional[str]) -> List[str]:
    """Lower-case words of a label or cname: "Limit Ad Tracking" -> ["limit", "ad", "tracking"]."""
    return [w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if w]


def _word_matches(word: str, pat: str) -> bool:
    if pat.endswith("*"):
        return word.startswith(pat[:-1])
    return word == pat


def has_pattern(ws: List[str], pattern: Pattern) -> bool:
    """True when the word patterns of `pattern` match consecutive words of `ws`."""
    n = len(pattern)
    for i in range(len(ws) - n + 1):
        if all(_word_matches(ws[i + j], pattern[j]) for j in range(n)):
            return True
    return False


def _any_pattern(item: Any, patterns: List[Pattern]) -> bool:
    """True when any pattern matches the words of the item's cname or name."""
    for pattern in patterns:
        if has_pattern(words(item.cname), pattern) or has_pattern(words(item.name), pattern):
            return True
    return False


def matches(item: Any) -> Optional[str]:
    """The reason the first privacy keyword matches the item, or None."""
    cname_words = words(item.cname)
    name_words = words(item.name)
    for pattern, why in PRIVACY_KEYWORDS:
        if has_pattern(cname_words, pattern) or has_pattern(name_words, pattern):
            return why
    return None


def is_protective(item: Any) -> bool:
    """True when the item limits or blocks tracking, so its private value is On."""
    return _any_pattern(item, PROTECTIVE)


def private_value(item: Any) -> Optional[str]:
    """The item's own choice that makes it private, in TV order, with original text."""
    wanted = ON_VALUES if is_protective(item) else OFF_VALUES
    for element in item.elements:
        if str(element).strip().lower() in wanted:
            return element
    return None


def is_identifier(item: Any) -> bool:
    """True when the item's value is an identifier that must never be printed."""
    return _any_pattern(item, IDENTIFIERS)


def skip_menu(item: Any) -> bool:
    """True when a settings walk should never open this menu."""
    return _any_pattern(item, SKIP_MENUS)


def display_value(item: Any) -> str:
    """The item's value as text, hidden when it is an identifier."""
    if is_identifier(item):
        return HIDDEN
    return str(item.value)
