#!/usr/bin/env python3
"""
Pre-event smoke test — run this the morning of the event (and any time
you're unsure things are alive) instead of manually clicking through the UI.

Usage:
    python3 scripts/smoke_test.py --backend https://YOUR-BACKEND.hf.space \
        --embedder https://YOUR-EMBEDDER.hf.space --access-code TESTCODE

--embedder is optional (only if you deployed the split-embedder setup).
--access-code should be a real team access code from your seeded/test data
(create one via the admin Teams tab first if you don't have one) — this
script deliberately does NOT create data for you, so it never pollutes
your real submissions table with test rows beyond one harmless check call.

Exit code is 0 if everything passed, 1 if anything failed — safe to use
in a CI job or a pre-event checklist script.
"""

import argparse
import sys
import time

import httpx

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"


def check(label: str, ok: bool, detail: str = "", warn_only: bool = False) -> bool:
    tag = WARN if (warn_only and not ok) else (PASS if ok else FAIL)
    print(f"  [{tag}] {label}" + (f" — {detail}" if detail else ""))
    return ok or warn_only


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True, help="Main backend Space URL")
    parser.add_argument("--embedder", default=None, help="Embedder Space URL (if split-deployed)")
    parser.add_argument("--access-code", default=None, help="A real team access code to test login/submit with")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    backend = args.backend.rstrip("/")
    all_ok = True
    client = httpx.Client(timeout=args.timeout)

    print(f"\n=== 1. Backend health ({backend}) ===")
    try:
        t0 = time.monotonic()
        resp = client.get(f"{backend}/health")
        elapsed = time.monotonic() - t0
        ok = resp.status_code == 200
        all_ok &= check("GET /health returns 200", ok, f"status={resp.status_code}")
        if ok:
            data = resp.json()
            all_ok &= check("secrets_configured", data.get("secrets_configured") is True)
            check(
                "embedder configured/reachable (optional — ok if not using one)",
                data.get("embedder_configured") is not True or data.get("embedder_reachable") is True,
                f"embedding_mode={data.get('embedding_mode')}",
                warn_only=True,
            )
            check(
                "responded quickly (not a cold start)",
                elapsed < 3.0,
                f"{elapsed:.1f}s — if slow, this Space was likely asleep; ping it again in ~30s",
                warn_only=True,
            )
            if data.get("embedding_mode") == "remote":
                check(
                    "embedder_reachable",
                    data.get("embedder_reachable") is True,
                    "remote embedder configured but not reachable right now — checks will run in fuzzy-only degraded mode",
                    warn_only=True,
                )
    except Exception as exc:
        all_ok = False
        check("GET /health reachable at all", False, str(exc))

    if args.embedder:
        embedder = args.embedder.rstrip("/")
        print(f"\n=== 2. Embedder health ({embedder}) ===")
        try:
            resp = client.get(f"{embedder}/health")
            ok = resp.status_code == 200
            all_ok &= check("GET /health returns 200", ok, f"status={resp.status_code}")
            if ok:
                all_ok &= check("model_loaded", resp.json().get("model_loaded") is True)
        except Exception as exc:
            all_ok = False
            check("GET /health reachable at all", False, str(exc))

    token = None
    if args.access_code:
        print("\n=== 3. Login ===")
        try:
            resp = client.post(f"{backend}/login", json={"access_code": args.access_code})
            ok = resp.status_code == 200
            all_ok &= check("POST /login returns 200", ok, f"status={resp.status_code} body={resp.text[:200]}")
            if ok:
                token = resp.json().get("token")
                all_ok &= check("received a session token", bool(token))
        except Exception as exc:
            all_ok = False
            check("POST /login reachable at all", False, str(exc))
    else:
        print("\n=== 3. Login — SKIPPED (no --access-code provided) ===")

    if token:
        headers = {"Authorization": f"Bearer {token}"}

        print("\n=== 4. /check-submission (the CPU-heavy endpoint) ===")
        try:
            t0 = time.monotonic()
            resp = client.post(
                f"{backend}/check-submission",
                json={"team_id": "smoke-test", "text": "यो एउटा परीक्षण वाक्य हो।"},
                headers=headers,
            )
            elapsed = time.monotonic() - t0
            ok = resp.status_code == 200
            all_ok &= check("POST /check-submission returns 200", ok, f"status={resp.status_code}")
            check(
                "responded within 5s",
                elapsed < 5.0,
                f"{elapsed:.1f}s — if this is slow under no load, expect worse under 100 concurrent participants",
                warn_only=True,
            )
        except Exception as exc:
            all_ok = False
            check("POST /check-submission reachable at all", False, str(exc))

        print("\n=== 5. /my-count (confirms token + DB read work) ===")
        try:
            resp = client.get(f"{backend}/my-count", headers=headers)
            ok = resp.status_code == 200
            all_ok &= check("GET /my-count returns 200", ok, f"status={resp.status_code}")
        except Exception as exc:
            all_ok = False
            check("GET /my-count reachable at all", False, str(exc))

        print(
            "\n(Not calling /submit — this script deliberately never writes real "
            "rows. Do one manual test submission through the UI to fully confirm "
            "the write path.)"
        )
    else:
        print("\n=== 4/5. SKIPPED (no session token — provide --access-code) ===")

    print("\n" + ("=" * 40))
    print("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED — see above")
    print("=" * 40 + "\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
