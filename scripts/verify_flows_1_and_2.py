"""Run Flows 1, 2, 3, 4 end-to-end and record all artifact properties."""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"

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

def run():
    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))
    print(f"Output directory: {temp_dir}", flush=True)

    qa1_prompt = "What did Sean Ellis and Ben Williams say about activation and onboarding metrics?"

    # =========================================================================
    # FLOW 1: Turn that into a Ship 30 essay
    # =========================================================================
    print("\n--- FLOW 1: QA -> 'Turn that into a Ship 30 essay' ---", flush=True)
    s1_id = create_session()
    t0 = time.perf_counter()
    qa1_resp = http_post(f"/sessions/{s1_id}/messages", {"content": qa1_prompt})
    print(f"  Turn 1 latency: {time.perf_counter() - t0:.2f}s | citations: {len(qa1_resp.get('citations', []))}", flush=True)

    f1_prompt = "Turn that into a Ship 30 essay"
    print(f"  Turn 2 prompt: {f1_prompt}", flush=True)
    t0 = time.perf_counter()
    f1_resp = http_post(f"/sessions/{s1_id}/messages", {"content": f1_prompt})
    dur_f1 = time.perf_counter() - t0
    f1_chat_content = f1_resp["message"]["content"]
    print(f"  Turn 2 latency: {dur_f1:.2f}s", flush=True)
    print(f"  Turn 2 chat bubble text:\n    {f1_chat_content}", flush=True)
    f1_art = f1_resp.get("artifact")
    if f1_art and f1_art.get("id"):
        full_art1 = http_get(f"/artifacts/{f1_art['id']}")
        f1_art_path = os.path.join(temp_dir, "flow1_ship30_essay.md")
        with open(f1_art_path, "w", encoding="utf-8") as f:
            f.write(full_art1["content"])
        print(f"  Saved Flow 1 artifact to: {f1_art_path} ({len(full_art1['content'])} bytes)", flush=True)

    # =========================================================================
    # FLOW 2: Fresh session: Elena Verna essay
    # =========================================================================
    print("\n--- FLOW 2: Fresh session: Elena Verna essay ---", flush=True)
    s2_id = create_session()
    f2_prompt = "Write a Ship 30 essay about product-led growth loops featuring Elena Verna's ideas"
    print(f"  Prompt: {f2_prompt}", flush=True)
    t0 = time.perf_counter()
    f2_resp = http_post(f"/sessions/{s2_id}/messages", {"content": f2_prompt})
    dur_f2 = time.perf_counter() - t0
    f2_chat_content = f2_resp["message"]["content"]
    print(f"  Flow 2 latency: {dur_f2:.2f}s", flush=True)
    print(f"  Flow 2 chat bubble text:\n    {f2_chat_content}", flush=True)
    f2_art = f2_resp.get("artifact")
    if f2_art and f2_art.get("id"):
        full_art2 = http_get(f"/artifacts/{f2_art['id']}")
        f2_art_path = os.path.join(temp_dir, "flow2_elena_verna_essay.md")
        with open(f2_art_path, "w", encoding="utf-8") as f:
            f.write(full_art2["content"])
        print(f"  Saved Flow 2 artifact to: {f2_art_path} ({len(full_art2['content'])} bytes)", flush=True)

    # =========================================================================
    # FLOW 3: HTML One-pager
    # =========================================================================
    print("\n--- FLOW 3: QA -> 'Make a one-pager (HTML)' ---", flush=True)
    s3_id = create_session()
    t0 = time.perf_counter()
    qa3_resp = http_post(f"/sessions/{s3_id}/messages", {"content": qa1_prompt})
    print(f"  Turn 1 latency: {time.perf_counter() - t0:.2f}s", flush=True)
    t0 = time.perf_counter()
    f3_resp = http_post(f"/sessions/{s3_id}/messages", {"content": "Make a one-pager (HTML)"})
    dur_f3 = time.perf_counter() - t0
    f3_chat_content = f3_resp["message"]["content"]
    print(f"  Turn 2 latency: {dur_f3:.3f}s", flush=True)
    print(f"  Turn 2 chat bubble text:\n    {f3_chat_content}", flush=True)
    f3_art = f3_resp.get("artifact")
    if f3_art and f3_art.get("id"):
        full_art3 = http_get(f"/artifacts/{f3_art['id']}")
        f3_art_path = os.path.join(temp_dir, "flow3_one_pager.html")
        with open(f3_art_path, "w", encoding="utf-8") as f:
            f.write(full_art3["content"])
        print(f"  Saved Flow 3 artifact to: {f3_art_path} ({len(full_art3['content'])} bytes)", flush=True)

    # =========================================================================
    # FLOW 4: Markdown Doc
    # =========================================================================
    print("\n--- FLOW 4: QA -> 'Make a markdown doc summarizing that' ---", flush=True)
    s4_id = create_session()
    t0 = time.perf_counter()
    qa4_resp = http_post(f"/sessions/{s4_id}/messages", {"content": qa1_prompt})
    print(f"  Turn 1 latency: {time.perf_counter() - t0:.2f}s", flush=True)
    t0 = time.perf_counter()
    f4_resp = http_post(f"/sessions/{s4_id}/messages", {"content": "Make a markdown doc summarizing that"})
    dur_f4 = time.perf_counter() - t0
    f4_chat_content = f4_resp["message"]["content"]
    print(f"  Turn 2 latency: {dur_f4:.3f}s", flush=True)
    print(f"  Turn 2 chat bubble text:\n    {f4_chat_content}", flush=True)
    f4_art = f4_resp.get("artifact")
    if f4_art and f4_art.get("id"):
        full_art4 = http_get(f"/artifacts/{f4_art['id']}")
        f4_art_path = os.path.join(temp_dir, "flow4_summary_doc.md")
        with open(f4_art_path, "w", encoding="utf-8") as f:
            f.write(full_art4["content"])
        print(f"  Saved Flow 4 artifact to: {f4_art_path} ({len(full_art4['content'])} bytes)", flush=True)

    print("\nAll 4 flows finished successfully!", flush=True)

if __name__ == "__main__":
    run()
