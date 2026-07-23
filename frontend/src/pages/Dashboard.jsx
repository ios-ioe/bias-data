import { useEffect, useMemo, useState } from "react";
import { fetchMySubmissions } from "../lib/api.js";
import { useTeam } from "../context/TeamContext.jsx";
import {
  CATEGORIES,
  QUOTAS,
  countByCategory,
  quotaProgress,
} from "../config/quotas.js";
import ProgressCard from "../components/ProgressCard.jsx";
import QuotaProgress from "../components/QuotaProgress.jsx";
import LoadingCard from "../components/LoadingCard.jsx";
import { SkeletonMeters } from "../components/Skeleton.jsx";
import Badge from "../components/Badge.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import EmptyState from "../components/EmptyState.jsx";
import TopBar from "../components/TopBar.jsx";

const REFRESH_MS = 15000;

function formatSubmittedAt(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function Dashboard() {
  const { team_name, logout } = useTeam();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const data = await fetchMySubmissions();
        if (active) {
          setRows(data);
          setError("");
        }
      } catch (err) {
        if (active) setError(err.message || "Failed to load progress.");
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    const interval = setInterval(load, REFRESH_MS);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const { counts } = useMemo(() => countByCategory(rows), [rows]);
  const progress = useMemo(() => quotaProgress(rows), [rows]);
  const completedQuotaCount = progress.completedCategories.length;

  return (
    <div className="dash">
      <TopBar
        label={team_name}
        links={[
          { to: "/submit", text: "Submit" },
          { to: "/dashboard", text: "Dashboard" },
          { to: "/tutorial", text: "Tutorial" },
        ]}
        onSignOut={logout}
      />
      <div className="submit-head">
        <div>
          <h1 className="page-title">{team_name}</h1>
          <p className="page-sub">Live progress toward each category quota.</p>
        </div>
        <div className="stat-pill stat-pill-lg">
          <span className="stat-num">{progress.pct}%</span>
          <span className="stat-cap">complete</span>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <LoadingCard count={5} />
      ) : (
        <div className="dash-summary">
          <ProgressCard label="Total submissions" value={rows.length} />
          <ProgressCard
            label="Completed quotas"
            value={completedQuotaCount}
            hint={`of ${CATEGORIES.length} categories`}
          />
          <ProgressCard label="Remaining quotas" value={progress.remaining} />
          <ProgressCard
            label="Overall completion"
            value={`${progress.pct}%`}
            hint={`${progress.earned} / ${progress.need} units`}
            accent
          />
        </div>
      )}

      {progress.completedCategories.length > 0 && (
        <section className="panel completed-panel">
          <h2 className="section-title">Completed categories</h2>
          <div className="badge-row">
            {progress.completedCategories.map((label) => (
              <Badge key={label} variant="success">
                {label}
              </Badge>
            ))}
          </div>
        </section>
      )}

      {loading ? (
        <SkeletonMeters count={11} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No submissions yet"
          message="Head to Submit and save your first labeled sentence."
        />
      ) : (
        <>
          <section className="panel quota-panel">
            <h2 className="section-title">Category progress</h2>
            <div className="quota-grid">
              {CATEGORIES.map((category) => (
                <QuotaProgress
                  key={category.key}
                  label={category.label}
                  count={counts[category.key]}
                  required={QUOTAS[category.key]}
                />
              ))}
            </div>
          </section>

          <section className="panel">
            <h2 className="section-title">Your submissions</h2>
            <p className="page-sub" style={{ marginTop: -4, marginBottom: 14 }}>
              Duplicate and PII flags update automatically once an organizer runs
              the QA batch after submissions close.
            </p>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Text</th>
                    <th>Labels</th>
                    <th>Duplicate</th>
                    <th>PII</th>
                    <th>Submitted</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.id}
                      className={row.flag_duplicate || row.flag_pii ? "row-flagged" : ""}
                    >
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
                      <td className="mono-sm">{formatSubmittedAt(row.submitted_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
