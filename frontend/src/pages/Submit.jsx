import { useCallback, useEffect, useMemo, useState } from "react";
import { checkSubmission, fetchMyCount, submitEntry } from "../lib/api.js";
import { useTeam } from "../context/TeamContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { CATEGORIES, SOURCE_PLATFORMS } from "../config/quotas.js";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import LoadingSpinner from "../components/LoadingSpinner.jsx";
import Badge from "../components/Badge.jsx";
import {
  DuplicateWarningContent,
  PiiWarningContent,
} from "../components/WarningCard.jsx";

const DIALOG = {
  NONE: "none",
  DUPLICATE: "duplicate",
  PII: "pii",
  SERVICE_DOWN: "service_down",
};

const emptyLabels = () =>
  CATEGORIES.reduce((acc, category) => ({ ...acc, [category.key]: 0 }), {});

function validateForm(text) {
  const trimmed = text.trim();
  if (!trimmed) {
    return "Enter a Nepali sentence before submitting.";
  }
  return "";
}

export default function Submit() {
  const { team_id, team_name } = useTeam();
  const { showToast } = useToast();

  const [text, setText] = useState("");
  const [labels, setLabels] = useState(emptyLabels);
  const [platform, setPlatform] = useState("");
  const [date, setDate] = useState("");

  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState("");
  const [flowError, setFlowError] = useState("");
  const [checkResult, setCheckResult] = useState(null);
  const [activeDialog, setActiveDialog] = useState(DIALOG.NONE);
  const [teamCount, setTeamCount] = useState(null);

  const trimmedText = text.trim();
  const charCount = trimmedText.length;
  const busy = checking || saving;

  const anyBias = useMemo(
    () => CATEGORIES.some((category) => labels[category.key] === 1),
    [labels]
  );

  const refreshCount = useCallback(async () => {
    try {
      const count = await fetchMyCount();
      setTeamCount(count);
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    refreshCount();
  }, [refreshCount]);

  function setLabel(key, value) {
    setLabels((current) => ({ ...current, [key]: value }));
    setValidationError("");
  }

  function resetForm() {
    setText("");
    setLabels(emptyLabels());
    setPlatform("");
    setDate("");
    setCheckResult(null);
    setFlowError("");
    setValidationError("");
    setActiveDialog(DIALOG.NONE);
  }

  function buildSubmissionRow(checkOutcome) {
    // Note: no team_id here — the backend derives it from the caller's signed
    // session token (see /submit in routers/submission.py), so a team can
    // never write a row under another team's id.
    return {
      text: trimmedText,
      ...Object.fromEntries(
        CATEGORIES.map((category) => [category.key, labels[category.key]])
      ),
      source_platform: platform || null,
      source_date: date || null,
      flag_duplicate: Boolean(checkOutcome?.duplicate?.flagged),
      flag_pii: Boolean(checkOutcome?.pii?.flagged),
    };
  }

  async function saveSubmission(checkOutcome) {
    setSaving(true);
    setFlowError("");

    try {
      await submitEntry(buildSubmissionRow(checkOutcome));
      resetForm();
      await refreshCount();
      showToast("Submission saved successfully", { type: "success" });
    } catch (err) {
      const message = err.message || "Failed to save submission. Try again.";
      setFlowError(message);
      showToast(message, { type: "error" });
    } finally {
      setSaving(false);
      setActiveDialog(DIALOG.NONE);
    }
  }

  function proceedAfterDuplicate(checkOutcome) {
    if (checkOutcome?.pii?.flagged) {
      setActiveDialog(DIALOG.PII);
      return;
    }
    saveSubmission(checkOutcome);
  }

  function proceedAfterCheck(checkOutcome) {
    if (checkOutcome?.duplicate?.flagged) {
      setActiveDialog(DIALOG.DUPLICATE);
      return;
    }
    if (checkOutcome?.pii?.flagged) {
      setActiveDialog(DIALOG.PII);
      return;
    }
    saveSubmission(checkOutcome);
  }

  async function handleSubmit() {
    const validationMessage = validateForm(text);
    if (validationMessage) {
      setValidationError(validationMessage);
      return;
    }

    setValidationError("");
    setFlowError("");
    setCheckResult(null);
    setChecking(true);

    try {
      const result = await checkSubmission(team_id, trimmedText);
      setCheckResult(result);
      proceedAfterCheck(result);
    } catch (err) {
      setFlowError(
        err.message ||
          "The duplicate and PII check service is unavailable. You can still save — issues will be caught in the final QA pass."
      );
      setCheckResult(null);
      setActiveDialog(DIALOG.SERVICE_DOWN);
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="submit">
      <div className="submit-head">
        <div>
          <h1 className="page-title">Submit labeled sentence</h1>
          <p className="page-sub">
            Enter one Nepali sentence for <strong>{team_name}</strong>, mark the
            bias categories that apply, then submit.
          </p>
        </div>
        {teamCount !== null && (
          <div className="stat-pill">
            <span className="stat-num">{teamCount}</span>
            <span className="stat-cap">saved</span>
          </div>
        )}
      </div>

      {checking && (
        <div className="submit-overlay">
          <LoadingSpinner label="Running duplicate and PII checks…" />
        </div>
      )}

      <div className="submit-grid">
        <section className="panel">
          <label className="field-label" htmlFor="sentence-text">
            Nepali sentence
          </label>
          <textarea
            id="sentence-text"
            className="textarea nepali textarea-lg"
            placeholder="यहाँ नेपाली वाक्य लेख्नुहोस्…"
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setValidationError("");
            }}
            rows={6}
            disabled={busy}
          />
          <div className="char-counter" aria-live="polite">
            {charCount} {charCount === 1 ? "character" : "characters"}
          </div>

          <div className="source-row">
            <div className="source-field">
              <label className="field-label" htmlFor="source-platform">
                Source platform <span className="opt">optional</span>
              </label>
              <select
                id="source-platform"
                className="input"
                value={platform}
                onChange={(event) => setPlatform(event.target.value)}
                disabled={busy}
              >
                <option value="">—</option>
                {SOURCE_PLATFORMS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <div className="source-field">
              <label className="field-label" htmlFor="source-date">
                Source date <span className="opt">optional</span>
              </label>
              <input
                id="source-date"
                type="date"
                className="input"
                value={date}
                onChange={(event) => setDate(event.target.value)}
                disabled={busy}
              />
            </div>
          </div>
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
                      disabled={busy}
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
                      disabled={busy}
                    />
                    <span>Yes</span>
                  </label>
                </fieldset>
              </div>
            ))}
          </div>
        </section>
      </div>

      {validationError && <div className="alert alert-error">{validationError}</div>}
      {flowError && activeDialog === DIALOG.NONE && (
        <div className="alert alert-error">{flowError}</div>
      )}

      <div className="submit-bar">
        <button
          type="button"
          className="btn btn-ghost"
          onClick={resetForm}
          disabled={busy}
        >
          Clear
        </button>
        <button
          type="button"
          className="btn btn-primary btn-lg"
          disabled={!trimmedText || busy}
          onClick={handleSubmit}
        >
          {checking ? "Checking…" : saving ? "Saving…" : "Submit"}
        </button>
      </div>

      <ConfirmDialog
        open={activeDialog === DIALOG.DUPLICATE}
        title="Duplicate warning"
        message="This sentence looks similar to an existing submission. You can still continue if it is different enough."
        confirmLabel="Continue"
        cancelLabel="Cancel"
        variant="primary"
        busy={saving}
        onCancel={() => setActiveDialog(DIALOG.NONE)}
        onConfirm={() => proceedAfterDuplicate(checkResult)}
      >
        <DuplicateWarningContent duplicate={checkResult?.duplicate} />
      </ConfirmDialog>

      <ConfirmDialog
        open={activeDialog === DIALOG.PII}
        title="Personal information warning"
        message="Possible personal information was detected. Remove sensitive details if possible, or continue if the text is safe to store."
        confirmLabel="Continue"
        cancelLabel="Cancel"
        variant="primary"
        busy={saving}
        onCancel={() => setActiveDialog(DIALOG.NONE)}
        onConfirm={() => saveSubmission(checkResult)}
      >
        <PiiWarningContent pii={checkResult?.pii} />
      </ConfirmDialog>

      <ConfirmDialog
        open={activeDialog === DIALOG.SERVICE_DOWN}
        title="Check service unavailable"
        message={flowError}
        confirmLabel="Continue without check"
        cancelLabel="Cancel"
        variant="primary"
        busy={saving}
        onCancel={() => {
          setActiveDialog(DIALOG.NONE);
          setFlowError("");
        }}
        onConfirm={() => saveSubmission(null)}
      />
    </div>
  );
}
