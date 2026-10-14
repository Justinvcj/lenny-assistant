#!/usr/bin/env python3
"""
Adversarial Phase 1 Layout & Interaction Stress-Testing Harness
Empirically tests:
1. Extreme viewports (320x500, 320x450, 480x500, 1024x500, 1280x500)
2. Extreme multiline inputs (10 lines, 25 lines, 50 lines, 4000 chars limit, 500 chars unbroken)
3. Zero messages empty state vs 50+ messages scroll containment
4. Independent scrolling of .chat-scroll-area (window.scrollY == 0)
5. Keyboard shortcut Ctrl+B / Cmd+B toggling sidebar & localStorage persistence
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
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LennyChallenger/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 304)
    except Exception:
        return False

def get_best_browser_channel() -> str:
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if os.path.exists(chrome_path):
        return "chrome"
    elif os.path.exists(edge_path):
        return "msedge"
    return "chromium"

def run_adversarial_challenge(target_url: str, output_dir: str, headless: bool = True) -> int:
    print("=" * 80)
    print("LENNY GROWTH ASSISTANT — PHASE 1 ADVERSARIAL CHALLENGE HARNESS")
    print(f"Target URL: {target_url}")
    print(f"Output Directory: {output_dir}")
    print("=" * 80)

    if not check_server_health(target_url):
        print(f"[ERROR] Target server at {target_url} is unreachable.")
        return 1

    os.makedirs(output_dir, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] Playwright is not installed.")
        return 1

    channel = get_best_browser_channel()
    print(f"[INFO] Using browser channel: '{channel}'")

    tests = [
        # --- Group 1: Extreme Small Viewports ---
        {
            "id": "ADV-01",
            "name": "Extreme Small Viewport 320x500 (Mobile)",
            "width": 320,
            "height": 500,
            "scale": 1.0,
            "is_mobile": True,
            "scenario": "default",
            "screenshot": "adv_01_viewport_320x500.png"
        },
        {
            "id": "ADV-02",
            "name": "Ultra-Short Mobile 320x450",
            "width": 320,
            "height": 450,
            "scale": 1.0,
            "is_mobile": True,
            "scenario": "default",
            "screenshot": "adv_02_viewport_320x450.png"
        },
        {
            "id": "ADV-03",
            "name": "Landscape Mobile Tiny 480x500",
            "width": 480,
            "height": 500,
            "scale": 1.0,
            "is_mobile": True,
            "scenario": "default",
            "screenshot": "adv_03_viewport_480x500.png"
        },
        {
            "id": "ADV-04",
            "name": "Desktop Short 1024x500",
            "width": 1024,
            "height": 500,
            "scale": 1.0,
            "is_mobile": False,
            "scenario": "default",
            "screenshot": "adv_04_desktop_1024x500.png"
        },
        {
            "id": "ADV-05",
            "name": "Wide Desktop Short 1280x500",
            "width": 1280,
            "height": 500,
            "scale": 1.0,
            "is_mobile": False,
            "scenario": "default",
            "screenshot": "adv_05_desktop_1280x500.png"
        },

        # --- Group 2: Multiline Input Stress ---
        {
            "id": "ADV-06",
            "name": "Multiline Stress 10 Lines (1280x600)",
            "width": 1280,
            "height": 600,
            "scale": 1.0,
            "is_mobile": False,
            "scenario": "multiline_10",
            "screenshot": "adv_06_multiline_10.png"
        },
        {
            "id": "ADV-07",
            "name": "Multiline Stress 25 Lines (1280x600)",
            "width": 1280,
            "height": 600,
            "scale": 1.0,
            "is_mobile": False,
            "scenario": "multiline_25",
            "screenshot": "adv_07_multiline_25.png"
        },
        {
            "id": "ADV-08",
            "name": "Multiline Stress 50 Lines (1280x500)",
            "width": 1280,
            "height": 500,
            "scale": 1.0,
            "is_mobile": False,
            "scenario": "multiline_50",
            "screenshot": "adv_08_multiline_50_short.png"
        },
        {
            "id": "ADV-09",
            "name": "Multiline Stress 4000 Chars Limit (1280x600)",
            "width": 1280,
            "height": 600,
            "scale": 1.0,
            "is_mobile": False,
            "scenario": "multiline_4000chars",
            "screenshot": "adv_09_multiline_4000chars.png"
        },
        {
            "id": "ADV-10",
            "name": "Unbroken Token Stress (500 chars unbroken)",
            "width": 375,
            "height": 667,
            "scale": 1.0,
            "is_mobile": True,
            "scenario": "unbroken_string",
            "screenshot": "adv_10_unbroken_string.png"
        },

        # --- Group 3: Message Count Stress ---
        {
            "id": "ADV-11",
            "name": "Zero Messages Empty State Layout (320x500)",
            "width": 320,
            "height": 500,
            "scale": 1.0,
            "is_mobile": True,
            "scenario": "zero_messages",
            "screenshot": "adv_11_zero_messages_320x500.png"
        },
        {
            "id": "ADV-12",
            "name": "50+ Messages Scroll Containment Stress",
            "width": 1280,
            "height": 600,
            "scale": 1.0,
            "is_mobile": False,
            "scenario": "50_messages",
            "screenshot": "adv_12_50_messages_scroll.png"
        },

        # --- Group 4: Keyboard Shortcut & LocalStorage ---
        {
            "id": "ADV-13",
            "name": "Ctrl+B Shortcut Desktop Toggle & LocalStorage",
            "width": 1280,
            "height": 768,
            "scale": 1.0,
            "is_mobile": False,
            "scenario": "ctrl_b_desktop",
            "screenshot": "adv_13_ctrl_b_desktop.png"
        },
        {
            "id": "ADV-14",
            "name": "Ctrl+B Shortcut Mobile Drawer Toggle",
            "width": 375,
            "height": 667,
            "scale": 1.0,
            "is_mobile": True,
            "scenario": "ctrl_b_mobile",
            "screenshot": "adv_14_ctrl_b_mobile.png"
        }
    ]

    results = []
    total_failures = 0

    with sync_playwright() as p:
        browser_kwargs = {"headless": headless}
        if channel in ("chrome", "msedge"):
            browser_kwargs["channel"] = channel

        browser = p.chromium.launch(**browser_kwargs)

        print("\n[RUNNING ADVERSARIAL CHALLENGE SUITE]")
        print("-" * 80)

        for tc in tests:
            tc_id = tc["id"]
            name = tc["name"]
            w = tc["width"]
            h = tc["height"]
            scale = tc["scale"]
            is_mobile = tc["is_mobile"]
            scenario = tc["scenario"]
            screenshot_path = os.path.join(output_dir, tc["screenshot"])

            page = browser.new_page(
                viewport={"width": w, "height": h},
                device_scale_factor=scale,
                is_mobile=is_mobile,
                has_touch=is_mobile,
            )

            try:
                page.goto(target_url, wait_until="networkidle", timeout=12000)
            except Exception:
                page.goto(target_url, wait_until="load", timeout=8000)

            time.sleep(0.3)
            failed_reasons = []

            # Scenario Execution
            if scenario == "multiline_10":
                textarea = page.locator(".composer-textarea").first
                if textarea.is_visible():
                    lines = [f"Line {i}: Testing multiline height clamp and flex behavior." for i in range(1, 11)]
                    textarea.fill("\n".join(lines))
                    time.sleep(0.2)
                else:
                    failed_reasons.append("Textarea not visible")

            elif scenario == "multiline_25":
                textarea = page.locator(".composer-textarea").first
                if textarea.is_visible():
                    lines = [f"Line {i}: Deep stress input testing vertical bounds of composer." for i in range(1, 26)]
                    textarea.fill("\n".join(lines))
                    time.sleep(0.2)
                else:
                    failed_reasons.append("Textarea not visible")

            elif scenario == "multiline_50":
                textarea = page.locator(".composer-textarea").first
                if textarea.is_visible():
                    lines = [f"Line {i}: Extreme 50-line input text block." for i in range(1, 51)]
                    textarea.fill("\n".join(lines))
                    time.sleep(0.2)
                else:
                    failed_reasons.append("Textarea not visible")

            elif scenario == "multiline_4000chars":
                textarea = page.locator(".composer-textarea").first
                if textarea.is_visible():
                    block = ("Lenny Product Strategy Knowledge Base Test. " * 80)[:3990]
                    textarea.fill(block)
                    time.sleep(0.2)
                else:
                    failed_reasons.append("Textarea not visible")

            elif scenario == "unbroken_string":
                textarea = page.locator(".composer-textarea").first
                if textarea.is_visible():
                    textarea.fill("A" * 500)
                    time.sleep(0.2)
                else:
                    failed_reasons.append("Textarea not visible")

            elif scenario == "50_messages":
                # Dynamically inject 50 messages into the conversation DOM
                page.evaluate("""() => {
                    const scrollArea = document.querySelector('.chat-scroll-area');
                    const container = document.querySelector('.chat-container');
                    if (!container) return;

                    // Remove empty state if present
                    const emptyState = container.querySelector('.empty-state');
                    if (emptyState) emptyState.remove();

                    let messageList = container.querySelector('.message-list');
                    if (!messageList) {
                        messageList = document.createElement('div');
                        messageList.className = 'message-list';
                        container.appendChild(messageList);
                    }

                    for (let i = 1; i <= 50; i++) {
                        const msgItem = document.createElement('div');
                        msgItem.className = 'message-item ' + (i % 2 === 0 ? 'user' : 'assistant');
                        msgItem.style.padding = '12px 16px';
                        msgItem.style.margin = '8px 0';
                        msgItem.style.borderRadius = '8px';
                        msgItem.style.background = i % 2 === 0 ? 'rgba(124, 92, 255, 0.15)' : 'rgba(255, 255, 255, 0.05)';
                        msgItem.innerHTML = '<strong>Turn #' + i + ':</strong> Sample message content demonstrating scroll containment and flex integrity under heavy message load.';
                        messageList.appendChild(msgItem);
                    }
                }""")
                time.sleep(0.3)

                # Test scrolling the scroll area
                scroll_test = page.evaluate("""() => {
                    const scrollArea = document.querySelector('.chat-scroll-area');
                    if (!scrollArea) return { error: 'No scrollArea' };

                    const initialScrollTop = scrollArea.scrollTop;
                    const scrollHeight = scrollArea.scrollHeight;
                    const clientHeight = scrollArea.clientHeight;

                    // Scroll down with instant behavior
                    scrollArea.scrollTo({ top: 800, behavior: 'instant' });

                    const newScrollTop = scrollArea.scrollTop;
                    const winScrollY = window.scrollY;
                    const docScrollTop = document.documentElement.scrollTop;

                    return {
                        scrollHeight,
                        clientHeight,
                        initialScrollTop,
                        newScrollTop,
                        winScrollY,
                        docScrollTop
                    };
                }""")

                if scroll_test.get("error"):
                    failed_reasons.append(scroll_test["error"])
                else:
                    print(f"      [DEBUG 50_messages] scrollHeight={scroll_test['scrollHeight']}, clientHeight={scroll_test['clientHeight']}, newScrollTop={scroll_test['newScrollTop']}")
                    if scroll_test["scrollHeight"] <= scroll_test["clientHeight"]:
                        failed_reasons.append(f"ScrollArea did not overflow: scrollHeight ({scroll_test['scrollHeight']}px) <= clientHeight ({scroll_test['clientHeight']}px)")
                    if scroll_test["newScrollTop"] == 0 and scroll_test["scrollHeight"] > scroll_test["clientHeight"]:
                        failed_reasons.append("ScrollArea scrollTop did not change after scrolling")
                    if scroll_test["winScrollY"] > 0 or scroll_test["docScrollTop"] > 0:
                        failed_reasons.append(f"Window itself scrolled! winScrollY={scroll_test['winScrollY']}, docScrollTop={scroll_test['docScrollTop']}")

            elif scenario == "ctrl_b_desktop":
                # Test desktop Ctrl+B shortcut and localStorage
                initial_state = page.evaluate("""() => {
                    const sidebar = document.querySelector('.app-sidebar');
                    const stored = localStorage.getItem('lenny_sidebar_collapsed');
                    return {
                        isCollapsed: sidebar ? sidebar.classList.contains('collapsed') : null,
                        stored: stored,
                        width: sidebar ? sidebar.getBoundingClientRect().width : null
                    };
                }""")

                # Press Ctrl+B
                page.keyboard.press("Control+b")
                time.sleep(0.3)

                toggled_state = page.evaluate("""() => {
                    const sidebar = document.querySelector('.app-sidebar');
                    const stored = localStorage.getItem('lenny_sidebar_collapsed');
                    return {
                        isCollapsed: sidebar ? sidebar.classList.contains('collapsed') : null,
                        stored: stored,
                        width: sidebar ? sidebar.getBoundingClientRect().width : null
                    };
                }""")

                # Press Ctrl+B again
                page.keyboard.press("Control+b")
                time.sleep(0.3)

                reverted_state = page.evaluate("""() => {
                    const sidebar = document.querySelector('.app-sidebar');
                    const stored = localStorage.getItem('lenny_sidebar_collapsed');
                    return {
                        isCollapsed: sidebar ? sidebar.classList.contains('collapsed') : null,
                        stored: stored,
                        width: sidebar ? sidebar.getBoundingClientRect().width : null
                    };
                }""")

                # Validate transitions
                if toggled_state["isCollapsed"] == initial_state["isCollapsed"]:
                    failed_reasons.append(f"Ctrl+B failed to toggle sidebar collapsed state (remained {initial_state['isCollapsed']})")
                if toggled_state["stored"] == initial_state["stored"]:
                    failed_reasons.append(f"Ctrl+B failed to update localStorage (remained {initial_state['stored']})")
                if reverted_state["isCollapsed"] != initial_state["isCollapsed"]:
                    failed_reasons.append("Ctrl+B second press failed to revert collapsed state")
                if reverted_state["stored"] != initial_state["stored"]:
                    failed_reasons.append("Ctrl+B second press failed to revert localStorage")

            elif scenario == "ctrl_b_mobile":
                # Test mobile drawer Ctrl+B toggle
                initial_mobile = page.evaluate("""() => {
                    const sidebar = document.querySelector('.app-sidebar');
                    return {
                        isOpen: sidebar ? sidebar.classList.contains('open') : false
                    };
                }""")

                page.keyboard.press("Control+b")
                time.sleep(0.3)

                toggled_mobile = page.evaluate("""() => {
                    const sidebar = document.querySelector('.app-sidebar');
                    return {
                        isOpen: sidebar ? sidebar.classList.contains('open') : false
                    };
                }""")

                page.keyboard.press("Control+b")
                time.sleep(0.3)

                reverted_mobile = page.evaluate("""() => {
                    const sidebar = document.querySelector('.app-sidebar');
                    return {
                        isOpen: sidebar ? sidebar.classList.contains('open') : false
                    };
                }""")

                if toggled_mobile["isOpen"] == initial_mobile["isOpen"]:
                    failed_reasons.append("Ctrl+B on mobile failed to toggle sidebar open drawer state")
                if reverted_mobile["isOpen"] != initial_mobile["isOpen"]:
                    failed_reasons.append("Ctrl+B on mobile second press failed to revert drawer state")

            # Layout & Geometry Evaluation
            metrics = page.evaluate("""() => {
                const dock = document.querySelector('[data-testid="composer-dock"]') || document.querySelector('.composer-dock');
                const textarea = document.querySelector('[data-testid="composer-textarea"]') || document.querySelector('.composer-textarea');
                const sendBtn = document.querySelector('[data-testid="composer-send-btn"]') || document.querySelector('.btn-send');
                const header = document.querySelector('.app-header');
                const scrollArea = document.querySelector('.chat-scroll-area');

                const winH = window.innerHeight;
                const winW = window.innerWidth;
                const docScrollW = document.documentElement.scrollWidth;
                const winScrollY = window.scrollY;

                const dockRect = dock ? dock.getBoundingClientRect() : null;
                const textareaRect = textarea ? textarea.getBoundingClientRect() : null;
                const sendBtnRect = sendBtn ? sendBtn.getBoundingClientRect() : null;
                const headerRect = header ? header.getBoundingClientRect() : null;

                return {
                    winH,
                    winW,
                    docScrollW,
                    winScrollY,
                    dock: dockRect ? {
                        top: dockRect.top,
                        bottom: dockRect.bottom,
                        height: dockRect.height
                    } : null,
                    textarea: textareaRect ? {
                        top: textareaRect.top,
                        bottom: textareaRect.bottom,
                        height: textareaRect.height,
                        scrollHeight: textarea.scrollHeight
                    } : null,
                    sendBtn: sendBtnRect ? {
                        top: sendBtnRect.top,
                        bottom: sendBtnRect.bottom
                    } : null,
                    header: headerRect ? {
                        top: headerRect.top,
                        bottom: headerRect.bottom,
                        height: headerRect.height
                    } : null
                };
            }""")

            # Capture screenshot
            page.screenshot(path=screenshot_path, full_page=False)

            dock = metrics.get("dock")
            win_h = metrics["winH"]
            win_w = metrics["winW"]
            doc_scroll_w = metrics["docScrollW"]
            win_scroll_y = metrics["winScrollY"]

            if not dock:
                failed_reasons.append("Composer dock not found")
                clipping_px = 999.0
                dock_bottom = 999.0
            else:
                dock_bottom = dock["bottom"]
                clipping_px = max(0.0, dock_bottom - win_h)

                # Assertion: dock bottom must be <= win_h + 0.5px
                if clipping_px > 0.5:
                    failed_reasons.append(f"Dock clipped: bottom ({dock_bottom:.1f}px) exceeds window ({win_h}px) by {clipping_px:.1f}px")

                # Assertion: dock top must be >= 0
                if dock["top"] < 0:
                    failed_reasons.append(f"Dock top ({dock['top']:.1f}px) pushed above top edge")

                # Assertion: dock height clamp (must not exceed 65% of viewport)
                if dock["height"] > win_h * 0.70:
                    failed_reasons.append(f"Dock height ({dock['height']:.1f}px) consumes >70% of viewport ({win_h}px)")

            # Assertion: Send button visible within viewport
            send_btn = metrics.get("sendBtn")
            if send_btn:
                if send_btn["bottom"] > win_h + 0.5:
                    failed_reasons.append(f"Send button clipped at bottom: {send_btn['bottom']:.1f}px > {win_h}px")

            # Assertion: Header remains pinned at top (top == 0)
            header = metrics.get("header")
            if header:
                if abs(header["top"]) > 1.0:
                    failed_reasons.append(f"Header pushed off top: top = {header['top']:.1f}px")

            # Assertion: No window-level scrolling (winScrollY == 0)
            if win_scroll_y > 0:
                failed_reasons.append(f"Window scrolled vertically: winScrollY = {win_scroll_y}px")

            # Assertion: No horizontal scroll overflow
            if doc_scroll_w > win_w + 1.0:
                failed_reasons.append(f"Horizontal scroll overflow: scrollWidth ({doc_scroll_w}px) > winWidth ({win_w}px)")

            # Assertion: Textarea height clamp (max-height <= 165px)
            textarea = metrics.get("textarea")
            if textarea:
                if textarea["height"] > 165.0:
                    failed_reasons.append(f"Textarea exceeded max height clamp: {textarea['height']:.1f}px > 165px")

            is_pass = len(failed_reasons) == 0
            if not is_pass:
                total_failures += 1

            status_str = "[PASS]" if is_pass else "[FAIL]"
            clip_display = f"{clipping_px:.1f}px" if dock else "N/A"
            bottom_display = f"{dock_bottom:.1f}px" if dock else "N/A"

            print(f"[RUN] {tc_id}: {name:<42} --> Bottom: {bottom_display:>7} | Clip: {clip_display:>5} | {status_str}")
            if not is_pass:
                for r in failed_reasons:
                    print(f"      --> FAILURE: {r}")

            results.append({
                "id": tc_id,
                "name": name,
                "viewport": {"width": w, "height": h},
                "scenario": scenario,
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

    manifest_data = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "target_url": target_url,
        "browser_channel": channel,
        "total_cases": len(tests),
        "passed": len(tests) - total_failures,
        "failed": total_failures,
        "success_rate": f"{((len(tests) - total_failures) / len(tests)) * 100:.1f}%",
        "results": results
    }

    manifest_path = os.path.join(output_dir, "manifest_adversarial.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    print("\n" + "=" * 80)
    print(f"ADVERSARIAL CHALLENGE SUMMARY: {len(tests) - total_failures} PASSED / {total_failures} FAILED")
    print(f"Success Rate: {manifest_data['success_rate']}")
    print(f"Manifest written to: {manifest_path}")
    print("=" * 80)

    return 0 if total_failures == 0 else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adversarial Phase 1 Layout Challenge Runner")
    parser.add_argument("--url", default="http://127.0.0.1:5173", help="Target URL (default: http://127.0.0.1:5173)")
    parser.add_argument("--output", default="docs/screenshots/phase1/adversarial", help="Output directory")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    args = parser.parse_args()

    exit_code = run_adversarial_challenge(
        target_url=args.url,
        output_dir=args.output,
        headless=not args.headed
    )
    sys.exit(exit_code)
