import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import {
  createJudge,
  createTeam,
  downloadJson,
  fetchAdminSubmissions,
  fetchExportRows,
  fetchJudgeReport,
  fetchJudges,
  fetchLeaderboard,
  fetchTeams,
  getAdminToken,
  runQaBatch,
  sampleForJudging,
  setAdminToken,
  updateJudgeReviewed,
} from "../lib/api.js";
import { useToast } from "../context/ToastContext.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import { SkeletonTable } from "../components/Skeleton.jsx";
import EmptyState from "../components/EmptyState.jsx";
import AdminFilters from "../components/AdminFilters.jsx";
import SubmissionTable from "../components/SubmissionTable.jsx";
import QaBatchReport from "../components/QaBatchReport.jsx";
import LoadingSpinner from "../components/LoadingSpinner.jsx";
import TopBar from "../components/TopBar.jsx";
import Leaderboard from "./Leaderboard.jsx";

const DISPLAY_LIMIT = 400;
const TABS = { SUBMISSIONS: "submissions", LEADERBOARD: "leaderboard", TEAMS: "teams", JUDGING: "judging" };

export default function Admin() {
  const { showToast } = useToast();

  // Login itself now happens on the unified /login page (Participant /
  // Judge / Admin tabs) -- this page only checks whether an admin token is
  // already present and redirects to /login if not.
  const [authed, setAuthed] = useState(() => Boolean(getAdminToken()));

  const [tab, setTab] = useState(TABS.SUBMISSIONS);
  const [rows, setRows] = useState([]);
  const [board, setBoard] = useState([]);
  const [teamsList, setTeamsList] = useState([]);
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [newTeamName, setNewTeamName] = useState("");
  const [newTeamEmails, setNewTeamEmails] = useState(["", ""]);
  const [creatingTeam, setCreatingTeam] = useState(false);
  const [teamsError, setTeamsError] = useState("");
  const [copiedCode, setCopiedCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [teamFilter, setTeamFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [report, setReport] = useState(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchConfirm, setBatchConfirm] = useState(false);
  const [reviewBusyId, setReviewBusyId] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [submissions, leaderboard] = await Promise.all([
        fetchAdminSubmissions(),
        fetchLeaderboard(),
      ]);
      setRows(submissions);
      setBoard(leaderboard);
      setError("");
    } catch (err) {
      setError(err.message || "Failed to load submissions.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  // If the admin session token gets rejected (TTL expired, or the backend's
  // SESSION_SECRET was rotated since login), drop back to /login instead of
  // leaving every tab silently failing with stale data on screen.
  useEffect(() => {
    function handleUnauthorized(event) {
      if (event.detail?.isAdminToken) {
        setAuthed(false);
      }
    }
    window.addEventListener("bias-tool:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("bias-tool:unauthorized", handleUnauthorized);
  }, []);

  const loadTeams = useCallback(async () => {
    setTeamsLoading(true);
    try {
      const data = await fetchTeams();
      setTeamsList(data);
      setTeamsError("");
    } catch (err) {
      setTeamsError(err.message || "Failed to load teams.");
    } finally {
      setTeamsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authed && tab === TABS.TEAMS) loadTeams();
  }, [authed, tab, loadTeams]);

  const [judgesList, setJudgesList] = useState([]);
  const [judgesLoading, setJudgesLoading] = useState(false);
  const [judgesError, setJudgesError] = useState("");
  const [newJudgeName, setNewJudgeName] = useState("");
  const [creatingJudge, setCreatingJudge] = useState(false);
  const [sampleCount, setSampleCount] = useState(10);
  const [samplingBusy, setSamplingBusy] = useState(false);
  const [judgeReport, setJudgeReport] = useState(null);
  const [judgeReportBusy, setJudgeReportBusy] = useState(false);

  const loadJudging = useCallback(async () => {
    setJudgesLoading(true);
    try {
      const data = await fetchJudges();
      setJudgesList(data);
      setJudgesError("");
    } catch (err) {
      setJudgesError(err.message || "Failed to load judges.");
    } finally {
      setJudgesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authed && tab === TABS.JUDGING) loadJudging();
  }, [authed, tab, loadJudging]);

  async function handleCreateJudge(event) {
    event.preventDefault();
    if (!newJudgeName.trim()) return;
    setCreatingJudge(true);
    try {
      await createJudge(newJudgeName.trim());
      setNewJudgeName("");
      await loadJudging();
      showToast("Judge added", { type: "success" });
    } catch (err) {
      showToast(err.message || "Failed to add judge.", { type: "error" });
    } finally {
      setCreatingJudge(false);
    }
  }

  async function handleSample() {
    setSamplingBusy(true);
    try {
      const result = await sampleForJudging(sampleCount);
      showToast(
        `Sampled ${result.sampled} submissions across ${result.teams_sampled} teams` +
          (result.teams_skipped_insufficient
            ? ` (${result.teams_skipped_insufficient} teams had none available)`
            : ""),
        { type: "success" }
      );
    } catch (err) {
      showToast(err.message || "Failed to sample submissions.", { type: "error" });
    } finally {
      setSamplingBusy(false);
    }
  }

  async function handleLoadReport() {
    setJudgeReportBusy(true);
    try {
      const data = await fetchJudgeReport();
      setJudgeReport(data);
    } catch (err) {
      showToast(err.message || "Failed to load judge report.", { type: "error" });
    } finally {
      setJudgeReportBusy(false);
    }
  }

  const trimmedEmails = newTeamEmails.map((e) => e.trim()).filter(Boolean);
  const canCreateTeam = newTeamName.trim() && trimmedEmails.length >= 2 && trimmedEmails.length <= 4;

  function updateEmailAt(index, value) {
    setNewTeamEmails((prev) => prev.map((e, i) => (i === index ? value : e)));
  }

  function addEmailField() {
    setNewTeamEmails((prev) => (prev.length < 4 ? [...prev, ""] : prev));
  }

  function removeEmailField(index) {
    setNewTeamEmails((prev) => (prev.length > 2 ? prev.filter((_, i) => i !== index) : prev));
  }

  async function handleCreateTeam(event) {
    event.preventDefault();
    if (!canCreateTeam) return;
    setCreatingTeam(true);
    setTeamsError("");
    try {
      const result = await createTeam(newTeamName.trim(), trimmedEmails);
      setNewTeamName("");
      setNewTeamEmails(["", ""]);
      await loadTeams();
      showToast(
        result?.email_sent
          ? "Team created — access code emailed to all members"
          : "Team created — email not sent, copy the code and send it manually",
        { type: result?.email_sent ? "success" : "warning" }
      );
    } catch (err) {
      const message = err.message || "Failed to create team.";
      setTeamsError(message);
      showToast(message, { type: "error" });
    } finally {
      setCreatingTeam(false);
    }
  }

  async function copyCode(code) {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(""), 1500);
    } catch {
      showToast("Could not copy — select and copy manually.", { type: "error" });
    }
  }

  const teams = useMemo(
    () => [...new Set(rows.map((row) => row.team_id).filter(Boolean))].sort(),
    [rows]
  );

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (teamFilter && row.team_id !== teamFilter) return false;
      if (statusFilter === "duplicate" && !row.flag_duplicate) return false;
      if (statusFilter === "pii" && !row.flag_pii) return false;
      if (statusFilter === "reviewed" && !row.judge_reviewed) return false;
      if (statusFilter === "unreviewed" && row.judge_reviewed) return false;
      if (query) {
        const haystack = `${row.text || ""} ${row.team_id || ""}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
  }, [rows, teamFilter, statusFilter, search]);

  const visibleRows = useMemo(() => filtered.slice(0, DISPLAY_LIMIT), [filtered]);

  async function markReviewed(id, value = true) {
    setReviewBusyId(id);
    try {
      await updateJudgeReviewed(id, value);
      setRows((current) =>
        current.map((row) => (row.id === id ? { ...row, judge_reviewed: value } : row))
      );
    } catch (err) {
      showToast(err.message || "Failed to update review status", { type: "error" });
    } finally {
      setReviewBusyId(null);
    }
  }

  async function onRunBatch() {
    setBatchBusy(true);
    setError("");
    try {
      const result = await runQaBatch();
      setReport(result);
      await load();
      showToast("QA batch completed", { type: "success" });
    } catch (err) {
      const message = err.message || "QA batch failed.";
      setError(message);
      showToast(message, { type: "error" });
    } finally {
      setBatchBusy(false);
      setBatchConfirm(false);
    }
  }

  async function exportJson() {
    try {
      const exportRows = await fetchExportRows();
      const count = downloadJson(exportRows);
      showToast(`Exported ${count} rows`, { type: "success" });
    } catch (err) {
      showToast(err.message || "Export failed", { type: "error" });
    }
  }

  if (!authed) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="admin">
      <TopBar
        label="Admin"
        onSignOut={() => setAdminToken(null)}
      />
      <div className="submit-head">
        <div>
          <h1 className="page-title">Admin</h1>
          <p className="page-sub">
            {rows.length} submissions total · leaderboard is visible to organizers
            and judges only
          </p>
        </div>
        <div className="admin-actions">
          <button type="button" className="btn btn-ghost" onClick={load} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={exportJson}
            disabled={!rows.length || loading}
          >
            Export JSON
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setBatchConfirm(true)}
            disabled={batchBusy}
          >
            {batchBusy ? "Running QA…" : "Run QA batch"}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="tabs">
        <button
          type="button"
          className={`tab ${tab === TABS.SUBMISSIONS ? "tab-active" : ""}`}
          onClick={() => setTab(TABS.SUBMISSIONS)}
        >
          Submissions
        </button>
        <button
          type="button"
          className={`tab ${tab === TABS.LEADERBOARD ? "tab-active" : ""}`}
          onClick={() => setTab(TABS.LEADERBOARD)}
        >
          Leaderboard
        </button>
        <button
          type="button"
          className={`tab ${tab === TABS.TEAMS ? "tab-active" : ""}`}
          onClick={() => setTab(TABS.TEAMS)}
        >
          Teams
        </button>
        <button
          type="button"
          className={`tab ${tab === TABS.JUDGING ? "tab-active" : ""}`}
          onClick={() => setTab(TABS.JUDGING)}
        >
          Judging
        </button>
      </div>

      {tab === TABS.TEAMS ? (
        <>
          <form className="panel" onSubmit={handleCreateTeam} style={{ display: "flex", gap: "0.75rem", alignItems: "flex-end", flexWrap: "wrap", marginBottom: "1rem" }}>
            <div>
              <label className="field-label" htmlFor="new-team-name">
                Team name
              </label>
              <input
                id="new-team-name"
                className="input"
                placeholder="e.g. Team Kanchenjunga"
                value={newTeamName}
                onChange={(event) => setNewTeamName(event.target.value)}
                disabled={creatingTeam}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              <label className="field-label">
                Member emails <span className="opt">2–4 required</span>
              </label>
              {newTeamEmails.map((email, index) => (
                <div key={index} style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                  <input
                    className="input"
                    type="email"
                    placeholder={`member${index + 1}@example.com`}
                    value={email}
                    onChange={(event) => updateEmailAt(index, event.target.value)}
                    disabled={creatingTeam}
                  />
                  {newTeamEmails.length > 2 && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => removeEmailField(index)}
                      disabled={creatingTeam}
                      aria-label={`Remove email ${index + 1}`}
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
              {newTeamEmails.length < 4 && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={addEmailField} disabled={creatingTeam}>
                  + Add another member
                </button>
              )}
            </div>

            <button type="submit" className="btn btn-primary" disabled={creatingTeam || !canCreateTeam}>
              {creatingTeam ? "Creating…" : "Add team"}
            </button>
          </form>
          <p className="muted" style={{ marginBottom: "1rem" }}>
            Adding a team generates an access code (format: team-name-#####) shared by the whole
            team, and emails it to every member listed above via Resend. If email delivery fails
            or Resend isn't configured, copy the code from the table below and send it manually.
          </p>

          {teamsError && <div className="alert alert-error">{teamsError}</div>}

          {teamsLoading ? (
            <SkeletonTable rows={4} cols={4} />
          ) : teamsList.length === 0 ? (
            <EmptyState title="No teams yet" message="Add your first team above." />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Team</th>
                    <th>Team ID</th>
                    <th>Access code</th>
                    <th>Member emails</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {teamsList.map((team) => (
                    <tr key={team.team_id}>
                      <td>{team.team_name}</td>
                      <td className="mono-sm muted">{team.team_id}</td>
                      <td className="mono-sm">{team.access_code}</td>
                      <td className="muted">
                        {Array.isArray(team.member_emails) && team.member_emails.length > 0
                          ? team.member_emails.join(", ")
                          : "—"}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => copyCode(team.access_code)}
                        >
                          {copiedCode === team.access_code ? "Copied!" : "Copy code"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : tab === TABS.LEADERBOARD ? (
        <Leaderboard />
      ) : tab === TABS.JUDGING ? (
        <>
          <div className="panel" style={{ marginBottom: "1rem" }}>
            <h3 style={{ marginTop: 0 }}>1. Add judges</h3>
            <p className="muted">
              Judges are a separate login from teams/admin. They only ever see
              sentence text — never the participant's labels, team name, or
              team_id.
            </p>
            <form
              onSubmit={handleCreateJudge}
              style={{ display: "flex", gap: "0.75rem", alignItems: "flex-end", flexWrap: "wrap" }}
            >
              <div>
                <label className="field-label" htmlFor="new-judge-name">
                  Judge name
                </label>
                <input
                  id="new-judge-name"
                  className="input"
                  placeholder="e.g. Alina Shrestha"
                  value={newJudgeName}
                  onChange={(event) => setNewJudgeName(event.target.value)}
                  disabled={creatingJudge}
                />
              </div>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={creatingJudge || !newJudgeName.trim()}
              >
                {creatingJudge ? "Adding…" : "Add judge"}
              </button>
            </form>

            {judgesError && <div className="alert alert-error">{judgesError}</div>}

            {judgesLoading ? (
              <SkeletonTable rows={2} cols={3} />
            ) : judgesList.length === 0 ? (
              <EmptyState title="No judges yet" message="Add your first judge above." />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Access code</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {judgesList.map((judge) => (
                      <tr key={judge.judge_id}>
                        <td>{judge.judge_name}</td>
                        <td className="mono-sm">{judge.access_code}</td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => copyCode(judge.access_code)}
                          >
                            {copiedCode === judge.access_code ? "Copied!" : "Copy code"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="panel" style={{ marginBottom: "1rem" }}>
            <h3 style={{ marginTop: 0 }}>2. Sample submissions for judging</h3>
            <p className="muted">
              Picks this many submissions from EACH team (not a flat total),
              so every team gets a fair, comparable sample. Run this once,
              after the event closes and after you've run the QA batch above
              (so duplicates are already flagged and excluded). Re-running
              only tops up unsampled rows per team — it never re-samples
              something already picked.
            </p>
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-end" }}>
              <div>
                <label className="field-label" htmlFor="sample-count">
                  Samples per team
                </label>
                <input
                  id="sample-count"
                  type="number"
                  className="input"
                  style={{ width: 100 }}
                  min={1}
                  max={100}
                  value={sampleCount}
                  onChange={(event) => setSampleCount(Number(event.target.value) || 1)}
                  disabled={samplingBusy}
                />
              </div>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSample}
                disabled={samplingBusy}
              >
                {samplingBusy ? "Sampling…" : "Sample now"}
              </button>
            </div>
          </div>

          <div className="panel">
            <h3 style={{ marginTop: 0 }}>3. Judge report</h3>
            <p className="muted">
              "Correct" means the judge's label matched the participant's on
              every category for that row. Refresh after judges finish
              labeling — use the Items list below the table to see the exact
              category-by-category breakdown for any row.
            </p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleLoadReport}
              disabled={judgeReportBusy}
            >
              {judgeReportBusy ? "Loading…" : "Load / refresh report"}
            </button>

            {judgeReport && (
              <div style={{ marginTop: "1rem" }}>
                {judgeReport.teams.length > 0 && (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Team Name</th>
                          <th>Total Data Collected</th>
                          <th>Sample Given to Judges</th>
                          <th>Correct Sample by Judge</th>
                          <th>Incorrect Sample by Judge</th>
                          <th>Flagged (duplicate)</th>
                          <th>Flagged (PII)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {judgeReport.teams.map((row) => (
                          <tr key={row.team_id}>
                            <td>{row.team_name}</td>
                            <td>{row.total_collected}</td>
                            <td>{row.sample_given}</td>
                            <td>{row.correct_by_judge}</td>
                            <td>{row.incorrect_by_judge}</td>
                            <td>{row.flagged_duplicate}</td>
                            <td>{row.flagged_pii}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {judgeReport.items.length > 0 && (
                  <details style={{ marginTop: "1rem" }}>
                    <summary>Item-by-item breakdown ({judgeReport.items.length})</summary>
                    <div className="table-wrap" style={{ marginTop: "0.5rem" }}>
                      <table className="table">
                        <thead>
                          <tr>
                            <th>Team ID</th>
                            <th>Text</th>
                            <th>Judge</th>
                            <th>All match?</th>
                          </tr>
                        </thead>
                        <tbody>
                          {judgeReport.items.map((item) => (
                            <tr key={`${item.submission_id}-${item.judge_id}`}>
                              <td className="mono-sm">{item.team_id}</td>
                              <td className="nepali">{item.text}</td>
                              <td>{item.judge_name}</td>
                              <td>{item.all_categories_match ? "Yes" : "No"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        </>
      ) : (
        <>
          <QaBatchReport report={report} onMarkReviewed={markReviewed} reviewingId={reviewBusyId} />

          <AdminFilters
            search={search}
            onSearchChange={setSearch}
            teamFilter={teamFilter}
            onTeamFilterChange={setTeamFilter}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            teams={teams}
            shownCount={filtered.length}
            totalCount={rows.length}
          />

          {loading ? (
            <SkeletonTable rows={6} cols={9} />
          ) : filtered.length === 0 ? (
            <EmptyState title="No matching submissions" message="Try adjusting your filters." />
          ) : (
            <>
              <SubmissionTable rows={visibleRows} onReviewChange={markReviewed} busyId={reviewBusyId} />
              {filtered.length > DISPLAY_LIMIT && (
                <div className="muted table-note">
                  Showing first {DISPLAY_LIMIT} of {filtered.length}. Narrow with the filters above.
                </div>
              )}
            </>
          )}
        </>
      )}

      <ConfirmDialog
        open={batchConfirm}
        title="Run QA batch?"
        message="This scans all submissions for duplicates and PII, and updates flag columns. It may take a minute on large datasets."
        confirmLabel="Run batch"
        cancelLabel="Cancel"
        variant="primary"
        busy={batchBusy}
        onCancel={() => setBatchConfirm(false)}
        onConfirm={onRunBatch}
      />
    </div>
  );
}
