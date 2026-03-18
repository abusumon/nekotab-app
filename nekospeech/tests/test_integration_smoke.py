"""
nekospeech integration smoke test.

Run against a local Docker stack to verify end-to-end wiring:

    python nekospeech/tests/test_integration_smoke.py --base-url http://localhost

Requires: httpx (pip install httpx)
"""

import argparse
import json
import sys
import time

try:
    import httpx
except ImportError:
    sys.exit("httpx is required.  Install with:  pip install httpx")


# ── Helpers ──────────────────────────────────────────────────────────────

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []


def report(step_name, passed, elapsed_ms, detail=""):
    tag = PASS if passed else FAIL
    line = f"  [{tag}] {step_name}  ({elapsed_ms:.0f} ms)"
    if detail:
        line += f"  — {detail}"
    print(line)
    results.append(passed)


def timed_request(client, method, url, **kwargs):
    """Execute request and return (response, elapsed_ms). Returns (None, elapsed) on error."""
    start = time.perf_counter()
    try:
        resp = getattr(client, method)(url, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        return resp, elapsed
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        print(f"    ERROR: {exc}")
        return None, elapsed


# ── Steps ────────────────────────────────────────────────────────────────

def step1_health(client, base):
    """GET /api/ie/health → expect 200"""
    resp, ms = timed_request(client, "get", f"{base}/api/ie/health")
    passed = resp is not None and resp.status_code == 200
    report("Step 1 — GET /api/ie/health", passed, ms,
           f"status={resp.status_code}" if resp else "no response")
    return passed


def step2_find_tournament(client, base):
    """Find the first tournament_id from the Django API (or fall back to 1)."""
    resp, ms = timed_request(client, "get", f"{base}/api/v1/tournaments",
                             headers={"Accept": "application/json"})
    tournament_id = 1
    if resp is not None and resp.status_code == 200:
        try:
            data = resp.json()
            # DRF list response may be paginated (object with 'results') or a plain list
            items = data.get("results", data) if isinstance(data, dict) else data
            if items:
                tournament_id = items[0].get("id", items[0].get("pk", 1))
        except Exception:
            pass
    passed = resp is not None and resp.status_code in (200, 301, 302, 404)
    report("Step 2 — Find tournament_id", passed, ms,
           f"tournament_id={tournament_id}")
    return passed, tournament_id


def step3_create_event(client, base, tournament_id, token):
    """POST /api/ie/events/ → create Oratory event"""
    payload = {
        "tournament_id": tournament_id,
        "name": "Smoke Test Oratory",
        "abbreviation": "SMOKE",
        "event_type": "ORATORY",
        "num_rounds": 3,
        "room_size": 6,
        "tiebreak_method": "TRUNC",
    }
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp, ms = timed_request(client, "post", f"{base}/api/ie/events/",
                             content=json.dumps(payload), headers=headers)
    event_id = None
    if resp is not None and resp.status_code in (200, 201):
        try:
            event_id = resp.json().get("id")
        except Exception:
            pass
    passed = resp is not None and resp.status_code in (200, 201) and event_id is not None
    report("Step 3 — POST /api/ie/events/ (create Oratory)", passed, ms,
           f"event_id={event_id}" if event_id else
           f"status={resp.status_code}" if resp else "no response")
    return passed, event_id


def step4_bulk_entries(client, base, event_id, token):
    """POST /api/ie/entries/bulk/ → register 12 test entries (2/school × 6 schools)"""
    entries = []
    for school_idx in range(1, 7):
        for speaker_idx in range(1, 3):
            entries.append({
                "event_id": event_id,
                "speaker_id": (school_idx - 1) * 2 + speaker_idx,
            })
    payload = {"event_id": event_id, "entries": entries}
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp, ms = timed_request(client, "post", f"{base}/api/ie/entries/bulk/",
                             content=json.dumps(payload), headers=headers)
    passed = resp is not None and resp.status_code in (200, 201)
    detail = f"status={resp.status_code}" if resp else "no response"
    if passed:
        try:
            detail += f", created={len(resp.json().get('created', resp.json()))}"
        except Exception:
            pass
    report("Step 4 — POST /api/ie/entries/bulk/ (12 entries)", passed, ms, detail)
    return passed


def step5_generate_draw(client, base, event_id, token):
    """POST /api/ie/draw/generate/ with round_number=1"""
    payload = {"event_id": event_id, "round_number": 1}
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp, ms = timed_request(client, "post", f"{base}/api/ie/draw/generate/",
                             content=json.dumps(payload), headers=headers)
    passed = resp is not None and resp.status_code in (200, 201)
    room_id = None
    if passed:
        try:
            body = resp.json()
            rooms = body.get("rooms", body) if isinstance(body, dict) else body
            if rooms and isinstance(rooms, list):
                room_id = rooms[0].get("id")
                # Verify no two same-school entries in a room
                for room in rooms:
                    institutions = [e.get("institution_id") for e in room.get("entries", [])]
                    if len(institutions) != len(set(institutions)):
                        passed = False
                        detail = "same-school conflict detected!"
                        break
        except Exception:
            pass
    report("Step 5 — POST /api/ie/draw/generate/ (round 1)", passed, ms,
           f"room_id={room_id}" if room_id else
           f"status={resp.status_code}" if resp else "no response")
    return passed, room_id


def step6_submit_ballot(client, base, room_id, token):
    """POST /api/ie/ballots/submit/ for one room"""
    # Create plausible ballot data (6 entries, ranks 1-6)
    ballot_results = []
    for rank in range(1, 7):
        ballot_results.append({
            "entry_id": rank,  # placeholder; may not match real IDs
            "rank": rank,
            "speaker_points": round(25.0 + (6 - rank) * 0.5, 2),
        })
    payload = {"room_id": room_id, "results": ballot_results}
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp, ms = timed_request(client, "post", f"{base}/api/ie/ballots/submit/",
                             content=json.dumps(payload), headers=headers)
    passed = resp is not None and resp.status_code in (200, 201)
    report("Step 6 — POST /api/ie/ballots/submit/", passed, ms,
           f"status={resp.status_code}" if resp else "no response")
    return passed


def step7_standings(client, base, event_id, token):
    """GET /api/ie/standings/{event_id}/ → verify structure"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp, ms = timed_request(client, "get",
                             f"{base}/api/ie/standings/{event_id}/",
                             headers=headers)
    passed = resp is not None and resp.status_code == 200
    if passed:
        try:
            body = resp.json()
            has_entries = "entries" in body or isinstance(body, list)
            passed = has_entries
        except Exception:
            passed = False
    report("Step 7 — GET /api/ie/standings/{event_id}/", passed, ms,
           f"status={resp.status_code}" if resp else "no response")
    return passed


def step8_health_again(client, base):
    """GET /api/ie/health again → expect 200"""
    resp, ms = timed_request(client, "get", f"{base}/api/ie/health")
    passed = resp is not None and resp.status_code == 200
    report("Step 8 — GET /api/ie/health (again)", passed, ms,
           f"status={resp.status_code}" if resp else "no response")
    return passed


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="nekospeech integration smoke test")
    parser.add_argument("--base-url", default="http://localhost",
                        help="Base URL of the running stack (default: http://localhost)")
    parser.add_argument("--token", default="",
                        help="JWT token for authenticated requests (optional)")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = args.token

    print(f"\nnekospeech smoke test against {base}\n{'=' * 50}\n")

    client = httpx.Client(timeout=30.0, follow_redirects=True)

    try:
        # Step 1
        step1_health(client, base)

        # Step 2
        _, tournament_id = step2_find_tournament(client, base)

        # Step 3
        ok, event_id = step3_create_event(client, base, tournament_id, token)
        if not ok or event_id is None:
            print("\n  ⚠ Cannot continue without event_id. Skipping steps 4-7.\n")
            step8_health_again(client, base)
        else:
            # Step 4
            step4_bulk_entries(client, base, event_id, token)

            # Step 5
            ok5, room_id = step5_generate_draw(client, base, event_id, token)

            # Step 6
            if ok5 and room_id:
                step6_submit_ballot(client, base, room_id, token)
            else:
                print("  [SKIP] Step 6 — no room_id from draw generation")
                results.append(False)

            # Step 7
            step7_standings(client, base, event_id, token)

            # Step 8
            step8_health_again(client, base)
    finally:
        client.close()

    # Summary
    total = len(results)
    passed = sum(results)
    failed = total - passed
    print(f"\n{'=' * 50}")
    print(f"  {passed}/{total} passed, {failed} failed\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
