#!/usr/bin/env python3
"""
Adversarial Verification Script for Phase 1 Layout & Screenshots
Author: challenger_p1_2 (empirical-challenger)

Tests:
1. Inspects all 14 PNG files in docs/screenshots/phase1/ and manifest.json.
2. Validates image integrity, dimensions, non-emptiness, and absence of visual clipping.
3. Runs live Playwright stress tests across breakpoints (375px, 640px, 768px, 1024px, 1440px, and edge cases).
4. Tests mobile drawer backdrop interaction: backdrop blocks underlying clicks, clicking backdrop closes drawer, Escape closes drawer.
"""

import os
import sys
import json
import time
from PIL import Image

def test_png_files_and_manifest(screenshots_dir: str):
    print("=" * 80)
    print("TASK 1: INSPECTION OF SCREENSHOTS AND MANIFEST.JSON")
    print("=" * 80)

    manifest_path = os.path.join(screenshots_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return False, f"manifest.json missing at {manifest_path}"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"Manifest timestamp: {manifest.get('timestamp')}")
    print(f"Total cases reported: {manifest.get('total_cases')}")
    print(f"Passed: {manifest.get('passed')}, Failed: {manifest.get('failed')}")

    results = manifest.get("results", [])
    if len(results) != 14:
        return False, f"Expected 14 results in manifest, found {len(results)}"

    failures = []
    inspected_files = []

    for item in results:
        case_id = item.get("id")
        name = item.get("name")
        filename = item.get("screenshot")
        status = item.get("status")
        clipping_px = item.get("clipping_px")
        item_failures = item.get("failures", [])

        if status != "PASS":
            failures.append(f"{case_id} ({name}): manifest reports status={status}")
        if clipping_px is None or clipping_px > 0.0:
            failures.append(f"{case_id} ({name}): manifest reports clipping_px={clipping_px}")
        if item_failures:
            failures.append(f"{case_id} ({name}): manifest failures: {item_failures}")

        img_path = os.path.join(screenshots_dir, filename)
        if not os.path.exists(img_path):
            failures.append(f"{case_id}: Image file missing: {img_path}")
            continue

        file_size = os.path.getsize(img_path)
        if file_size == 0:
            failures.append(f"{case_id}: Image file is empty (0 bytes): {filename}")
            continue

        # Inspect image with Pillow
        try:
            with Image.open(img_path) as img:
                img_format = img.format
                width, height = img.size
                if img_format != "PNG":
                    failures.append(f"{case_id}: Image {filename} format is {img_format}, expected PNG")

                # Verify image is not pure blank/solid color
                extrema = img.getextrema()
                # Check bounding box
                bbox = img.getbbox()
                if bbox is None:
                    failures.append(f"{case_id}: Image {filename} is completely blank")

                expected_viewport = item.get("viewport", {})
                scale = item.get("device_scale_factor", 1.0)
                expected_w = int(round(expected_viewport.get("width", 0) * scale))
                expected_h = int(round(expected_viewport.get("height", 0) * scale))

                dim_match = (width == expected_w and height == expected_h)

                inspected_files.append({
                    "id": case_id,
                    "filename": filename,
                    "size_bytes": file_size,
                    "dimensions": f"{width}x{height}",
                    "expected_dim": f"{expected_w}x{expected_h}",
                    "dim_match": dim_match,
                    "format": img_format,
                    "clipping_px": clipping_px
                })
                print(f"[{'PASS' if dim_match else 'WARN'}] {case_id} | {filename:<36} | {file_size:>7} bytes | {width}x{height} | clip={clipping_px}px")
        except Exception as e:
            failures.append(f"{case_id}: Error reading {filename} with PIL: {e}")

    # Check for any extra/unexpected files in directory
    all_pngs = [f for f in os.listdir(screenshots_dir) if f.endswith(".png")]
    print(f"\nFound {len(all_pngs)} PNG files in {screenshots_dir}:")
    for f in sorted(all_pngs):
        print(f"  - {f} ({os.path.getsize(os.path.join(screenshots_dir, f))} bytes)")

    if len(all_pngs) != 14:
        failures.append(f"Expected exactly 14 PNG files, found {len(all_pngs)}")

    if failures:
        print("\nFailures in Task 1:")
        for fail in failures:
            print(f"  - {fail}")
        return False, failures

    print(f"\nAll 14 PNG files verified: non-empty, valid PNG format, zero clipping reported.")
    return True, inspected_files


def run_live_adversarial_tests(target_url: str):
    print("\n" + "=" * 80)
    print("TASK 2 & 3: LIVE ADVERSARIAL RESPONSIVE & MOBILE DRAWER TESTS")
    print(f"Target URL: {target_url}")
    print("=" * 80)

    from playwright.sync_api import sync_playwright

    test_breakpoints = [
        {"name": "Mobile Small (320px)", "w": 320, "h": 568, "is_mobile": True},
        {"name": "Mobile Standard (375px)", "w": 375, "h": 667, "is_mobile": True},
        {"name": "Mobile Medium (414px)", "w": 414, "h": 896, "is_mobile": True},
        {"name": "Tablet Boundary (640px)", "w": 640, "h": 800, "is_mobile": False},
        {"name": "Tablet Portrait (768px)", "w": 768, "h": 1024, "is_mobile": False},
        {"name": "Desktop Small (1024px)", "w": 1024, "h": 768, "is_mobile": False},
        {"name": "Desktop Standard (1280px)", "w": 1280, "h": 768, "is_mobile": False},
        {"name": "Desktop Large (1440px)", "w": 1440, "h": 900, "is_mobile": False},
        {"name": "Desktop Ultra (1920px)", "w": 1920, "h": 1080, "is_mobile": False},
        {"name": "Desktop Constrained Height (1280x600)", "w": 1280, "h": 600, "is_mobile": False},
    ]

    adversarial_failures = []
    test_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # 1. Test responsive transitions & zero horizontal overflow
        print("\n--- [A] Responsive Breakpoint Transitions & Clipping ---")
        for bp in test_breakpoints:
            w = bp["w"]
            h = bp["h"]
            name = bp["name"]
            is_mobile = bp["is_mobile"]

            page = browser.new_page(
                viewport={"width": w, "height": h},
                is_mobile=is_mobile,
                has_touch=is_mobile
            )

            try:
                page.goto(target_url, wait_until="networkidle", timeout=10000)
            except Exception:
                page.goto(target_url, wait_until="load", timeout=8000)

            time.sleep(0.3)

            # Evaluate metrics
            metrics = page.evaluate("""() => {
                const dock = document.querySelector('.composer-dock') || document.querySelector('[data-testid="composer-dock"]');
                const winH = window.innerHeight;
                const winW = window.innerWidth;
                const docScrollW = document.documentElement.scrollWidth;
                const bodyScrollW = document.body.scrollWidth;
                const dockRect = dock ? dock.getBoundingClientRect() : null;

                // Check all elements for horizontal overflow
                let overflowElements = [];
                document.querySelectorAll('*').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.right > winW + 1 && el.tagName !== 'HTML' && el.tagName !== 'BODY') {
                        // ignore hidden or translated elements like collapsed drawer
                        const style = window.getComputedStyle(el);
                        if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0' && !el.closest('.app-sidebar:not(.open)')) {
                            overflowElements.push({
                                tag: el.tagName,
                                class: el.className,
                                right: rect.right
                            });
                        }
                    }
                });

                return {
                    winH,
                    winW,
                    docScrollW,
                    bodyScrollW,
                    dockRect: dockRect ? {
                        top: dockRect.top,
                        bottom: dockRect.bottom,
                        height: dockRect.height,
                        left: dockRect.left,
                        right: dockRect.right,
                        width: dockRect.width
                    } : null,
                    overflowElements: overflowElements.slice(0, 5)
                };
            }""")

            dock = metrics["dockRect"]
            win_h = metrics["winH"]
            win_w = metrics["winW"]
            doc_scroll_w = metrics["docScrollW"]
            overflow_elems = metrics["overflowElements"]

            reasons = []
            if not dock:
                reasons.append("Composer dock missing")
            else:
                clipping_bottom = dock["bottom"] - win_h
                if clipping_bottom > 0.5:
                    reasons.append(f"Dock clipped by {clipping_bottom:.1f}px at bottom (bottom={dock['bottom']}, winH={win_h})")
                if dock["top"] < 0:
                    reasons.append(f"Dock top offscreen: {dock['top']}")
                if dock["height"] < 35:
                    reasons.append(f"Dock collapsed: height={dock['height']}")

            if doc_scroll_w > win_w + 1:
                reasons.append(f"Horizontal scroll overflow: docScrollW={doc_scroll_w} > winW={win_w}")

            if reasons:
                adversarial_failures.extend([f"{name}: {r}" for r in reasons])
                print(f"[FAIL] {name:<35} | docScrollW={doc_scroll_w}/{win_w} | dockBottom={dock['bottom'] if dock else 'N/A'}/{win_h} | REASONS: {reasons}")
            else:
                print(f"[PASS] {name:<35} | docScrollW={doc_scroll_w}/{win_w} | dockBottom={dock['bottom']:.1f}/{win_h} | clip=0px")

            test_results.append({
                "breakpoint": name,
                "width": w,
                "height": h,
                "status": "FAIL" if reasons else "PASS",
                "reasons": reasons
            })

            page.close()

        # 2. Test Mobile Drawer & Backdrop Interaction (<768px: e.g. 375px and 640px)
        print("\n--- [B] Mobile Drawer Backdrop & Interaction Adversarial Tests ---")
        drawer_viewports = [
            {"name": "Mobile 375px", "w": 375, "h": 667, "is_mobile": True},
            {"name": "Tablet 640px", "w": 640, "h": 800, "is_mobile": False},
        ]

        for vp in drawer_viewports:
            w = vp["w"]
            h = vp["h"]
            name = vp["name"]
            is_mobile = vp["is_mobile"]

            page = browser.new_page(
                viewport={"width": w, "height": h},
                is_mobile=is_mobile,
                has_touch=is_mobile
            )

            try:
                page.goto(target_url, wait_until="networkidle", timeout=10000)
            except Exception:
                page.goto(target_url, wait_until="load", timeout=8000)

            time.sleep(0.3)

            # Test 1: Initially drawer is closed
            sidebar_open_initial = page.locator(".app-sidebar.open").count()
            backdrop_initial = page.locator(".drawer-backdrop").count()
            print(f"[{name}] Initial state: sidebar open count={sidebar_open_initial}, backdrop count={backdrop_initial}")
            if sidebar_open_initial > 0 or backdrop_initial > 0:
                adversarial_failures.append(f"{name}: Drawer or backdrop open on initial load")

            # Test 2: Open drawer via hamburger toggle button
            toggle_btn = page.locator(".btn-sidebar-toggle").first
            if not toggle_btn.is_visible():
                adversarial_failures.append(f"{name}: .btn-sidebar-toggle is not visible")
                page.close()
                continue

            toggle_btn.click()
            time.sleep(0.35)

            # Verify sidebar is now open
            sidebar_open = page.locator(".app-sidebar.open").first
            backdrop = page.locator(".drawer-backdrop").first

            sidebar_visible = sidebar_open.is_visible()
            backdrop_visible = backdrop.is_visible()

            print(f"[{name}] After toggle click: sidebar open visible={sidebar_visible}, backdrop visible={backdrop_visible}")
            if not sidebar_visible:
                adversarial_failures.append(f"{name}: Sidebar did not become visible after clicking toggle")
            if not backdrop_visible:
                adversarial_failures.append(f"{name}: .drawer-backdrop is not visible when drawer is open")

            # Test 3: Check backdrop geometry & z-index
            backdrop_props = page.evaluate("""() => {
                const bd = document.querySelector('.drawer-backdrop');
                const sb = document.querySelector('.app-sidebar');
                if (!bd || !sb) return null;
                const bdRect = bd.getBoundingClientRect();
                const bdStyle = window.getComputedStyle(bd);
                const sbStyle = window.getComputedStyle(sb);
                return {
                    rect: {
                        top: bdRect.top,
                        bottom: bdRect.bottom,
                        left: bdRect.left,
                        right: bdRect.right,
                        width: bdRect.width,
                        height: bdRect.height
                    },
                    bdZIndex: bdStyle.zIndex,
                    sbZIndex: sbStyle.zIndex,
                    winW: window.innerWidth,
                    winH: window.innerHeight
                };
            }""")

            if backdrop_props:
                bd_rect = backdrop_props["rect"]
                win_w = backdrop_props["winW"]
                win_h = backdrop_props["winH"]
                print(f"[{name}] Backdrop bounds: {bd_rect['width']}x{bd_rect['height']} (win: {win_w}x{win_h}), z-index={backdrop_props['bdZIndex']} (sidebar z-index={backdrop_props['sbZIndex']})")

                # Verify backdrop covers the whole viewport
                if bd_rect["width"] < win_w - 1 or bd_rect["height"] < win_h - 1:
                    adversarial_failures.append(f"{name}: Backdrop does not cover full viewport: bd={bd_rect['width']}x{bd_rect['height']} vs win={win_w}x{win_h}")

            # Test 4: Adversarial Test — Backdrop blocks clicks to underlying content
            # We attempt to click the background / underlying chat content or starter chip while drawer is open.
            # We inject an event listener on starter chips / composer to see if clicks penetrate the backdrop.
            click_penetration = page.evaluate("""() => {
                window.__underlyingClicked = false;
                const starter = document.querySelector('.starter-chip') || document.querySelector('.composer-textarea');
                if (starter) {
                    starter.addEventListener('click', () => {
                        window.__underlyingClicked = true;
                    }, { once: true });
                }

                // Determine coordinates where underlying element sits (e.g. right side of screen, outside sidebar)
                const targetX = Math.round(window.innerWidth * 0.85);
                const targetY = Math.round(window.innerHeight * 0.5);

                const elementAtPoint = document.elementFromPoint(targetX, targetY);
                return {
                    elementAtPointTag: elementAtPoint ? elementAtPoint.tagName : null,
                    elementAtPointClass: elementAtPoint ? elementAtPoint.className : null,
                    isBackdrop: elementAtPoint && elementAtPoint.classList.contains('drawer-backdrop'),
                    targetX,
                    targetY
                };
            }""")

            print(f"[{name}] Element at point outside sidebar (X={click_penetration.get('targetX')}, Y={click_penetration.get('targetY')}): tag={click_penetration.get('elementAtPointTag')}, class={click_penetration.get('elementAtPointClass')}, isBackdrop={click_penetration.get('isBackdrop')}")

            if not click_penetration.get("isBackdrop"):
                adversarial_failures.append(f"{name}: Element at (X={click_penetration.get('targetX')}, Y={click_penetration.get('targetY')}) is {click_penetration.get('elementAtPointClass')}, NOT .drawer-backdrop! Backdrop failed to intercept interaction.")
            else:
                print(f"[{name}] PASS: .drawer-backdrop is top hit-test element; underlying interactions blocked.")

            # Test 5: Clicking the backdrop closes the drawer
            # Click at targetX, targetY (which hits the backdrop)
            target_x = click_penetration["targetX"]
            target_y = click_penetration["targetY"]
            page.mouse.click(target_x, target_y)
            time.sleep(0.35)

            # Check if drawer closed
            drawer_closed_after_backdrop_click = page.evaluate("""() => {
                const sb = document.querySelector('.app-sidebar.open');
                const bd = document.querySelector('.drawer-backdrop');
                return {
                    sidebarOpen: !!sb,
                    backdropPresent: !!bd
                };
            }""")

            print(f"[{name}] After clicking backdrop: sidebarOpen={drawer_closed_after_backdrop_click['sidebarOpen']}, backdropPresent={drawer_closed_after_backdrop_click['backdropPresent']}")

            if drawer_closed_after_backdrop_click["sidebarOpen"] or drawer_closed_after_backdrop_click["backdropPresent"]:
                adversarial_failures.append(f"{name}: Clicking backdrop did NOT close drawer: sidebarOpen={drawer_closed_after_backdrop_click['sidebarOpen']}, backdropPresent={drawer_closed_after_backdrop_click['backdropPresent']}")
            else:
                print(f"[{name}] PASS: Clicking backdrop successfully closed the drawer.")

            # Test 6: Re-open drawer and test Escape key closes drawer
            toggle_btn.click()
            time.sleep(0.35)
            page.keyboard.press("Escape")
            time.sleep(0.35)

            drawer_closed_after_escape = page.evaluate("""() => {
                const sb = document.querySelector('.app-sidebar.open');
                const bd = document.querySelector('.drawer-backdrop');
                return {
                    sidebarOpen: !!sb,
                    backdropPresent: !!bd
                };
            }""")
            print(f"[{name}] After pressing Escape: sidebarOpen={drawer_closed_after_escape['sidebarOpen']}, backdropPresent={drawer_closed_after_escape['backdropPresent']}")
            if drawer_closed_after_escape["sidebarOpen"] or drawer_closed_after_escape["backdropPresent"]:
                adversarial_failures.append(f"{name}: Pressing Escape did NOT close drawer")
            else:
                print(f"[{name}] PASS: Pressing Escape successfully closed the drawer.")

            page.close()

        browser.close()

    print("\n" + "=" * 80)
    if adversarial_failures:
        print(f"ADVERSARIAL FAILURES FOUND ({len(adversarial_failures)}):")
        for f in adversarial_failures:
            print(f"  [FAIL] {f}")
        return False, adversarial_failures
    else:
        print("ALL ADVERSARIAL STRESS TESTS PASSED (100% OK)")
        return True, test_results


if __name__ == "__main__":
    screenshots_dir = os.path.abspath("docs/screenshots/phase1")
    t1_pass, t1_details = test_png_files_and_manifest(screenshots_dir)

    target_url = "http://127.0.0.1:5173"
    t2_pass, t2_details = run_live_adversarial_tests(target_url)

    # Also test port 3000
    target_url_3000 = "http://127.0.0.1:3000"
    print("\nTesting port 3000 for parity:")
    t3_pass, t3_details = run_live_adversarial_tests(target_url_3000)

    overall_pass = t1_pass and t2_pass and t3_pass
    print("\n" + "=" * 80)
    print(f"OVERALL VERDICT: {'APPROVE' if overall_pass else 'CHALLENGE_FAILED'}")
    print("=" * 80)
    sys.exit(0 if overall_pass else 1)
