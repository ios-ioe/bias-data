"""PII detection for submission text."""

import logging
import re
import threading
from typing import Optional, TypedDict

from services.embedder_client import ner_remote

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
    """Detect phone numbers, emails, and common Nepali first names.

    Used on the LIVE /check-submission path -- regex + a fixed name list
    only, deliberately. No model loading, no network call, no meaningful
    latency added to a participant's submit flow."""
    matched: list[str] = []
    matched.extend(_find_phones(text))
    matched.extend(_find_emails(text))
    matched.extend(_find_roman_names(text))
    matched.extend(_find_devanagari_names(text))

    flagged = len(matched) > 0
    if flagged:
        logger.info("PII matches found: %s", matched)

    return {"flagged": flagged, "matched_terms": matched}


# ---------------------------------------------------------------------------
# NER-based name detection -- QA BATCH ONLY (see run_qa_batch in qa_batch.py).
#
# The fixed name list above catches ~70 common first names instantly with
# zero latency, which is fine for the live per-submission check. It misses
# everything else, though -- most Nepali names aren't in any fixed list.
# Since the QA batch is an admin-triggered, one-time, post-event action (not
# something running on every participant's submit click), we can afford to
# lazily load a real NER model here and run it once across every row, without
# adding any cost to the live flow at all.
#
# This never raises: if the model can't be loaded (no internet, HF Hub
# unreachable, out of memory, whatever), the batch just logs a warning and
# falls back to the regex+list-only result for every row -- same as before
# this feature existed.
# ---------------------------------------------------------------------------

NER_MODEL_NAME = "debabrata-ai/Nepali-Named-Entity-Tagger-XLM-R"

_ner_pipeline = None
_ner_load_attempted = False
_ner_lock = threading.Lock()


def _get_ner_pipeline():
    """Lazily load the NER pipeline on first use. Loaded at most once per
    process; a failed load is remembered so we don't retry a slow HF Hub
    download on every single batch run within the same process lifetime."""
    global _ner_pipeline, _ner_load_attempted

    with _ner_lock:
        if _ner_pipeline is not None or _ner_load_attempted:
            return _ner_pipeline

        _ner_load_attempted = True
        try:
            from transformers import (
                AutoModelForTokenClassification,
                AutoTokenizer,
                pipeline,
            )

            logger.info("QA batch: loading NER model %s (first use, may take a while)", NER_MODEL_NAME)
            tokenizer = AutoTokenizer.from_pretrained(NER_MODEL_NAME)
            model = AutoModelForTokenClassification.from_pretrained(NER_MODEL_NAME)
            _ner_pipeline = pipeline(
                "ner",
                model=model,
                tokenizer=tokenizer,
                aggregation_strategy="simple",
            )
            logger.info("QA batch: NER model loaded successfully")
        except Exception as exc:
            logger.warning(
                "QA batch: could not load NER model (%s) -- falling back to "
                "regex + fixed name list only for this run: %s",
                NER_MODEL_NAME,
                exc,
            )
            _ner_pipeline = None

    return _ner_pipeline


def is_ner_available() -> bool:
    """True once a load has been attempted and succeeded. Does not trigger
    a load itself -- callers that want to know before doing real work should
    call _get_ner_pipeline() (via scan_pii_batch) and check its return."""
    return _ner_pipeline is not None


_NER_BATCH_SIZE = 32


def scan_pii_batch(texts: list[str]) -> list[PiiResult]:
    """QA-batch version of scan_pii: same regex + name-list checks as the
    live path, PLUS any PERSON entity a NER model finds -- covering names
    outside the fixed list. Tiered fallback, same pattern as
    duplicate_service's embedding lookup: try the remote embedder Space's
    /ner endpoint first, then a local in-process model, then plain
    regex+list if neither is available. Never raises.

    Runs NER across all texts in one batched pass rather than one row at a
    time, since this is the whole point of only doing this at QA-batch time:
    an admin runs it once, not per-submission."""
    base_results = [scan_pii(text) for text in texts]
    if not texts:
        return base_results

    entities_per_text = ner_remote(texts)
    if entities_per_text is None:
        entities_per_text = _local_ner_batch(texts)

    if entities_per_text is None:
        return base_results

    for result, entities in zip(base_results, entities_per_text):
        person_names = [
            ent["word"].strip()
            for ent in entities
            if ent.get("entity_group") == "PER" and ent.get("word", "").strip()
        ]
        new_names = [name for name in person_names if name not in result["matched_terms"]]
        if new_names:
            result["matched_terms"] = result["matched_terms"] + new_names
            result["flagged"] = True

    return base_results


def _local_ner_batch(texts: list[str]) -> Optional[list[list[dict]]]:
    """Fallback tier when the remote embedder Space's /ner is unconfigured
    or unreachable: load and run the same NER model in-process instead.
    Returns None (never raises) if that also fails, so the caller degrades
    to regex+list-only."""
    ner = _get_ner_pipeline()
    if ner is None:
        return None

    all_entities: list[list[dict]] = []
    try:
        for start in range(0, len(texts), _NER_BATCH_SIZE):
            chunk = texts[start : start + _NER_BATCH_SIZE]
            chunk_entities = ner(chunk)
            if chunk and chunk_entities and not isinstance(chunk_entities[0], list):
                chunk_entities = [chunk_entities]
            all_entities.extend(chunk_entities)
    except Exception as exc:
        logger.warning("Local NER inference failed partway through, using regex+list results only: %s", exc)
        return None

    return all_entities
