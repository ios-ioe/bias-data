"""PII detection for submission text."""

import logging
import re
from typing import TypedDict

logger = logging.getLogger(__name__)

NEPALI_FIRST_NAMES: list[str] = [
    "Ram",
    "Shyam",
    "Hari",
    "Gopal",
    "Krishna",
    "Sita",
    "Gita",
    "Radha",
    "Sarita",
    "Sunita",
    "Anita",
    "Binita",
    "Prakash",
    "Deepak",
    "Dipak",
    "Raju",
    "Rajesh",
    "Suresh",
    "Ramesh",
    "Mahesh",
    "Ganesh",
    "Binod",
    "Manoj",
    "Santosh",
    "Anil",
    "Sunil",
    "Sushil",
    "Kamal",
    "Bimala",
    "Bishal",
    "Suman",
    "Sagar",
]

# NOTE: surnames (Shrestha, Sharma, Gurung, Tamang, etc.) were intentionally
# removed from this PII list. In Nepali text, surnames are strong caste/
# ethnicity markers, and "caste" is one of this tool's own 10 target bias
# categories — flagging every sentence containing a common surname as PII
# nudged annotators toward a friction dialog on exactly the caste-bias data
# the competition needs. Surnames alone are also weak PII signal compared to
# a phone number or email. If you need surname-level PII detection, pair it
# with a nearby phone number/address match instead of a bare name hit.

DEVANAGARI_NAMES: set[str] = {
    "राम",
    "श्याम",
    "हरि",
    "गोपाल",
    "कृष्ण",
    "सीता",
    "गीता",
    "राधा",
    "सरिता",
    "सुनिता",
    "अनिता",
    "बिनिता",
    "प्रकाश",
    "दिपक",
    "दीपक",
    "राजु",
    "राजेश",
    "सुरेश",
    "रमेश",
    "महेश",
    "गणेश",
    "बिनोद",
    "मनोज",
    "सन्तोष",
    "अनिल",
    "सुनिल",
    "सुशील",
    "कमल",
    "बिमला",
    "सरस्वती",
    "लक्ष्मी",
    "पार्वती",
    "मीना",
    "रीता",
    "पूजा",
    "निर्मला",
    "सुमन",
    "प्रदीप",
    "अशोक",
    "अर्जुन",
    "बिष्णु",
}
# Surnames (श्रेष्ठ, शर्मा, गुरुङ, तामाङ, etc.) intentionally excluded — see note
# above NEPALI_FIRST_NAMES.

PHONE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\+9779[678]\d{8}"),
    re.compile(r"(?<!\d)9[678]\d{8}(?!\d)"),
    re.compile(
        r"(?:\+?977[\s\-]?)?"
        r"(?:0\d{1,2}[\s\-]?\d{6,7}"
        r"|[\u0966-\u096F]{7,10})"
    ),
]

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

DEVA_TOKEN_RE = re.compile(r"[\u0900-\u097F\u200d]+")

_sorted_names = sorted(NEPALI_FIRST_NAMES, key=len, reverse=True)
ROMAN_NAME_RE = re.compile(
    r"(?<![A-Za-z])("
    + "|".join(re.escape(name) for name in _sorted_names)
    + r")(?![A-Za-z])",
    re.IGNORECASE,
)


class PiiResult(TypedDict):
    flagged: bool
    matched_terms: list[str]


def _find_phones(text: str) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for pattern in PHONE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0).strip()
            if value and value not in seen:
                seen.add(value)
                matches.append(value)
    return matches


def _find_emails(text: str) -> list[str]:
    return list(dict.fromkeys(EMAIL_PATTERN.findall(text)))


def _find_roman_names(text: str) -> list[str]:
    return list(dict.fromkeys(ROMAN_NAME_RE.findall(text)))


def _find_devanagari_names(text: str) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for token in DEVA_TOKEN_RE.findall(text):
        if token in DEVANAGARI_NAMES and token not in seen:
            seen.add(token)
            matches.append(token)
    return matches


def scan_pii(text: str) -> PiiResult:
    """Detect phone numbers, emails, and common Nepali first names."""
    matched: list[str] = []
    matched.extend(_find_phones(text))
    matched.extend(_find_emails(text))
    matched.extend(_find_roman_names(text))
    matched.extend(_find_devanagari_names(text))

    flagged = len(matched) > 0
    if flagged:
        logger.info("PII matches found: %s", matched)

    return {"flagged": flagged, "matched_terms": matched}
