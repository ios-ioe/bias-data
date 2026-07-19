"""Post-event judge report: for every team, shows how much they submitted,
how much got sampled to judges, and how the judge's blind label compared to
the participant's original label -- plus duplicate/PII flag counts.

"Correct" here means the judge's label matched the participant's on every
single category for that row (a whole-item match, not a partial-credit
score) -- a clear, unambiguous default. The full per-category breakdown is
still included per item, so an organizer can eyeball any specific
disagreement and override this by hand rather than trusting one number.

No model-based check yet -- there's no trained classifier to run this
against currently (see conversation notes). If one gets added later, it
slots in as a third label set here without disturbing this comparison.
"""

import logging

import database
from config import CATEGORIES

logger = logging.getLogger(__name__)

_SAMPLED_COLUMNS = (
    "id,team_id,text,flag_duplicate,flag_pii,sampled_for_judging,"
    + ",".join(f'"{c}"' if c[0].isupper() else c for c in CATEGORIES)
)


def build_judge_report() -> dict:
    teams = {t["team_id"]: t["team_name"] for t in database.list_teams()}

    # Every submission, for total-collected and flag counts per team.
    all_rows = database.fetch_all_submissions("id,team_id,flag_duplicate,flag_pii,sampled_for_judging")

    sampled_rows = database.fetch_sampled_submissions_with_labels(_SAMPLED_COLUMNS)
    sampled_by_id = {row["id"]: row for row in sampled_rows}

    judge_labels = database.fetch_all_judge_labels()
    judges = {j["judge_id"]: j["judge_name"] for j in database.list_judges()}

    # --- Per-team base counts (total collected, flags, sample size) --------
    team_stats: dict[str, dict] = {
        team_id: {
            "team_id": team_id,
            "team_name": team_name,
            "total_collected": 0,
            "flagged_duplicate": 0,
            "flagged_pii": 0,
            "sample_given": 0,
        }
        for team_id, team_name in teams.items()
    }

    for row in all_rows:
        team_id = row.get("team_id")
        if not team_id or team_id not in team_stats:
            continue
        bucket = team_stats[team_id]
        bucket["total_collected"] += 1
        if row.get("flag_duplicate"):
            bucket["flagged_duplicate"] += 1
        if row.get("flag_pii"):
            bucket["flagged_pii"] += 1
        if row.get("sampled_for_judging"):
            bucket["sample_given"] += 1

    # --- Per-item judge comparison, rolled up into correct/incorrect -------
    # A row can have more than one judge's label; each (submission, judge)
    # pair is counted as its own judged item here, since each is an
    # independent blind judgment.
    items: list[dict] = []
    for label in judge_labels:
        submission = sampled_by_id.get(label["submission_id"])
        if not submission:
            continue  # judge labeled something no longer in the sampled set

        team_id = submission.get("team_id")
        per_category: dict[str, dict] = {}
        all_match = True
        for category in CATEGORIES:
            participant_value = int(submission.get(category) or 0)
            judge_value = int(label.get(category) or 0)
            is_match = participant_value == judge_value
            per_category[category] = {
                "participant": participant_value,
                "judge": judge_value,
                "match": is_match,
            }
            if not is_match:
                all_match = False

        if team_id in team_stats:
            key = "correct_by_judge" if all_match else "incorrect_by_judge"
            team_stats[team_id][key] = team_stats[team_id].get(key, 0) + 1

        items.append(
            {
                "submission_id": submission["id"],
                "team_id": team_id,
                "text": submission.get("text"),
                "judge_id": label["judge_id"],
                "judge_name": judges.get(label["judge_id"], label["judge_id"]),
                "all_categories_match": all_match,
                "categories": per_category,
            }
        )

    team_report = []
    for bucket in team_stats.values():
        bucket.setdefault("correct_by_judge", 0)
        bucket.setdefault("incorrect_by_judge", 0)
        team_report.append(bucket)

    # Teams with the most incorrect judged items first -- likely what needs
    # organizer attention.
    team_report.sort(key=lambda t: (-t["incorrect_by_judge"], t["team_name"].lower()))

    return {
        "teams": team_report,
        "items": items,
    }
