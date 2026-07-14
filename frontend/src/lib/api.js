// All reads and writes now go through the FastAPI backend instead of talking
// to Supabase directly with the anon key. The backend derives team_id (and,
// for admin routes, organizer identity) from a signed session token — the
// client can no longer forge team_id on an insert, read another team's data,
// or unlock the admin panel just by knowing a build-time env var.

const DEFAULT_TIMEOUT_MS = 30000;
const HF_BASE = (import.meta.env.VITE_HF_SPACE_URL || "").replace(/\/$/, "");

const TEAM_TOKEN_KEY = "bias_tool_team_token";
const ADMIN_TOKEN_KEY = "bias_tool_admin_token";

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

export async function loginWithAccessCode(accessCode) {
  const code = accessCode.trim();
  if (!code) {
    throw new Error("Enter your team access code.");
  }
  const data = await request("/login", { method: "POST", body: { access_code: code } });
  setTeamToken(data.token);
  return { team_id: data.team_id, team_name: data.team_name };
}

export function checkSubmission(team_id, text) {
  // team_id here is informational only (used for logging on the backend) —
  // the backend never trusts it for authorization.
  return request("/check-submission", { method: "POST", body: { team_id, text } });
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

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export async function adminLogin(password) {
  const data = await request("/admin/login", { method: "POST", body: { password } });
  setAdminToken(data.token);
  return true;
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
