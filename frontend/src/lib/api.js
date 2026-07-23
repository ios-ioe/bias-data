// All reads and writes now go through the FastAPI backend instead of talking
// to Supabase directly with the anon key. The backend derives team_id (and,
// for admin routes, organizer identity) from a signed session token — the
// client can no longer forge team_id on an insert, read another team's data,
// or unlock the admin panel just by knowing a build-time env var.

const DEFAULT_TIMEOUT_MS = 30000;
const HF_BASE = (import.meta.env.VITE_HF_SPACE_URL || "").replace(/\/$/, "");

const TEAM_TOKEN_KEY = "bias_tool_team_token";
const ADMIN_TOKEN_KEY = "bias_tool_admin_token";
const JUDGE_TOKEN_KEY = "bias_tool_judge_token";

export function getTeamToken() {
  return localStorage.getItem(TEAM_TOKEN_KEY) || "";
}
export function setTeamToken(token) {
  if (token) localStorage.setItem(TEAM_TOKEN_KEY, token);
  else localStorage.removeItem(TEAM_TOKEN_KEY);
}

export function getAdminToken() {
  return sessionStorage.getItem(ADMIN_TOKEN_KEY) || "";
}
export function setAdminToken(token) {
  if (token) sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
  else sessionStorage.removeItem(ADMIN_TOKEN_KEY);
}

// Judges are a separate identity from teams/admin, entirely post-event.
// Session stored the same way as a team's (localStorage), since a judge
// might reasonably take a break and come back mid-review-session.
export function getJudgeToken() {
  return localStorage.getItem(JUDGE_TOKEN_KEY) || "";
}
export function setJudgeToken(token) {
  if (token) localStorage.setItem(JUDGE_TOKEN_KEY, token);
  else localStorage.removeItem(JUDGE_TOKEN_KEY);
}

async function request(path, { method = "GET", body, token, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  if (!HF_BASE) {
    throw new Error(
      "VITE_HF_SPACE_URL is not configured. Set it in .env or Vercel env vars."
    );
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const res = await fetch(`${HF_BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = "";
      try {
        const payload = await res.json();
        detail = payload.detail || JSON.stringify(payload);
      } catch {
        detail = await res.text().catch(() => "");
      }

      if (res.status === 401 && token) {
        // A previously-valid token is now rejected (expired, or the
        // backend's SESSION_SECRET was rotated) -- broadcast which kind of
        // session it was so TeamContext / Admin can clear the stale
        // session and send the user back to a real login screen, instead
        // of leaving them stuck on a page that will keep 401ing forever.
        window.dispatchEvent(
          new CustomEvent("bias-tool:unauthorized", {
            detail: {
              isTeamToken: token === getTeamToken(),
              isAdminToken: token === getAdminToken(),
              isJudgeToken: token === getJudgeToken(),
            },
          })
        );
      }

      throw new Error(detail || `${path} failed (${res.status})`);
    }

    if (res.status === 204) return null;
    return res.json();
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error(`${path} timed out after ${timeoutMs / 1000}s`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function checkHealth() {
  if (!HF_BASE) return { ok: false, reason: "missing_url" };
  try {
    const res = await fetch(`${HF_BASE}/health`, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) return { ok: false, reason: `status_${res.status}` };
    return { ok: true, data: await res.json() };
  } catch {
    return { ok: false, reason: "unreachable" };
  }
}

// ---------------------------------------------------------------------------
// Team auth + submissions
// ---------------------------------------------------------------------------

export async function loginWithAccessCode(email, accessCode) {
  const trimmedEmail = (email || "").trim();
  const code = (accessCode || "").trim();
  if (!trimmedEmail) {
    throw new Error("Enter your email address.");
  }
  if (!code) {
    throw new Error("Enter your team access code.");
  }
  const data = await request("/login", {
    method: "POST",
    body: { email: trimmedEmail, access_code: code },
  });
  setTeamToken(data.token);
  return { team_id: data.team_id, team_name: data.team_name };
}

export function checkSubmission(team_id, text) {
  // team_id is kept for logging/display only -- the backend now derives
  // the real team_id from the session token below, and scopes the
  // duplicate check to that team's own submissions only.
  return request("/check-submission", {
    method: "POST",
    body: { team_id, text },
    token: getTeamToken(),
  });
}

export function submitEntry(entry) {
  return request("/submit", { method: "POST", body: entry, token: getTeamToken() });
}

export function fetchMySubmissions() {
  return request("/my-submissions", { token: getTeamToken() });
}

export function fetchMyCount() {
  return request("/my-count", { token: getTeamToken() }).then((r) => r.count);
}

// Standings (rank, team name, completion %) visible to organizers and
// judges only -- see routers/leaderboard.py, gated by require_admin_or_judge.
// Uses whichever session is active; judge takes priority since a judge is
// never also logged in as admin in the same browser tab in practice, but
// admin access should still work if opened from the Admin panel.
export function fetchTeamLeaderboard() {
  const token = getJudgeToken() || getAdminToken();
  return request("/leaderboard", { token });
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export async function adminLogin(email, password) {
  const data = await request("/admin/login", {
    method: "POST",
    body: { email: (email || "").trim(), password },
  });
  setAdminToken(data.token);
  return { admin_id: data.admin_id, admin_name: data.admin_name };
}

export function fetchAdmins() {
  return request("/admin/admins", { token: getAdminToken() });
}

export function createAdmin(admin_name, email, password) {
  return request("/admin/admins", {
    method: "POST",
    body: { admin_name, email, password },
    token: getAdminToken(),
  });
}

export function fetchAdminSubmissions() {
  return request("/admin/submissions", { token: getAdminToken() });
}

export function fetchLeaderboard() {
  return request("/admin/leaderboard", { token: getAdminToken() });
}

export function updateJudgeReviewed(id, reviewed) {
  return request("/admin/mark-reviewed", {
    method: "POST",
    body: { id, reviewed },
    token: getAdminToken(),
  });
}

export function runQaBatch() {
  return request("/admin/qa-batch", { method: "POST", token: getAdminToken(), timeoutMs: 120000 });
}

export function fetchExportRows() {
  return request("/admin/export", { token: getAdminToken() });
}

export function fetchTeams() {
  return request("/admin/teams", { token: getAdminToken() });
}

export function createTeam(team_name, member_emails) {
  return request("/admin/teams", {
    method: "POST",
    body: { team_name, member_emails },
    token: getAdminToken(),
  });
}

export function fetchJudges() {
  return request("/admin/judges", { token: getAdminToken() });
}

export function createJudge(judge_name) {
  return request("/admin/judges", {
    method: "POST",
    body: { judge_name },
    token: getAdminToken(),
  });
}

export function sampleForJudging(per_team = 10) {
  return request("/admin/judge-sample", {
    method: "POST",
    body: { per_team },
    token: getAdminToken(),
  });
}

export function fetchJudgeReport() {
  return request("/admin/judge-report", { token: getAdminToken() });
}

// ---------------------------------------------------------------------------
// Judge (post-event blind review) — separate identity from teams/admin
// ---------------------------------------------------------------------------

export async function judgeLogin(accessCode) {
  const code = accessCode.trim();
  if (!code) {
    throw new Error("Enter your judge access code.");
  }
  const data = await request("/judge/login", { method: "POST", body: { access_code: code } });
  setJudgeToken(data.token);
  return { judge_id: data.judge_id, judge_name: data.judge_name };
}

export function fetchJudgeQueue() {
  return request("/judge/queue", { token: getJudgeToken() });
}

export function submitJudgeLabel(submission_id, labels) {
  return request("/judge/label", {
    method: "POST",
    body: { submission_id, ...labels },
    token: getJudgeToken(),
  });
}

export function downloadJson(rows, filenamePrefix = "bias_submissions") {
  const blob = new Blob([JSON.stringify(rows, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${filenamePrefix}_${new Date().toISOString().slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
  return rows.length;
}
