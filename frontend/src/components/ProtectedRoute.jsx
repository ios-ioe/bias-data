import { Navigate } from "react-router-dom";
import { useTeam } from "../context/TeamContext.jsx";
import { useJudge } from "../context/JudgeContext.jsx";
import { getAdminToken } from "../lib/api.js";
import LoadingSpinner from "./LoadingSpinner.jsx";

export function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useTeam();

  if (loading) {
    return (
      <div className="route-loading">
        <LoadingSpinner label="Restoring session…" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

export function GuestRoute({ children }) {
  const { isAuthenticated: teamAuthed, loading: teamLoading } = useTeam();
  const { isAuthenticated: judgeAuthed, loading: judgeLoading } = useJudge();

  if (teamLoading || judgeLoading) {
    return (
      <div className="route-loading">
        <LoadingSpinner label="Restoring session…" />
      </div>
    );
  }

  if (teamAuthed) return <Navigate to="/submit" replace />;
  if (judgeAuthed) return <Navigate to="/judge" replace />;
  if (getAdminToken()) return <Navigate to="/admin" replace />;

  return children;
}

// Judges are a wholly separate identity from teams -- a team session does
// not grant judge access and vice versa, so this checks JudgeContext only.
export function JudgeProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useJudge();

  if (loading) {
    return (
      <div className="route-loading">
        <LoadingSpinner label="Restoring session…" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

// No longer used as a route guard directly (the unified /login page covers
// this), kept for any code still importing it.
export function GuestJudgeRoute({ children }) {
  const { isAuthenticated, loading } = useJudge();

  if (loading) {
    return (
      <div className="route-loading">
        <LoadingSpinner label="Restoring session…" />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/judge" replace />;
  }

  return children;
}

// Visible to organizers and judges only, never participant teams -- e.g.
// the leaderboard, so teams can't track a rival's standing mid-event.
export function JudgeOrAdminRoute({ children }) {
  const { isAuthenticated: judgeAuthed, loading: judgeLoading } = useJudge();

  if (judgeLoading) {
    return (
      <div className="route-loading">
        <LoadingSpinner label="Restoring session…" />
      </div>
    );
  }

  const adminAuthed = Boolean(getAdminToken());

  if (!judgeAuthed && !adminAuthed) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

export function RootRedirect() {
  const { isAuthenticated, loading } = useTeam();

  if (loading) {
    return (
      <div className="route-loading">
        <LoadingSpinner label="Restoring session…" />
      </div>
    );
  }

  return <Navigate to={isAuthenticated ? "/submit" : "/login"} replace />;
}
