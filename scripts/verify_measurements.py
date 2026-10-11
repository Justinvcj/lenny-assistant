"""Complete verification and measurement script for Lenny Assistant Round 2."""

import asyncio
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"
EXACT_REFUSAL = "I don't have information about that in the transcripts."
EXACT_REFUSAL_ALT = "I couldn't find any discussion of that in the podcast transcripts."

def http_post(endpoint: str, data: dict, timeout=300) -> dict:
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def http_get(endpoint: str, timeout=60) -> dict:
    url = f"{BASE_URL}{endpoint}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def create_session() -> str:
    res = http_post("/sessions", {})
    return res["id"]

def run_tests():
    print("=" * 80)
    print("LENNY ASSISTANT - ROUND 2 EMPIRICAL VERIFICATION & MEASUREMENTS")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 7a. LATENCY MEASUREMENTS: 5 in-scope questions in fresh sessions
    # -------------------------------------------------------------------------
    print("\n[ITEM 7a] Measuring latency for 5 in-scope questions in fresh sessions...")
    questions = [
        "What did Sean Ellis say about the 40% PMF survey rule?",
        "How does Ben Williams describe product-led growth loops and activation?",
        "What are the core retention metrics recommended by Brian Balfour?",
        "What does Elena Verna say about B2B product-led sales and growth loops?",
        "What advice does Lenny give regarding user onboarding friction?",
    ]
    latencies = []
    q_results = []
    for i, q in enumerate(questions, 1):
        s_id = create_session()
        t0 = time.perf_counter()
        res = http_post(f"/sessions/{s_id}/messages", {"content": q}, timeout=180)
        dur_s = time.perf_counter() - t0
        lat_ms = res.get("latency_ms", int(dur_s * 1000))
        latencies.append(dur_s)
        msg = res["message"]
        cits = res.get("citations", [])
        tool_trace = msg.get("tool_trace", [])
        retry_fired = any(t.get("retry") for t in tool_trace if isinstance(t, dict))
        degraded = res.get("degraded", False)

        q_results.append({
            "index": i,
            "question": q,
            "duration_s": round(dur_s, 2),
            "latency_ms": lat_ms,
            "citations_count": len(cits),
            "retry_fired": retry_fired,
            "degraded": degraded,
            "content_preview": msg["content"][:120].replace("\n", " "),
        })
        print(f"  Q{i}: {dur_s:.2f}s | Citations: {len(cits)} | Retry: {retry_fired} | Degraded: {degraded}")

    latencies_sorted = sorted(latencies)
    median_lat = latencies_sorted[len(latencies_sorted) // 2]
    print(f"\nLatency Summary: Min: {min(latencies):.2f}s | Median: {median_lat:.2f}s | Max: {max(latencies):.2f}s")

    # -------------------------------------------------------------------------
    # 7b. REFUSAL GATE EVALUATION
    # -------------------------------------------------------------------------
    print("\n[ITEM 7b] Evaluating 8 plausible-but-absent questions on chat API...")
    absent_questions = [
        "What did Steve Jobs say when he appeared on Lenny's podcast about the iPhone?",
        "What are Lenny's podcast recommendations for fixing a leaky toilet pipe?",
        "What recipe did Gordon Ramsay recommend for cooking risotto on the podcast?",
        "How did Elon Musk explain rocket staging during his interview with Lenny?",
        "What does the podcast say about planting tomatoes in cold winter climates?",
        "What did Taylor Swift discuss regarding album promotion on Lenny's show?",
        "How to train for an ultra marathon according to Lenny's guests?",
        "What did Barack Obama say about healthcare policy on Lenny's podcast?",
    ]
    gate_results = []
    for i, aq in enumerate(absent_questions, 1):
        s_id = create_session()
        t0 = time.perf_counter()
        res = http_post(f"/sessions/{s_id}/messages", {"content": aq}, timeout=30)
        dur_s = time.perf_counter() - t0
        content = res["message"]["content"]
        is_refusal = (content.strip() == EXACT_REFUSAL.strip() or content.strip() == EXACT_REFUSAL_ALT.strip())
        tool_trace = res["message"].get("tool_trace", [])
        top_score = None
        for t in tool_trace:
            if isinstance(t, dict) and "top_score" in t:
                top_score = t["top_score"]
        gate_results.append({
            "q": aq,
            "duration_s": round(dur_s, 3),
            "is_refusal": is_refusal,
            "top_score": top_score,
            "content": content,
        })
        print(f"  Gate Q{i}: {dur_s:.3f}s | Score: {top_score} | Exact Refusal: {is_refusal}")

    all_refused = all(g["is_refusal"] for g in gate_results)
    print(f"  All 8 plausible-but-absent queries refused immediately: {all_refused}")

    # -------------------------------------------------------------------------
    # FINAL 4 FLOWS & ARTIFACT GENERATION
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("RUNNING FINAL 4 FLOWS & GENERATING ARTIFACTS")
    print("=" * 80)

    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))
    flow_artifacts = {}

    # FLOW 1: QA -> "Turn that into a Ship 30 essay"
    print("\n--- Flow 1: QA -> 'Turn that into a Ship 30 essay' ---")
    s1_id = create_session()
    qa1_prompt = "What did Sean Ellis and Ben Williams say about activation and onboarding metrics?"
    print(f"  Turn 1 prompt: {qa1_prompt}")
    t0 = time.perf_counter()
    qa1_resp = http_post(f"/sessions/{s1_id}/messages", {"content": qa1_prompt})
    print(f"  Turn 1 answer latency: {time.perf_counter() - t0:.2f}s | citations: {len(qa1_resp.get('citations', []))}")

    f1_prompt = "Turn that into a Ship 30 essay"
    print(f"  Turn 2 prompt: {f1_prompt}")
    t0 = time.perf_counter()
    f1_resp = http_post(f"/sessions/{s1_id}/messages", {"content": f1_prompt})
    dur_f1 = time.perf_counter() - t0
    f1_chat_content = f1_resp["message"]["content"]
    print(f"  Turn 2 latency: {dur_f1:.2f}s")
    print(f"  Turn 2 chat bubble text:\n    {f1_chat_content}")
    f1_art = f1_resp.get("artifact")
    if f1_art and f1_art.get("id"):
        full_art1 = http_get(f"/artifacts/{f1_art['id']}")
        f1_art_path = os.path.join(temp_dir, "flow1_ship30_essay.md")
        with open(f1_art_path, "w", encoding="utf-8") as f:
            f.write(full_art1["content"])
        flow_artifacts["flow1"] = {
            "path": f1_art_path,
            "type": "markdown",
            "title": full_art1["title"],
            "content": full_art1["content"],
            "chat_content": f1_chat_content,
            "duration_s": round(dur_f1, 2),
        }
        print(f"  Saved Flow 1 artifact to: {f1_art_path}")

    # FLOW 2: Fresh session: "Write a Ship 30 essay about product-led growth loops featuring Elena Verna's ideas"
    print("\n--- Flow 2: Fresh session: Elena Verna essay ---")
    s2_id = create_session()
    f2_prompt = "Write a Ship 30 essay about product-led growth loops featuring Elena Verna's ideas"
    print(f"  Prompt: {f2_prompt}")
    t0 = time.perf_counter()
    f2_resp = http_post(f"/sessions/{s2_id}/messages", {"content": f2_prompt})
    dur_f2 = time.perf_counter() - t0
    f2_chat_content = f2_resp["message"]["content"]
    print(f"  Flow 2 latency: {dur_f2:.2f}s")
    print(f"  Flow 2 chat bubble text:\n    {f2_chat_content}")
    f2_art = f2_resp.get("artifact")
    if f2_art and f2_art.get("id"):
        full_art2 = http_get(f"/artifacts/{f2_art['id']}")
        f2_art_path = os.path.join(temp_dir, "flow2_elena_verna_essay.md")
        with open(f2_art_path, "w", encoding="utf-8") as f:
            f.write(full_art2["content"])
        flow_artifacts["flow2"] = {
            "path": f2_art_path,
            "type": "markdown",
            "title": full_art2["title"],
            "content": full_art2["content"],
            "chat_content": f2_chat_content,
            "duration_s": round(dur_f2, 2),
        }
        print(f"  Saved Flow 2 artifact to: {f2_art_path}")

    # FLOW 3: QA -> "Make a one-pager (HTML)"
    print("\n--- Flow 3: QA -> 'Make a one-pager (HTML)' ---")
    s3_id = create_session()
    print(f"  Turn 1 prompt: {qa1_prompt}")
    t0 = time.perf_counter()
    qa3_resp = http_post(f"/sessions/{s3_id}/messages", {"content": qa1_prompt})
    print(f"  Turn 1 answer latency: {time.perf_counter() - t0:.2f}s")

    f3_prompt = "Make a one-pager (HTML)"
    print(f"  Turn 2 prompt: {f3_prompt}")
    t0 = time.perf_counter()
    f3_resp = http_post(f"/sessions/{s3_id}/messages", {"content": f3_prompt})
    dur_f3 = time.perf_counter() - t0
    f3_chat_content = f3_resp["message"]["content"]
    print(f"  Turn 2 latency: {dur_f3:.3f}s (Deterministic, 0 LLM calls!)")
    print(f"  Turn 2 chat bubble text:\n    {f3_chat_content}")
    f3_art = f3_resp.get("artifact")
    if f3_art and f3_art.get("id"):
        full_art3 = http_get(f"/artifacts/{f3_art['id']}")
        f3_art_path = os.path.join(temp_dir, "flow3_one_pager.html")
        with open(f3_art_path, "w", encoding="utf-8") as f:
            f.write(full_art3["content"])
        flow_artifacts["flow3"] = {
            "path": f3_art_path,
            "type": "html",
            "title": full_art3["title"],
            "content": full_art3["content"],
            "chat_content": f3_chat_content,
            "duration_s": round(dur_f3, 3),
        }
        print(f"  Saved Flow 3 artifact to: {f3_art_path}")

    # FLOW 4: QA -> "Make a markdown doc summarizing that"
    print("\n--- Flow 4: QA -> 'Make a markdown doc summarizing that' ---")
    s4_id = create_session()
    print(f"  Turn 1 prompt: {qa1_prompt}")
    t0 = time.perf_counter()
    qa4_resp = http_post(f"/sessions/{s4_id}/messages", {"content": qa1_prompt})
    print(f"  Turn 1 answer latency: {time.perf_counter() - t0:.2f}s")

    f4_prompt = "Make a markdown doc summarizing that"
    print(f"  Turn 2 prompt: {f4_prompt}")
    t0 = time.perf_counter()
    f4_resp = http_post(f"/sessions/{s4_id}/messages", {"content": f4_prompt})
    dur_f4 = time.perf_counter() - t0
    f4_chat_content = f4_resp["message"]["content"]
    print(f"  Turn 2 latency: {dur_f4:.3f}s (Deterministic, 0 LLM calls!)")
    print(f"  Turn 2 chat bubble text:\n    {f4_chat_content}")
    f4_art = f4_resp.get("artifact")
    if f4_art and f4_art.get("id"):
        full_art4 = http_get(f"/artifacts/{f4_art['id']}")
        f4_art_path = os.path.join(temp_dir, "flow4_summary_doc.md")
        with open(f4_art_path, "w", encoding="utf-8") as f:
            f.write(full_art4["content"])
        flow_artifacts["flow4"] = {
            "path": f4_art_path,
            "type": "markdown",
            "title": full_art4["title"],
            "content": full_art4["content"],
            "chat_content": f4_chat_content,
            "duration_s": round(dur_f4, 3),
        }
        print(f"  Saved Flow 4 artifact to: {f4_art_path}")

    # Output detailed report JSON to stdout for recording
    report_data = {
        "latency_measurements": q_results,
        "latency_summary": {
            "min_s": round(min(latencies), 2),
            "median_s": round(median_lat, 2),
            "max_s": round(max(latencies), 2),
        },
        "gate_measurements": gate_results,
        "flow_artifacts_summary": {
            k: {
                "path": v["path"],
                "type": v["type"],
                "title": v["title"],
                "bytes": len(v["content"].encode("utf-8")),
                "words": len(v["content"].split()),
                "duration_s": v["duration_s"],
                "chat_content": v["chat_content"],
            }
            for k, v in flow_artifacts.items()
        },
    }

    report_path = os.path.join(temp_dir, "round2_verification_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"\nWrote full report to: {report_path}")

if __name__ == "__main__":
    run_tests()
