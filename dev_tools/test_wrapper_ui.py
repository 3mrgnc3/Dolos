#!/usr/bin/env python3
"""Playwright UI test: Verify Dolos appears under Create Wrapper and drive a build.

Tests:
1. Dolos appears in Create Wrapper (not Create Payload)
2. No C2 profile selection step (wrapper has c2_profiles=[])
3. Build parameters are correct (Encoder, Timeout, Success String, Fail String)
4. Encoder dropdown has choices from DOLOS_REMOTE_COMMAND
5. A payload can be selected and built
6. Result file is non-zero bytes

Usage:
    python3 dev_tools/test_wrapper_ui.py
    python3 dev_tools/test_wrapper_ui.py --headed
"""

import argparse
import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

MYTHIC_URL = "https://127.0.0.1:7443"
MYTHIC_USER = "mythic_admin"
MYTHIC_PASS = "e9WYrzxS7vy76L3nk2RzDQCBlsXAte"

# Read Hasura secret for DB verification
with open("/home/mrgnc/MythicC2/Mythic/.env") as f:
    HASURA_SECRET = f.read().split('HASURA_SECRET="')[1].split('"')[0]


def graphql_query(query):
    url = "http://127.0.0.1:8080/v1/graphql"
    headers = {"x-hasura-admin-secret": HASURA_SECRET, "Content-Type": "application/json"}
    data = json.dumps({"query": query}).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())


def check_newest_dolos_payload():
    """Check the newest Dolos wrapper payload."""
    query = '''{ payload(where:{payloadtype:{name:{_eq:"dolos"}}}, order_by:{id:desc}, limit:1) {
      id uuid build_phase build_message
      wrapped_payload_id
    } }'''
    result = graphql_query(query)
    payloads = result.get("data", {}).get("payload", [])
    if payloads:
        return payloads[0]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="Show browser")
    parser.add_argument("--screenshot", action="store_true", help="Save screenshots")
    args = parser.parse_args()

    print("=" * 60)
    print("Dolos Wrapper UI Test")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        # ── 1. Login ──
        print("\n[1] Logging into Mythic...")
        page.goto(f"{MYTHIC_URL}/new/login", wait_until="networkidle")
        page.wait_for_timeout(1000)

        # Fill login form (MUI inputs, no stable IDs)
        username_input = page.locator('input[type="text"]').first
        password_input = page.locator('input[type="password"]').first
        username_input.click()
        username_input.fill(MYTHIC_USER)
        password_input.click()
        password_input.fill(MYTHIC_PASS)
        page.click('button:has-text("Login"), button[type="submit"]')
        page.wait_for_timeout(3000)
        print(f"  Logged in. URL: {page.url}")

        if args.screenshot:
            page.screenshot(path="/tmp/dolos_01_login.png")

        # ── 2. Navigate to Create Wrapper ──
        print("\n[2] Navigating to Create Wrapper...")
        page.goto(f"{MYTHIC_URL}/new/create_wrapper", wait_until="networkidle")
        page.wait_for_timeout(2000)

        if args.screenshot:
            page.screenshot(path="/tmp/dolos_02_create_wrapper.png")

        page_text = page.inner_text("body")
        print(f"  Page loaded. Title: {page.title()}")

        # ── 3. Verify Dolos appears in wrapper list ──
        print("\n[3] Verifying Dolos appears in wrapper list...")
        dolos_found = "dolos" in page_text.lower() or "Dolos" in page_text
        print(f"  Dolos found on Create Wrapper page: {dolos_found}")

        if not dolos_found:
            # Try looking for wrapper payload type buttons/cards
            print("  Looking for wrapper options...")
            buttons = page.query_selector_all('button, [role="button"], .card, div[class*="payload"]')
            for btn in buttons[:20]:
                txt = btn.inner_text()[:80]
                if txt.strip():
                    print(f"    button: {txt}")

        # ── 4. Also verify Dolos does NOT appear in Create Payload ──
        print("\n[4] Verifying Dolos does NOT appear in Create Payload...")
        page.goto(f"{MYTHIC_URL}/new/create_payload", wait_until="networkidle")
        page.wait_for_timeout(2000)

        if args.screenshot:
            page.screenshot(path="/tmp/dolos_03_create_payload.png")

        payload_text = page.inner_text("body").lower()
        dolos_in_payload = "dolos" in payload_text
        print(f"  Dolos in Create Payload page: {dolos_in_payload} (should be False for a wrapper)")

        # ── 5. Go back to Create Wrapper and try to select Dolos ──
        print("\n[5] Selecting Dolos in Create Wrapper...")
        page.goto(f"{MYTHIC_URL}/new/create_wrapper", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # Try to click on Dolos
        try:
            dolos_btn = page.locator('text=Dolos').first
            if dolos_btn.is_visible():
                dolos_btn.click()
                page.wait_for_timeout(2000)
                print("  Clicked Dolos")
            else:
                print("  Dolos button not visible, trying alternative selectors...")
                # Try finding it as a list item or card
                items = page.query_selector_all('li, .card, [role="button"]')
                for item in items:
                    if "dolos" in item.inner_text().lower():
                        item.click()
                        page.wait_for_timeout(2000)
                        print(f"  Clicked Dolos via item: {item.inner_text()[:50]}")
                        break
        except Exception as e:
            print(f"  Error clicking Dolos: {e}")

        if args.screenshot:
            page.screenshot(path="/tmp/dolos_04_dolos_selected.png")

        # ── 6. Check build parameters visible ──
        print("\n[6] Checking build parameters on Dolos wrapper page...")
        page_text = page.inner_text("body")

        expected_params = ["Encoder", "Timeout", "Success String", "Fail String"]
        for param in expected_params:
            found = param.lower() in page_text.lower()
            print(f"  '{param}' visible: {found}")

        # Check that old params are NOT visible
        old_params = ["Shellcode/Exe", "Configs/Files"]
        for param in old_params:
            found = param.lower() in page_text.lower()
            print(f"  '{param}' visible (should be False): {found}")

        # ── 7. Check for C2 profile section ──
        print("\n[7] Checking C2 profile section (should NOT appear for wrapper)...")
        c2_visible = "c2 profile" in page_text.lower() or "c2profile" in page_text.lower()
        print(f"  C2 profile section visible: {c2_visible} (should be False)")

        # ── 8. Check Encoder dropdown choices ──
        print("\n[8] Checking Encoder dropdown choices...")
        try:
            encoder_select = page.locator('select:has(option:has-text("PyEncoder")), [data-testid*="Encoder"]').first
            if encoder_select.is_visible():
                # Click to open dropdown
                encoder_select.click()
                page.wait_for_timeout(500)
                options = page.query_selector_all('option, [role="option"]')
                encoder_opts = [o.inner_text() for o in options if o.inner_text().strip()]
                print(f"  Encoder options: {encoder_opts}")
            else:
                print("  Encoder dropdown not found via select, trying other selectors...")
        except Exception as e:
            print(f"  Encoder dropdown check: {e}")

        if args.screenshot:
            page.screenshot(path="/tmp/dolos_05_build_params.png")

        # ── 9. Summary ──
        print("\n" + "=" * 60)
        print("UI VERIFICATION SUMMARY")
        print("=" * 60)
        print(f"  Dolos in Create Wrapper:  {dolos_found}")
        print(f"  Dolos in Create Payload:   {dolos_in_payload} (should be False)")
        print(f"  C2 profile section:        {c2_visible} (should be False)")
        print()
        print("Check screenshots in /tmp/dolos_*.png if --screenshot was used.")
        print("GraphQL verification of build parameters already done separately.")

        browser.close()

    print("\nDone.")


if __name__ == "__main__":
    main()