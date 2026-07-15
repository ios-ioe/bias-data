// Offline outbox queue for /submit.
//
// WHAT THIS IS FOR: if the backend (HF Space) or Supabase is unreachable —
// crashed, asleep, network blip, DNS hiccup — a team's submission would
// otherwise just fail and the participant has to remember to retry. Instead,
// we save it to localStorage immediately and keep retrying in the
// background until it succeeds, so nobody loses work mid-event.
//
// WHAT THIS IS NOT: a replacement for the backend. It's per-browser,
// per-device storage — it does NOT sync across a team's other devices, and
// it does NOT survive a cleared browser / different machine. Treat it as a
// short-term shock absorber, not a database. See exportLocalBackup() below
// for a manual last-resort escape hatch if the backend is down for good.

import { submitEntry } from "./api.js";

const QUEUE_KEY = "bias_tool_offline_queue_v1";
const MAX_RETRY_BACKOFF_MS = 60_000;
const BASE_RETRY_BACKOFF_MS = 3_000;
const PERIODIC_SYNC_INTERVAL_MS = 20_000;

/** @typedef {{
 *   client_submission_id: string,
 *   entry: object,
 *   queued_at: string,
 *   attempts: number,
 *   last_error: string | null,
 * }} QueuedSubmission
 */

function readQueue() {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    // Corrupt or inaccessible localStorage (private mode, quota, etc.) —
    // fail safe to an empty queue rather than throwing on every render.
    return [];
  }
}

function writeQueue(queue) {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  } catch (err) {
    console.error("offlineQueue: failed to persist queue (storage full or unavailable)", err);
  }
  notifyListeners(queue);
}

function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  // Fallback for older browsers.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// ---------------------------------------------------------------------------
// Listeners — so UI (e.g. a "Syncing 2 offline submissions…" banner) can
// react without polling.
// ---------------------------------------------------------------------------
const _listeners = new Set();
function notifyListeners(queue) {
  for (const fn of _listeners) fn(queue);
}
export function onQueueChange(fn) {
  _listeners.add(fn);
  fn(readQueue());
  return () => _listeners.delete(fn);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Try to submit immediately; on failure, queue for background retry.
 * Returns { synced: true, id } on immediate success, or
 * { synced: false, client_submission_id } if it was queued instead. */
export async function submitWithFallback(entry) {
  const client_submission_id = uuid();
  const payload = { ...entry, client_submission_id };

  try {
    const result = await submitEntry(payload);
    return { synced: true, id: result.id };
  } catch (err) {
    console.warn("submit failed, queuing offline:", err.message);
    const queue = readQueue();
    queue.push({
      client_submission_id,
      entry: payload,
      queued_at: new Date().toISOString(),
      attempts: 0,
      last_error: String(err.message || err),
    });
    writeQueue(queue);
    scheduleSync();
    return { synced: false, client_submission_id };
  }
}

export function getQueuedCount() {
  return readQueue().length;
}

export function getQueue() {
  return readQueue();
}

/** Attempt to flush every queued submission. Safe to call repeatedly/
 * concurrently — uses client_submission_id so a retry that actually
 * succeeded server-side but lost its response won't create a duplicate
 * row (see backend/database.py insert_submission). */
let _syncing = false;
export async function syncQueue() {
  if (_syncing) return;
  _syncing = true;
  try {
    let queue = readQueue();
    if (queue.length === 0) return;

    const stillQueued = [];
    for (const item of queue) {
      try {
        await submitEntry(item.entry);
        // Success — dropped from the queue.
      } catch (err) {
        stillQueued.push({
          ...item,
          attempts: item.attempts + 1,
          last_error: String(err.message || err),
        });
      }
    }
    writeQueue(stillQueued);

    if (stillQueued.length > 0) {
      scheduleSync(stillQueued[0].attempts);
    }
  } finally {
    _syncing = false;
  }
}

let _retryTimer = null;
function scheduleSync(attempts = 1) {
  if (_retryTimer) clearTimeout(_retryTimer);
  const backoff = Math.min(BASE_RETRY_BACKOFF_MS * 2 ** (attempts - 1), MAX_RETRY_BACKOFF_MS);
  _retryTimer = setTimeout(syncQueue, backoff);
}

/** Call once at app startup: retries on load, on a periodic timer, and
 * whenever the browser regains network connectivity. */
export function startBackgroundSync() {
  syncQueue();
  const interval = setInterval(syncQueue, PERIODIC_SYNC_INTERVAL_MS);
  window.addEventListener("online", syncQueue);
  return () => {
    clearInterval(interval);
    window.removeEventListener("online", syncQueue);
  };
}

/** Last-resort manual escape hatch: download everything still sitting in
 * this browser's local queue as JSON, so it can be handed to an organizer
 * and inserted manually if the backend is down for the rest of the event. */
export function exportLocalBackup() {
  const queue = readQueue();
  const blob = new Blob([JSON.stringify(queue, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `offline-backup-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
