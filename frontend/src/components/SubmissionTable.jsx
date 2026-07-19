import { CATEGORIES } from "../config/quotas.js";
import Badge from "./Badge.jsx";
import StatusBadge from "./StatusBadge.jsx";

function formatSubmittedAt(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function SubmissionTable({ rows, onReviewChange, busyId }) {
  return (
    <div className="table-wrap">
      <table className="table admin-table">
        <thead>
          <tr>
            <th>Team</th>
            <th>Text</th>
            <th>Labels</th>
            <th>Duplicate</th>
            <th>PII</th>
            <th>Reviewed</th>
            <th>Submitted</th>
            <th>Platform</th>
            <th>Comment</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={row.flag_duplicate || row.flag_pii ? "row-flagged" : ""}
            >
              <td className="mono-sm">{row.team_id}</td>
              <td className="td-text nepali">{row.text}</td>
              <td className="td-labels">
                {CATEGORIES.filter((category) => Number(row[category.key]) === 1).map(
                  (category) => (
                    <Badge key={category.key} variant="accent">
                      {category.label}
                    </Badge>
                  )
                )}
                {CATEGORIES.every((category) => Number(row[category.key]) === 0) && (
                  <Badge variant="neutral">non-biased</Badge>
                )}
              </td>
              <td>
                <StatusBadge active={row.flag_duplicate} variant="dup" />
              </td>
              <td>
                <StatusBadge active={row.flag_pii} variant="warn" />
              </td>
              <td>
                <label className="review-toggle">
                  <input
                    type="checkbox"
                    checked={!!row.judge_reviewed}
                    disabled={busyId === row.id}
                    onChange={(event) => onReviewChange(row.id, event.target.checked)}
                    aria-label={`Mark submission ${row.id} as reviewed`}
                  />
                  <span>{row.judge_reviewed ? "Yes" : "No"}</span>
                </label>
              </td>
              <td className="mono-sm">{formatSubmittedAt(row.submitted_at)}</td>
              <td>{row.source_platform || "—"}</td>
              <td className="td-text">{row.comment || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
