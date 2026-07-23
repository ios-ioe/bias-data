"""Organizer QA batch: exhaustive dedup, PII scan, quota report."""

import logging

from config import BATCH_SIMILARITY_THRESHOLD, CATEGORIES, QUOTAS
from database import fetch_all_submissions, get_supabase
from services.duplicate_service import pairwise_duplicates
from services.pii_service import scan_pii_batch

logger = logging.getLogger(__name__)


def _submission_columns() -> str:
    quoted = [f'"{category}"' if category[0].isupper() else category for category in CATEGORIES]
    return "id,team_id,text," + ",".join(quoted)


def _build_quota_report(rows: list[dict]) -> dict:
    report: dict = {}
    team_ids = sorted({row.get("team_id") for row in rows if row.get("team_id")})

    for team_id in team_ids:
        team_rows = [row for row in rows if row.get("team_id") == team_id]
        team_report: dict = {}

        for category in CATEGORIES:
            count = sum(1 for row in team_rows if int(row.get(category) or 0) == 1)
            required = QUOTAS.get(category, 0)
            team_report[category] = {
                "count": count,
                "required": required,
                "met": count >= required,
            }

        report[team_id] = team_report

    return report


def _persist_flags(dup_ids: list[str], pii_ids: list[str]) -> None:
    try:
        sb = get_supabase()
        for chunk_ids, column in ((dup_ids, "flag_duplicate"), (pii_ids, "flag_pii")):
            for start in range(0, len(chunk_ids), 200):
                batch = chunk_ids[start : start + 200]
                if batch:
                    sb.table("submissions").update({column: True}).in_("id", batch).execute()
    except Exception as exc:
        logger.warning("Could not persist QA flags: %s", exc)


def run_qa_batch() -> dict:
    """Run the full QA batch and return a structured report."""
    rows = fetch_all_submissions(_submission_columns())
    total_rows = len(rows)

    flagged_duplicates = pairwise_duplicates(rows, threshold=BATCH_SIMILARITY_THRESHOLD)

    flagged_pii: list[dict] = []
    texts = [row.get("text") or "" for row in rows]
    pii_results = scan_pii_batch(texts)
    for row, result in zip(rows, pii_results):
        if result["flagged"]:
            flagged_pii.append({"id": row["id"], "matched_terms": result["matched_terms"]})

    quota_report = _build_quota_report(rows)

    dup_ids = [item["id"] for item in flagged_duplicates]
    pii_ids = [item["id"] for item in flagged_pii]
    _persist_flags(dup_ids, pii_ids)

    logger.info(
        "QA batch complete: rows=%d duplicates=%d pii=%d",
        total_rows,
        len(flagged_duplicates),
        len(flagged_pii),
    )

    return {
        "total_rows": total_rows,
        "flagged_duplicates": flagged_duplicates,
        "flagged_pii": flagged_pii,
        "quota_report": quota_report,
    }
