"""Empirical runner for Phase D Step 3: Run essay skill on 3 topics through the live API."""

import sys
import json
import urllib.request
import urllib.error
import time

API_BASE = "http://localhost:8000"

TOPICS = [
    "Product-market fit and retention",
    "First-week user activation strategies",
    "Pricing and monetization for B2B SaaS",
]

def count_words(text: str) -> int:
    import re
    cleaned = re.sub(r"[#*_`~>\[\]()!-]", " ", text)
    words = [w for w in cleaned.split() if any(c.isalnum() for c in w)]
    return len(words)

def post_json(url: str, data: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    print(f"=== Running Essay Skill Evaluation against {API_BASE} ===")
    results = []

    for idx, topic in enumerate(TOPICS, 1):
        print(f"\n--- [Essay {idx}/3] Topic: {topic} ---")
        t0 = time.time()
        
        # 1. Create Session
        try:
            sess_resp = post_json(f"{API_BASE}/sessions", {"user_metadata": {"eval": "phase_d", "topic": topic}})
            session_id = sess_resp["id"]
            print(f"Created session: {session_id}")
        except Exception as exc:
            print(f"ERROR creating session: {exc}")
            continue

        # 2. Post Essay prompt
        prompt = f"Write an essay about {topic}"
        print(f"Sending prompt: {prompt}")
        
        try:
            msg_resp = post_json(f"{API_BASE}/sessions/{session_id}/messages", {"content": prompt}, timeout=360)
            elapsed = time.time() - t0
            print(f"Response received in {elapsed:.1f}s")
        except Exception as exc:
            print(f"ERROR generating essay: {exc}")
            continue

        artifact = msg_resp.get("artifact")
        message_content = msg_resp.get("message", {}).get("content", "")
        
        essay_text = ""
        report_data = None
        
        if artifact:
            print(f"Artifact received: id={artifact.get('id')} title={artifact.get('title')}")
            essay_text = artifact.get("html", "") or artifact.get("content", "")
            report_data = artifact.get("validation_report")
        else:
            print("No artifact returned directly in message payload. Checking message text...")
            essay_text = message_content

        words = count_words(essay_text)
        print(f"Measured Word Count: {words}")
        
        # Validate using validator module if available
        try:
            from app.skills.validator import validate_essay
            # Fake chunks for source validation if sources not in payload
            sources = msg_resp.get("citations", [])
            # If citations present, construct minimal sources for index checking
            max_s = 10
            fake_sources = [None] * max_s
            report = validate_essay(essay_text, fake_sources)
            print(f"Validator Passed: {report.passed}")
            print(f"Failed Rules: {report.failed_rules}")
            for r in report.rule_results:
                print(f"  - {r.rule_id} ({r.rule_name}): {'PASS' if r.passed else 'FAIL'} | Target: {r.target} | Actual: {r.actual}")
        except Exception as v_err:
            print(f"Validator inspection note: {v_err}")

        results.append({
            "topic": topic,
            "session_id": session_id,
            "elapsed_s": round(elapsed, 1),
            "word_count": words,
            "artifact_present": bool(artifact),
            "validation_report": report_data,
        })

    print("\n=== Summary Table ===")
    print(f"{'Topic':<40} | {'Words':<8} | {'Time (s)':<10} | {'Artifact':<10}")
    print("-" * 75)
    for r in results:
        print(f"{r['topic']:<40} | {r['word_count']:<8} | {r['elapsed_s']:<10} | {str(r['artifact_present']):<10}")

if __name__ == "__main__":
    main()
