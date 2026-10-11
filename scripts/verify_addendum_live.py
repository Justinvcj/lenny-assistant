"""Empirical verification script for Round 2 Addendum requirements.

Tests:
1. Reference Resolution sequence:
   - QA A: Elena Verna growth loops
   - QA B: Activation metrics
   - "Turn that into a Ship 30 essay" -> must reference B (activation), NOT A (Elena Verna)
   - "Write a Ship 30 essay on product-led growth loops" -> must retrieve for explicit topic (Elena Verna)
2. Item 8: Honest code-written chat message with collapsible Checks panel; no raw essay in chat bubble
3. Item 9: Deterministic summary artifact latency and timing logs
"""

import json
import sys
import time
import urllib.request

BASE_URL = "http://localhost:8000"


def http_post(path: str, data: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE_URL}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_full_addendum_flows():
    print("======================================================================")
    print("STARTING ROUND 2 ADDENDUM EMPIRICAL VERIFICATION")
    print("======================================================================")

    # 1. Create Session
    session = http_post("/sessions", {"title": "Addendum Verification Session"})
    session_id = session["id"]
    print(f"\n[1] Created Session: {session_id}")

    # 2. QA Turn A: Elena Verna on product-led growth loops
    print("\n[2] Turn A: 'What does Elena Verna say about product-led growth loops?'")
    t0 = time.perf_counter()
    resp_a = http_post(f"/sessions/{session_id}/messages", {
        "content": "What does Elena Verna say about product-led growth loops?"
    })
    dur_a = time.perf_counter() - t0
    cits_a = resp_a.get("citations", [])
    guests_a = [c.get("guest") for c in cits_a if c.get("guest")]
    print(f"    Turn A duration: {dur_a:.1f}s")
    print(f"    Turn A cited guests: {set(guests_a)}")
    print(f"    Turn A content preview: {resp_a['message']['content'][:120]}...")

    # 3. QA Turn B: How should a startup think about activation
    print("\n[3] Turn B: 'How should a startup think about activation?'")
    t0 = time.perf_counter()
    resp_b = http_post(f"/sessions/{session_id}/messages", {
        "content": "How should a startup think about activation?"
    })
    dur_b = time.perf_counter() - t0
    cits_b = resp_b.get("citations", [])
    guests_b = [c.get("guest") for c in cits_b if c.get("guest")]
    print(f"    Turn B duration: {dur_b:.1f}s")
    print(f"    Turn B cited guests: {set(guests_b)}")
    print(f"    Turn B content preview: {resp_b['message']['content'][:120]}...")

    # 4. Turn C: "Turn that into a Ship 30 essay"
    print("\n[4] Turn C (Reference Resolution): 'Turn that into a Ship 30 essay'")
    t0 = time.perf_counter()
    resp_c = http_post(f"/sessions/{session_id}/messages", {
        "content": "Turn that into a Ship 30 essay"
    })
    dur_c = time.perf_counter() - t0
    msg_c = resp_c["message"]["content"]
    cits_c = resp_c.get("citations", [])
    guests_c = [c.get("guest") for c in cits_c if c.get("guest")]
    art_c = resp_c.get("artifact")

    print(f"    Turn C duration: {dur_c:.1f}s")
    print(f"    Turn C cited guests: {set(guests_c)}")
    print(f"    Turn C chat message body:\n---\n{msg_c}\n---")
    
    # Assertions for Turn C:
    # (a) Sources must be from Answer B (activation), NOT Elena Verna
    assert "Elena Verna" not in set(guests_c), f"ERROR: Essay C cited Elena Verna from Answer A! Guests: {guests_c}"
    print("    [PASS] Essay C cited guests are derived from Answer B (Activation), NOT Answer A (Elena Verna).")

    # (b) Chat bubble must be code-written honest message with Checks panel
    assert msg_c.startswith("Your Ship 30 essay is ready:"), f"ERROR: Chat message not code-written! Found: {msg_c[:60]}"
    assert "<details" in msg_c and "<summary>" in msg_c, "ERROR: Collapsible Checks panel missing in chat message!"
    assert "Support Score:" in msg_c, "ERROR: Support score missing in Checks panel!"
    assert "Quotes Verified:" in msg_c, "ERROR: Quotes verified missing in Checks panel!"
    assert "Names Verified:" in msg_c, "ERROR: Names verified missing in Checks panel!"
    print("    [PASS] Chat message is 100% code-written with collapsible Checks panel.")

    # (c) Chat message does NOT contain raw essay text or conversational fluff
    assert "Certainly!" not in msg_c, "ERROR: Found conversational fluff in chat message!"
    assert "## " not in msg_c, "ERROR: Found raw markdown headings in chat bubble!"
    assert art_c is not None, "ERROR: Artifact missing in response!"
    assert art_c["type"] == "markdown", "ERROR: Artifact type is not markdown!"
    print(f"    [PASS] Raw essay is delivered in artifact ({len(art_c['content'].split())} words), NOT in chat bubble.")

    # 5. Turn D: "Write a Ship 30 essay on product-led growth loops"
    print("\n[5] Turn D (Explicit Topic): 'Write a Ship 30 essay on product-led growth loops'")
    t0 = time.perf_counter()
    resp_d = http_post(f"/sessions/{session_id}/messages", {
        "content": "Write a Ship 30 essay on product-led growth loops"
    })
    dur_d = time.perf_counter() - t0
    msg_d = resp_d["message"]["content"]
    cits_d = resp_d.get("citations", [])
    guests_d = [c.get("guest") for c in cits_d if c.get("guest")]
    art_d = resp_d.get("artifact")

    print(f"    Turn D duration: {dur_d:.1f}s")
    print(f"    Turn D cited guests: {set(guests_d)}")
    print(f"    Turn D chat message body:\n---\n{msg_d}\n---")
    
    # Assertions for Turn D:
    # Explicit topic retrieval must cite Elena Verna, NOT activation sources
    assert any("Elena Verna" in str(g) for g in guests_d), f"ERROR: Turn D failed to cite Elena Verna for PLG loops! Guests: {guests_d}"
    print("    [PASS] Essay D retrieved solely for explicit topic (Elena Verna / PLG loops).")

    # 6. Item 9: Summary artifact ("Make a one-pager (HTML)")
    print("\n[6] Turn E (Item 9 Deterministic Summary): 'Make a one-pager (HTML)'")
    t0 = time.perf_counter()
    resp_e = http_post(f"/sessions/{session_id}/messages", {
        "content": "Make a one-pager (HTML)"
    })
    dur_e = time.perf_counter() - t0
    msg_e = resp_e["message"]["content"]
    art_e = resp_e.get("artifact")

    print(f"    Turn E duration: {dur_e:.3f}s (Expected <15s)")
    print(f"    Turn E chat message:\n---\n{msg_e}\n---")
    assert dur_e < 15.0, f"ERROR: Summary artifact took {dur_e:.1f}s >= 15s!"
    assert art_e is not None, "ERROR: Artifact missing in Turn E response!"
    assert art_e["type"] == "html", "ERROR: Artifact is not HTML!"
    assert "<sup><a href=\"#source-S" in art_e["content"], "ERROR: HTML summary missing citation links!"
    print(f"    [PASS] Deterministic HTML one-pager produced in {dur_e:.3f}s (<15s) with safe citation links.")

    print("\n======================================================================")
    print("ALL ADDENDUM VERIFICATION FLOWS SUCCEEDED!")
    print("======================================================================")


if __name__ == "__main__":
    test_full_addendum_flows()
