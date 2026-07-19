import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminLogin, judgeLogin, loginWithAccessCode, setAdminToken } from "../lib/api.js";
import { useTeam } from "../context/TeamContext.jsx";
import { useJudge } from "../context/JudgeContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import LoadingSpinner from "../components/LoadingSpinner.jsx";

const ROLES = {
  PARTICIPANT: "participant",
  JUDGE: "judge",
  ADMIN: "admin",
};

const ROLE_COPY = {
  [ROLES.PARTICIPANT]: {
    label: "Team access code",
    placeholder: "e.g. everest-7412",
    type: "text",
  },
  [ROLES.JUDGE]: {
    label: "Judge access code",
    placeholder: "e.g. judge-alina-40213",
    type: "text",
  },
  [ROLES.ADMIN]: {
    label: "Password",
    placeholder: "admin password",
    type: "password",
  },
};

const EMAIL_ROLES = new Set([ROLES.PARTICIPANT, ROLES.ADMIN]);

export default function Login() {
  const [role, setRole] = useState(ROLES.PARTICIPANT);
  const [email, setEmail] = useState("");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const { login: teamLogin, logout: teamLogout } = useTeam();
  const { login: judgeLoginContext, logout: judgeLogout } = useJudge();
  const { showToast } = useToast();
  const navigate = useNavigate();

  function selectRole(nextRole) {
    setRole(nextRole);
    setEmail("");
    setValue("");
    setError("");
  }

  // A device can only be signed in as ONE of team / judge / admin at a
  // time. Whichever role just logged in wins -- clear the other two
  // sessions (both their tokens and their stored identity) so a stale
  // session from a previous role never lingers alongside the new one.
  function clearOtherSessions(activeRole) {
    if (activeRole !== "team") teamLogout();
    if (activeRole !== "judge") judgeLogout();
    if (activeRole !== "admin") setAdminToken(null);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (EMAIL_ROLES.has(role) && !email.trim()) {
      setError("Enter your email address.");
      return;
    }
    if (!value.trim()) {
      setError(
        role === ROLES.ADMIN ? "Enter the admin password." : "Enter your access code."
      );
      return;
    }

    setBusy(true);
    try {
      if (role === ROLES.PARTICIPANT) {
        const team = await loginWithAccessCode(email, value);
        clearOtherSessions("team");
        teamLogin(team);
        showToast(`Welcome, ${team.team_name}`, { type: "success" });
        navigate("/submit", { replace: true });
      } else if (role === ROLES.JUDGE) {
        const judge = await judgeLogin(value);
        clearOtherSessions("judge");
        judgeLoginContext(judge);
        showToast(`Welcome, ${judge.judge_name}`, { type: "success" });
        navigate("/judge", { replace: true });
      } else {
        const admin = await adminLogin(email, value);
        clearOtherSessions("admin");
        showToast(`Welcome back, ${admin.admin_name}`, { type: "success" });
        navigate("/admin", { replace: true });
      }
    } catch (err) {
      setError(err.message || "Sign-in failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const copy = ROLE_COPY[role];

  return (
    <div className="unified-login-wrap">
      <div className="unified-login-card">
        <h1 className="unified-login-title">Welcome Back</h1>
        <p className="unified-login-sub">Access your dashboard to manage your activities.</p>

        <div className="unified-login-tabs" role="tablist" aria-label="Sign in as">
          {[
            { key: ROLES.PARTICIPANT, label: "Participant" },
            { key: ROLES.JUDGE, label: "Judge" },
            { key: ROLES.ADMIN, label: "Admin" },
          ].map((tab) => (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={role === tab.key}
              className={`unified-login-tab ${role === tab.key ? "unified-login-tab-active" : ""}`}
              onClick={() => selectRole(tab.key)}
              disabled={busy}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="unified-login-form" noValidate>
          {EMAIL_ROLES.has(role) && (
            <>
              <label className="field-label" htmlFor="unified-login-email">
                Email address
              </label>
              <input
                id="unified-login-email"
                className="input unified-login-input"
                type="email"
                placeholder="name@company.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="off"
                disabled={busy}
              />
            </>
          )}

          <label className="field-label" htmlFor="unified-login-value">
            {copy.label}
          </label>
          <input
            id="unified-login-value"
            className="input unified-login-input"
            type={copy.type}
            placeholder={copy.placeholder}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            autoFocus={!EMAIL_ROLES.has(role)}
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
          />

          <button
            className="btn unified-login-submit btn-block"
            type="submit"
            disabled={busy}
          >
            {busy ? "Signing in…" : "Sign In →"}
          </button>
        </form>

        {busy && (
          <div className="login-spinner">
            <LoadingSpinner label="Verifying…" inline />
          </div>
        )}
        {error && <div className="alert alert-error">{error}</div>}

        <p className="unified-login-footer">
          New here? Ask your organizer for a team access code.
        </p>
      </div>
    </div>
  );
}
