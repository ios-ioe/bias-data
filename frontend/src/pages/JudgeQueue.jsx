import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchJudgeQueue, submitJudgeLabel } from "../lib/api.js";
import { useJudge } from "../context/JudgeContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { CATEGORIES } from "../config/quotas.js";
import LoadingSpinner from "../components/LoadingSpinner.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Badge from "../components/Badge.jsx";
import TopBar from "../components/TopBar.jsx";

const emptyLabels = () =>
  CATEGORIES.reduce((acc, category) => ({ ...acc, [category.key]: 0 }), {});

export default function JudgeQueue() {
  const { judge_name, logout } = useJudge();
  const { showToast } = useToast();

  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [labels, setLabels] = useState(emptyLabels);
  const [saving, setSaving] = useState(false);
  const [doneCount, setDoneCount] = useState(0);

  const current = queue[0] || null;

  const anyBias = useMemo(
    () => CATEGORIES.some((category) => labels[category.key] === 1),
    [labels]
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchJudgeQueue();
      setQueue(data);
      setError("");
    } catch (err) {
      setError(err.message || "Failed to load the judging queue.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function setLabel(key, value) {
    setLabels((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit() {
    if (!current) return;
    setSaving(true);
    try {
      await submitJudgeLabel(current.id, labels);
      setDoneCount((count) => count + 1);
      setLabels(emptyLabels());
      setQueue((prev) => prev.slice(1));
      showToast("Label saved", { type: "success" });
    } catch (err) {
      showToast(err.message || "Failed to save label. Try again.", { type: "error" });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="route-loading">
        <LoadingSpinner label="Loading your queue…" />
      </div>
    );
  }

  return (
    <div className="submit">
      <TopBar
        label={judge_name}
        links={[
          { to: "/judge", text: "Review queue" },
          { to: "/leaderboard", text: "Leaderboard" },
        ]}
        onSignOut={logout}
      />
      <div className="submit-head">
        <div>
          <h1 className="page-title">Judge review</h1>
          <p className="page-sub">
            Signed in as <strong>{judge_name}</strong>. Label each sentence
            independently — you won't see the participant's original labels.
          </p>
        </div>
        <div className="stat-pill">
          <span className="stat-num">{doneCount}</span>
          <span className="stat-cap">labeled</span>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {!current ? (
        <EmptyState
          title="Queue empty"
          message="No sampled items left to review. Check back if the organizer samples another batch, or you're all done — thank you!"
        />
      ) : (
        <>
          <div className="submit-grid">
            <section className="panel">
              <span className="field-label">Sentence {doneCount + 1} of {doneCount + queue.length}</span>
              <p className="nepali" style={{ fontSize: 18, marginTop: 12 }}>
                {current.text}
              </p>
            </section>

            <section className="panel">
              <div className="labels-head">
                <span className="field-label">Bias categories</span>
                <Badge variant={anyBias ? "accent" : "neutral"}>
                  {anyBias ? "biased" : "non-biased"}
                </Badge>
              </div>
              <div className="labels">
                {CATEGORIES.map((category) => (
                  <div className="label-row" key={category.key}>
                    <span className="label-name">{category.label}</span>
                    <fieldset className="radio-group">
                      <legend className="sr-only">{category.label}</legend>
                      <label className="radio-label">
                        <input
                          type="radio"
                          name={category.key}
                          value="0"
                          checked={labels[category.key] === 0}
                          onChange={() => setLabel(category.key, 0)}
                          disabled={saving}
                        />
                        <span>No</span>
                      </label>
                      <label className="radio-label">
                        <input
                          type="radio"
                          name={category.key}
                          value="1"
                          checked={labels[category.key] === 1}
                          onChange={() => setLabel(category.key, 1)}
                          disabled={saving}
                        />
                        <span>Yes</span>
                      </label>
                    </fieldset>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <div className="submit-bar">
            <button
              type="button"
              className="btn btn-primary btn-lg"
              disabled={saving}
              onClick={handleSubmit}
            >
              {saving ? "Saving…" : "Save & next"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
