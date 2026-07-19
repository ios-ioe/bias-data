import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchTeamLeaderboard } from "../lib/api.js";
import { SkeletonBoard } from "../components/Skeleton.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Badge from "../components/Badge.jsx";

const REFRESH_MS = 15000;
const MEDALS = { 1: "🥇", 2: "🥈", 3: "🥉" };

function rankBadgeClass(rank) {
  if (rank === 1) return "lb-rank lb-rank-gold";
  if (rank === 2) return "lb-rank lb-rank-silver";
  if (rank === 3) return "lb-rank lb-rank-bronze";
  return "lb-rank";
}

function rowClass(rank, isYou) {
  const classes = ["board-row"];
  if (rank === 1) classes.push("lb-row-top-1");
  else if (rank === 2) classes.push("lb-row-top-2");
  else if (rank === 3) classes.push("lb-row-top-3");
  if (isYou) classes.push("board-leader");
  return classes.join(" ");
}

export default function Leaderboard() {
  const [board, setBoard] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await fetchTeamLeaderboard();
      setBoard(data);
      setError("");
    } catch (err) {
      setError(err.message || "Failed to load the leaderboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, REFRESH_MS);
    return () => clearInterval(interval);
  }, [load]);

  const you = board.find((entry) => entry.is_you);
  const maxCount = useMemo(
    () => Math.max(1, ...board.map((entry) => entry.credited_submissions || 0)),
    [board]
  );
  const totalCollected = useMemo(
    () => board.reduce((sum, entry) => sum + (entry.credited_submissions || 0), 0),
    [board]
  );

  return (
    <div className="dash">
      <div className="submit-head">
        <div>
          <h1 className="page-title">Leaderboard</h1>
          <p className="page-sub">
            Ranked by number of sentences collected (duplicates excluded). Updates
            automatically.
          </p>
        </div>
        <div className="lb-header-stats">
          {you && (
            <div className="stat-pill stat-pill-lg">
              <span className="stat-num">#{you.rank}</span>
              <span className="stat-cap">your rank</span>
            </div>
          )}
          <div className="stat-pill stat-pill-lg">
            <span className="stat-num">{totalCollected}</span>
            <span className="stat-cap">total collected</span>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <SkeletonBoard count={6} />
      ) : board.length === 0 ? (
        <EmptyState
          title="No teams yet"
          message="Standings will appear here once teams start submitting."
        />
      ) : (
        <ul className="board-list">
          {board.map((entry) => (
            <li
              key={`${entry.rank}-${entry.team_name}`}
              className={rowClass(entry.rank, entry.is_you)}
            >
              <span className={rankBadgeClass(entry.rank)}>
                {MEDALS[entry.rank] || entry.rank}
              </span>
              <div className="board-main">
                <div className="board-name-line">
                  <span className="board-name">
                    {entry.team_name}
                    {entry.is_you && (
                      <span style={{ marginLeft: 8 }}>
                        <Badge variant="accent">You</Badge>
                      </span>
                    )}
                  </span>
                  <span className="board-count">
                    {entry.credited_submissions}
                    <span className="board-count-label">
                      {entry.credited_submissions === 1 ? "sentence" : "sentences"}
                    </span>
                  </span>
                </div>
                <div
                  className="board-track"
                  role="progressbar"
                  aria-valuenow={entry.credited_submissions}
                  aria-valuemin={0}
                  aria-valuemax={maxCount}
                  aria-label={`${entry.team_name} sentences collected`}
                >
                  <div
                    className="board-fill"
                    style={{ width: `${Math.max(3, (entry.credited_submissions / maxCount) * 100)}%` }}
                  />
                </div>
                <div className="board-meta-line">
                  <span>{entry.completion_pct}% of quota</span>
                  {entry.total_submissions > entry.credited_submissions && (
                    <span className="muted">
                      {entry.total_submissions - entry.credited_submissions} excluded (duplicate/PII)
                    </span>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
