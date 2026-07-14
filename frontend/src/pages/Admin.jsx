import { useCallback, useEffect, useMemo, useState } from "react";
import {
  adminLogin,
  createTeam,
  downloadJson,
  fetchAdminSubmissions,
  fetchExportRows,
  fetchLeaderboard,
  fetchTeams,
  getAdminToken,
  runQaBatch,
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

const DISPLAY_LIMIT = 400;
const TABS = { SUBMISSIONS: "submissions", LEADERBOARD: "leaderboard", TEAMS: "teams" };

export default function Admin() {
  const { showToast } = useToast();

  // The admin "password gate" now calls the backend, which checks ADMIN_PASSWORD
  // server-side and returns a signed admin token — the password itself, and the
  // authorization decision, never live in the browser bundle like the old
  // VITE_ADMIN_PASSWORD did.
  const [authed, setAuthed] = useState(() => Boolean(getAdminToken()));
  const [pass, setPass] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState("");

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

  async function handleLogin(event) {
    event.preventDefault();
    setLoginBusy(true);
    setLoginError("");
    try {
      await adminLogin(pass);
      setAuthed(true);
    } catch (err) {
      setLoginError(err.message || "Wrong password.");
    } finally {
      setLoginBusy(false);
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
    return (
      <div className="login-wrap">
        <div className="login-card">
          <div className="login-eyebrow">Organizer only</div>
          <h1 className="login-title">Admin</h1>
          <form className="login-form" onSubmit={handleLogin}>
            <label className="field-label" htmlFor="admin-pass">
              Admin password
            </label>
            <input
              id="admin-pass"
              className="input login-input"
              type="password"
              placeholder="admin password"
              value={pass}
              onChange={(event) => setPass(event.target.value)}
              autoFocus
              disabled={loginBusy}
            />
            <button className="btn btn-primary btn-block" type="submit" disabled={loginBusy}>
              {loginBusy ? "Checking…" : "Unlock"}
            </button>
          </form>
          {loginBusy && (
            <div className="login-spinner">
              <LoadingSpinner label="Verifying…" inline />
            </div>
          )}
          {loginError && <div className="alert alert-error">{loginError}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="admin">
      <div className="submit-head">
        <div>
          <h1 className="page-title">Admin</h1>
          <p className="page-sub">
            {rows.length} submissions total · leaderboard visible to organizers only
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
        loading ? (
          <SkeletonTable rows={6} cols={3} />
        ) : board.length === 0 ? (
          <EmptyState title="No teams yet" message="Teams will appear here once they start submitting." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Team ID</th>
                  <th>Credited submissions</th>
                  <th>Total submissions (incl. duplicates)</th>
                </tr>
              </thead>
              <tbody>
                {board.map((team, index) => (
                  <tr key={team.team_id}>
                    <td>{index + 1}</td>
                    <td className="mono-sm">{team.team_id}</td>
                    <td>{team.credited}</td>
                    <td className="muted">{team.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
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
