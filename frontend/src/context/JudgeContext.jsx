import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { setJudgeToken } from "../lib/api.js";

const JudgeContext = createContext(null);
const STORAGE_KEY = "bias_tool_judge";

function readStoredJudge() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed?.judge_id && parsed?.judge_name) return parsed;
    return null;
  } catch {
    return null;
  }
}

export function JudgeProvider({ children }) {
  const [judge, setJudge] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setJudge(readStoredJudge());
    setLoading(false);
  }, []);

  useEffect(() => {
    if (loading) return;
    try {
      if (judge) localStorage.setItem(STORAGE_KEY, JSON.stringify(judge));
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore storage errors */
    }
  }, [judge, loading]);

  // Same stale-session handling as TeamContext -- a judge session token can
  // expire or be rejected after a backend redeploy; clear it so /judge/login
  // becomes reachable again instead of looping on 401s.
  useEffect(() => {
    function handleUnauthorized(event) {
      if (event.detail?.isJudgeToken) {
        setJudge(null);
        setJudgeToken(null);
      }
    }
    window.addEventListener("bias-tool:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("bias-tool:unauthorized", handleUnauthorized);
  }, []);

  const login = (nextJudge) => {
    setJudge({
      judge_id: nextJudge.judge_id,
      judge_name: nextJudge.judge_name,
    });
  };

  const logout = () => {
    setJudge(null);
    setJudgeToken(null);
  };

  const value = useMemo(
    () => ({
      judge,
      judge_id: judge?.judge_id ?? null,
      judge_name: judge?.judge_name ?? null,
      isAuthenticated: Boolean(judge),
      loading,
      login,
      logout,
    }),
    [judge, loading]
  );

  return <JudgeContext.Provider value={value}>{children}</JudgeContext.Provider>;
}

export function useJudge() {
  const ctx = useContext(JudgeContext);
  if (!ctx) throw new Error("useJudge must be used inside JudgeProvider");
  return ctx;
}
