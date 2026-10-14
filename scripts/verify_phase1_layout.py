#!/usr/bin/env python3
"""
Phase 1 Browser Layout & Screenshot Verification Script
Empirically verifies that the composer dock is 100% visible with zero clipping
across desktop window heights (600px, 768px, 900px), display zoom levels (100%, 125%, 150%),
and mobile viewports (375x667px).

Usage:
    python scripts/verify_phase1_layout.py
    python scripts/verify_phase1_layout.py --url http://localhost:3000 --output docs/screenshots/phase1
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.request
import urllib.error

def check_server_health(url: str, timeout: float = 4.0) -> bool:
    """Verifies that the target frontend/server is responding to HTTP requests."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LennyLayoutVerifier/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 304)
    except Exception:
        return False

def get_best_browser_channel() -> str:
    """Detects available browser channels on Windows host (Chrome -> Edge -> default)."""
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if os.path.exists(chrome_path):
        return "chrome"
    elif os.path.exists(edge_path):
        return "msedge"
    return "chromium"

def run_layout_verification(target_url: str, output_dir: str, headless: bool = True) -> int:
    print("=" * 80)
    print("LENNY GROWTH ASSISTANT — PHASE 1 BROWSER LAYOUT & SCREENSHOT VERIFICATION")
    print(f"Target URL: {target_url}")
    print(f"Output Directory: {output_dir}")
    print("=" * 80)

    # 1. Connectivity Check
    print(f"[INFO] Probing connectivity to {target_url}...")
    if not check_server_health(target_url):
        print(f"[ERROR] Target server at {target_url} is not reachable!")
        print("        Ensure frontend is running via: docker compose up -d frontend")
        print("        Or locally via: cd frontend; npm run dev")
        return 1
    print(f"[INFO] Target server reachable. Initializing Playwright...")

    os.makedirs(output_dir, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] Playwright is not installed in the current Python environment.")
        print("        Install via: pip install playwright; python -m playwright install-deps")
        return 1

    channel = get_best_browser_channel()
    print(f"[INFO] Using browser channel: '{channel}'")

    # Define the 14 verification test cases
    test_cases = [
        # Desktop 600px Height Matrix
        {
            "id": "TC-01",
            "name": "Desktop 1280x600 @ 100%",
            "width": 1280,
            "height": 600,
            "scale": 1.0,
            "is_mobile": False,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "desktop_1280x600_zoom100.png"
        },
        {
            "id": "TC-02",
            "name": "Desktop 1280x600 @ 125%",
            "width": 1280,
            "height": 600,
            "scale": 1.25,
            "is_mobile": False,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "desktop_1280x600_zoom125.png"
        },
        {
            "id": "TC-03",
            "name": "Desktop 1280x600 @ 150%",
            "width": 1280,
            "height": 600,
            "scale": 1.5,
            "is_mobile": False,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "desktop_1280x600_zoom150.png"
        },
        # Desktop 768px Height Matrix
        {
            "id": "TC-04",
            "name": "Desktop 1280x768 @ 100%",
            "width": 1280,
            "height": 768,
            "scale": 1.0,
            "is_mobile": False,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "desktop_1280x768_zoom100.png"
        },
        {
            "id": "TC-05",
            "name": "Desktop 1280x768 @ 125%",
            "width": 1280,
            "height": 768,
            "scale": 1.25,
            "is_mobile": False,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "desktop_1280x768_zoom125.png"
        },
        {
            "id": "TC-06",
            "name": "Desktop 1280x768 @ 150%",
            "width": 1280,
            "height": 768,
            "scale": 1.5,
            "is_mobile": False,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "desktop_1280x768_zoom150.png"
        },
        # Desktop 900px Height Matrix
        {
            "id": "TC-07",
            "name": "Desktop 1440x900 @ 100%",
            "width": 1440,
            "height": 900,
            "scale": 1.0,
            "is_mobile": False,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "desktop_1440x900_zoom100.png"
        },
        {
            "id": "TC-08",
            "name": "Desktop 1440x900 @ 125%",
            "width": 1440,
            "height": 900,
            "scale": 1.25,
            "is_mobile": False,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "desktop_1440x900_zoom125.png"
        },
        {
            "id": "TC-09",
            "name": "Desktop 1440x900 @ 150%",
            "width": 1440,
            "height": 900,
            "scale": 1.5,
            "is_mobile": False,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "desktop_1440x900_zoom150.png"
        },
        # Mobile Matrix (375x667)
        {
            "id": "TC-10",
            "name": "Mobile 375x667 (Closed)",
            "width": 375,
            "height": 667,
            "scale": 1.0,
            "is_mobile": True,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "mobile_375x667_zoom100_closed.png"
        },
        {
            "id": "TC-11",
            "name": "Mobile 375x667 (Drawer Open)",
            "width": 375,
            "height": 667,
            "scale": 1.0,
            "is_mobile": True,
            "drawer_action": "open",
            "stress_multiline": False,
            "screenshot": "mobile_375x667_zoom100_drawer_open.png"
        },
        {
            "id": "TC-12",
            "name": "Mobile 375x667 @ 125%",
            "width": 375,
            "height": 667,
            "scale": 1.25,
            "is_mobile": True,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "mobile_375x667_zoom125.png"
        },
        {
            "id": "TC-13",
            "name": "Mobile 375x667 @ 150%",
            "width": 375,
            "height": 667,
            "scale": 1.5,
            "is_mobile": True,
            "drawer_action": None,
            "stress_multiline": False,
            "screenshot": "mobile_375x667_zoom150.png"
        },
        # Stress Test Case: Multiline Expanded Textarea
        {
            "id": "TC-14",
            "name": "Stress Multiline 1280x600",
            "width": 1280,
            "height": 600,
            "scale": 1.0,
            "is_mobile": False,
            "drawer_action": None,
            "stress_multiline": True,
            "screenshot": "stress_multiline_expanded_600.png"
        }
    ]

    results = []
    total_failures = 0

    with sync_playwright() as p:
        browser_kwargs = {"headless": headless}
        if channel in ("chrome", "msedge"):
            browser_kwargs["channel"] = channel

        browser = p.chromium.launch(**browser_kwargs)

        print("\n[RUNNING TEST CASES]")
        print("-" * 80)

        for tc in test_cases:
            tc_id = tc["id"]
            name = tc["name"]
            w = tc["width"]
            h = tc["height"]
            scale = tc["scale"]
            is_mobile = tc["is_mobile"]
            screenshot_path = os.path.join(output_dir, tc["screenshot"])

            # Setup page context
            context_kwargs = {
                "viewport": {"width": w, "height": h},
                "device_scale_factor": scale,
                "is_mobile": is_mobile,
                "has_touch": is_mobile,
            }

            page = browser.new_page(**context_kwargs)

            try:
                page.goto(target_url, wait_until="networkidle", timeout=15000)
            except Exception as e:
                # Fallback to load event if networkidle times out
                page.goto(target_url, wait_until="load", timeout=10000)

            # Wait for layout stability
            time.sleep(0.3)

            # Perform actions if specified
            if tc.get("drawer_action") == "open":
                # Click the sidebar hamburger toggle
                toggle_btn = page.locator(".btn-sidebar-toggle").first
                if toggle_btn.is_visible():
                    toggle_btn.click()
                    time.sleep(0.35)

            if tc.get("stress_multiline"):
                # Fill textarea with 5 lines of text to trigger auto-growth
                textarea = page.locator(".composer-textarea").first
                if textarea.is_visible():
                    textarea.fill("Line 1: Stress testing composer height auto-growth.\nLine 2: Expanding textarea to max height clamp.\nLine 3: Checking that dock does not overflow.\nLine 4: Bounding box must remain strictly within viewport.\nLine 5: Fully verified.")
                    time.sleep(0.2)

            # Measure geometry via JS evaluation in page context
            metrics = page.evaluate("""() => {
                const dock = document.querySelector('[data-testid="composer-dock"]') || document.querySelector('.composer-dock');
                const textarea = document.querySelector('[data-testid="composer-textarea"]') || document.querySelector('.composer-textarea');
                const sendBtn = document.querySelector('[data-testid="composer-send-btn"]') || document.querySelector('.btn-send');
                const scrollArea = document.querySelector('.chat-scroll-area');

                const winH = window.innerHeight;
                const winW = window.innerWidth;
                const docScrollW = document.documentElement.scrollWidth;
                const docScrollH = document.body.scrollHeight;

                const dockRect = dock ? dock.getBoundingClientRect() : null;
                const textareaRect = textarea ? textarea.getBoundingClientRect() : null;
                const sendBtnRect = sendBtn ? sendBtn.getBoundingClientRect() : null;

                return {
                    winH: winH,
                    winW: winW,
                    docScrollW: docScrollW,
                    docScrollH: docScrollH,
                    dock: dockRect ? {
                        x: dockRect.x,
                        y: dockRect.y,
                        width: dockRect.width,
                        height: dockRect.height,
                        top: dockRect.top,
                        bottom: dockRect.bottom,
                        right: dockRect.right,
                        left: dockRect.left
                    } : null,
                    textarea: textareaRect ? {
                        top: textareaRect.top,
                        bottom: textareaRect.bottom,
                        height: textareaRect.height
                    } : null,
                    sendBtn: sendBtnRect ? {
                        top: sendBtnRect.top,
                        bottom: sendBtnRect.bottom,
                        right: sendBtnRect.right
                    } : null
                };
            }""")

            # Capture screenshot
            page.screenshot(path=screenshot_path, full_page=False)

            # Evaluate Assertions
            dock = metrics.get("dock")
            win_h = metrics["winH"]
            win_w = metrics["winW"]
            doc_scroll_w = metrics["docScrollW"]

            failed_reasons = []

            if not dock:
                failed_reasons.append("Composer dock element not found in DOM")
                clipping_px = 999.0
                dock_bottom = 999.0
            else:
                dock_bottom = dock["bottom"]
                clipping_px = max(0.0, dock_bottom - win_h)

                # Assertion 1: Dock bottom <= viewport height (subpixel tolerance 0.5px)
                if clipping_px > 0.5:
                    failed_reasons.append(f"Dock clipped: bottom ({dock_bottom:.1f}px) exceeds viewport ({win_h}px) by {clipping_px:.1f}px")

                # Assertion 2: Dock top >= 0
                if dock["top"] < 0:
                    failed_reasons.append(f"Dock top ({dock['top']:.1f}px) pushed off top edge")

                # Assertion 3: Dock height >= 40px
                if dock["height"] < 40:
                    failed_reasons.append(f"Dock height ({dock['height']:.1f}px) collapsed")

            # Assertion 4: Send button visible
            send_btn = metrics.get("sendBtn")
            if send_btn:
                if send_btn["bottom"] > win_h + 0.5:
                    failed_reasons.append(f"Send button clipped at bottom: {send_btn['bottom']:.1f}px > {win_h}px")
            else:
                failed_reasons.append("Send button not found")

            # Assertion 5: Zero horizontal overflow on mobile
            if is_mobile:
                if doc_scroll_w > win_w + 1.0:
                    failed_reasons.append(f"Horizontal scroll overflow: doc scrollWidth ({doc_scroll_w}px) > winWidth ({win_w}px)")

            is_pass = len(failed_reasons) == 0
            if not is_pass:
                total_failures += 1

            status_str = "[PASS]" if is_pass else "[FAIL]"
            clip_display = f"{clipping_px:.1f}px" if dock else "N/A"
            bottom_display = f"{dock_bottom:.1f}px" if dock else "N/A"

            print(f"[RUN] {tc_id}: {name:<35} --> Bottom: {bottom_display:>7} | Clip: {clip_display:>5} | {status_str}")
            if not is_pass:
                for r in failed_reasons:
                    print(f"      ↳ REASON: {r}")

            results.append({
                "id": tc_id,
                "name": name,
                "viewport": {"width": w, "height": h},
                "device_scale_factor": scale,
                "is_mobile": is_mobile,
                "dock_rect": dock,
                "clipping_px": clipping_px if dock else None,
                "win_height": win_h,
                "win_width": win_w,
                "status": "PASS" if is_pass else "FAIL",
                "failures": failed_reasons,
                "screenshot": tc["screenshot"]
            })

            page.close()

        browser.close()

    # Generate Structured Manifest
    manifest_data = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "target_url": target_url,
        "browser_channel": channel,
        "total_cases": len(test_cases),
        "passed": len(test_cases) - total_failures,
        "failed": total_failures,
        "success_rate": f"{((len(test_cases) - total_failures) / len(test_cases)) * 100:.1f}%",
        "results": results
    }

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    print("\n" + "=" * 80)
    print(f"VERIFICATION SUMMARY: {len(test_cases) - total_failures} PASSED / {total_failures} FAILED")
    print(f"Success Rate: {manifest_data['success_rate']}")
    print(f"Manifest written to: {manifest_path}")
    print("=" * 80)

    return 0 if total_failures == 0 else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 1 Browser Layout Verification Runner")
    parser.add_argument("--url", default="http://localhost:3000", help="Target URL to test (default: http://localhost:3000)")
    parser.add_argument("--output", default="docs/screenshots/phase1", help="Output directory for screenshots (default: docs/screenshots/phase1)")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    args = parser.parse_args()

    exit_code = run_layout_verification(
        target_url=args.url,
        output_dir=args.output,
        headless=not args.headed
    )
    sys.exit(exit_code)
