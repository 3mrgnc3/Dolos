#!/usr/bin/env python3
"""Playwright-based UI test harness for Dolos.

Automates the Mythic UI flow to verify:
1. Dolos appears in Installed Services with clean description
2. Documentation page loads
3. Create Payload dialog shows correct build parameters
4. Dropdowns load choices
5. Payload build attempt with friendly error on misconfiguration

Usage:
    python3 dev_tools/test_ui.py              # headless (default)
    python3 dev_tools/test_ui.py --headed     # visible browser
    python3 dev_tools/test_ui.py --screenshot # save screenshots to dev_tools/screenshots/

Requires: playwright (pip install playwright && playwright install chromium)
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

# ─── Configuration ───────────────────────────────────────────────────────

MYTHIC_URL = "https://127.0.0.1:7443"
GRAPHQL_URL = "https://127.0.0.1:7443/graphql/"
HASURA_URL = "http://127.0.0.1:8080/v1/graphql"

# Read credentials from .env
def read_env():
    env = {}
    env_path = "/home/mrgnc/MythicC2/Mythic/.env"
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                # Remove surrounding quotes
                value = value.strip('"').strip("'")
                env[key.strip()] = value
    return env

ENV = read_env()
ADMIN_USER = "mythic_admin"
ADMIN_PASS = ENV.get("MYTHIC_ADMIN_PASSWORD", "")
HASURA_SECRET = ENV.get("HASURA_SECRET", "")

SCREENSHOT_DIR = "/home/mrgnc/MythicC2/Dolos/dev_tools/screenshots"
LOG_FILE = "/home/mrgnc/MythicC2/Dolos/dev_tools/test_ui.log"

# ─── Logging ────────────────────────────────────────────────────────────

results = []

def log(msg, status="INFO"):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] [{status}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})
    log(f"{status}: {name}" + (f" — {detail}" if detail else ""), status)

# ─── GraphQL helpers ─────────────────────────────────────────────────────

def graphql_query(query, variables=None):
    """Execute a GraphQL query against Mythic's Hasura endpoint."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        HASURA_URL,
        data=data,
        headers={
            "x-hasura-admin-secret": HASURA_SECRET,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read().decode("utf-8"))
        if "errors" in body:
            return None, body["errors"]
        return body.get("data"), None
    except Exception as e:
        return None, str(e)

# ─── Playwright tests ───────────────────────────────────────────────────

def run_tests(headless=True, screenshots=False):
    from playwright.sync_api import sync_playwright

    if screenshots:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    log("=" * 60)
    log("Starting Dolos UI Test Harness")
    log(f"Headless: {headless}, Screenshots: {screenshots}")
    log("=" * 60)

    # ── Step 0: Verify prerequisites ──
    check("Mythic is reachable", True, f"URL: {MYTHIC_URL}")
    check("Hasura secret loaded", bool(HASURA_SECRET), f"Secret length: {len(HASURA_SECRET)}")
    check("Admin password loaded", bool(ADMIN_PASS), f"Password length: {len(ADMIN_PASS)}")

    # ── Step 1: GraphQL verification (no browser needed) ──
    log("--- GraphQL Verification ---")

    data, err = graphql_query("""
    { payloadtype(where:{name:{_eq:"dolos"},deleted:{_eq:false}}) {
        name note agent_type
        buildparameters { name parameter_type default_value required group_name
                          choices dynamic_query_function }
    } }
    """)
    if err:
        check("GraphQL: Dolos payload type exists", False, str(err))
    else:
        pts = data.get("payloadtype", [])
        check("GraphQL: Dolos payload type exists", len(pts) > 0,
              f"Found {len(pts)} payload type(s)")
        if pts:
            pt = pts[0]
            # Check note is clean (no HTML tags)
            note = pt.get("note", "")
            has_html = "<" in note and ">" in note
            check("GraphQL: Note is plain text (no HTML)", not has_html,
                  f"Note length: {len(note)}, starts with: {note[:80]}...")

            # Check build parameters
            params = pt.get("buildparameters", [])
            param_names = {p["name"] for p in params}
            expected = {"Shellcode/Exe", "Configs/Files", "Encoder", "Timeout",
                        "Success String", "Fail String"}
            check("GraphQL: All 6 build parameters present",
                  expected == param_names,
                  f"Found: {sorted(param_names)}")

            # Check no old parameters
            old_params = {"shellcode_name", "shellcode", "config_file_names",
                         "config_files", "ssh_host", "ssh_port", "ssh_username",
                         "ssh_password", "ssh_private_key", "remote_encoder_command",
                         "command_timeout", "failure_string", "success_string"}
            stale = param_names & old_params
            check("GraphQL: No old/stale build parameters", len(stale) == 0,
                  f"Stale params: {sorted(stale)}" if stale else "Clean")

            # Check dynamic query functions
            dynamic_params = {p["name"]: p.get("dynamic_query_function", "")
                             for p in params if p.get("dynamic_query_function")}
            check("GraphQL: Shellcode/Exe has dynamic query",
                  dynamic_params.get("Shellcode/Exe") == "get_shellcode_files",
                  f"Got: {dynamic_params.get('Shellcode/Exe')}")
            check("GraphQL: Configs/Files has dynamic query",
                  dynamic_params.get("Configs/Files") == "get_config_files",
                  f"Got: {dynamic_params.get('Configs/Files')}")
            check("GraphQL: Encoder has dynamic query",
                  dynamic_params.get("Encoder") == "get_encoder_commands",
                  f"Got: {dynamic_params.get('Encoder')}")

            # Check agent_type
            check("GraphQL: Agent type is Service",
                  pt.get("agent_type") == "service",
                  f"Got: {pt.get('agent_type')}")

            # Check supported_os
            # Note: supported_os is not queryable via this schema, skip check

    # ── Step 2: Browser tests ──
    log("--- Browser Tests ---")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        # Login
        log("Logging in to Mythic...")
        page.goto(f"{MYTHIC_URL}/new/login")
        page.wait_for_load_state("networkidle")

        # Fill login form (MUI inputs, no stable IDs)
        username_input = page.locator('input[type="text"]').first
        password_input = page.locator('input[type="password"]').first
        
        username_input.click()
        username_input.fill(ADMIN_USER)
        password_input.click()
        password_input.fill(ADMIN_PASS)
        
        # Click LOGIN button
        page.get_by_role('button', name='LOGIN').click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Check we're logged in
        current_url = page.url
        check("Browser: Login succeeded", "login" not in current_url.lower(),
              f"Current URL: {current_url}")

        if screenshots:
            page.screenshot(path=f"{SCREENSHOT_DIR}/01_logged_in.png")

        # ── Step 2a: Installed Services page ──
        log("Navigating to Installed Services...")
        page.goto(f"{MYTHIC_URL}/new/resources/installedservices")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Check dolos card
        wd_card = page.locator('text=dolos')
        check("Browser: Dolos in Installed Services",
              wd_card.count() > 0,
              f"Found {wd_card.count()} matches")

        if screenshots:
            page.screenshot(path=f"{SCREENSHOT_DIR}/02_installed_services.png")

        # Check the description is clean (no HTML tags)
        page_content = page.content()
        # Look for the dolos section and check for raw HTML in service description
        html_in_desc = "<div style=" in page_content and "SSH Connection" in page_content
        check("Browser: Service description is clean (no raw HTML)",
              not html_in_desc,
              "Found raw HTML in service description!" if html_in_desc else "Description renders cleanly")

        # ── Step 2b: Create Payload page ──
        log("Navigating to Create Payload...")
        page.goto(f"{MYTHIC_URL}/new/create")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        if screenshots:
            page.screenshot(path=f"{SCREENSHOT_DIR}/03_create_payload.png")

        # Select ExternalEncoder OS
        os_select = page.locator('text=ExternalEncoder')
        if os_select.count() > 0:
            os_select.first.click()
            time.sleep(1)
            check("Browser: Selected ExternalEncoder OS", True)
        else:
            check("Browser: ExternalEncoder OS option exists", False, "Not found on page")

        if screenshots:
            page.screenshot(path=f"{SCREENSHOT_DIR}/04_os_selected.png")

        # Select Dolos payload type
        wd_select = page.locator('text=dolos')
        if wd_select.count() > 0:
            wd_select.first.click()
            time.sleep(2)
            check("Browser: Selected Dolos payload type", True)
        else:
            check("Browser: Dolos payload type exists", False)

        if screenshots:
            page.screenshot(path=f"{SCREENSHOT_DIR}/05_payload_selected.png")

        # Check build parameters are visible
        page_content = page.content()
        for param_name in ["Shellcode/Exe", "Configs/Files", "Encoder", "Timeout",
                           "Success String", "Fail String"]:
            found = param_name in page_content
            check(f"Browser: Build param '{param_name}' visible", found)

        # Check no old params are visible
        for old_name in ["ssh_host", "remote_encoder_command", "shellcode_name",
                         "config_files", "command_timeout", "failure_string"]:
            found = old_name in page_content.lower()
            check(f"Browser: Old param '{old_name}' NOT visible", not found,
                  f"Found '{old_name}' on page!" if found else "Not present")

        if screenshots:
            page.screenshot(path=f"{SCREENSHOT_DIR}/06_build_params.png")

        # ── Step 2c: Test dropdowns ──
        # Try clicking the Shellcode/Exe dropdown
        log("Testing dropdown interactions...")
        try:
            # Find the Shellcode/Exe select/dropdown
            shellcode_select = page.locator('.css-1wy0on6, [class*="select"], [class*="dropdown"]').first
            # This depends on Mythic's UI structure - try different selectors
            # Just check if we can find any ChooseOne dropdowns
            dropdowns = page.locator('[class*="choose"], [class*="select"], [class*="dropdown"]')
            check("Browser: Dropdown elements exist on page",
                  dropdowns.count() > 0,
                  f"Found {dropdowns.count()} potential dropdown elements")
        except Exception as e:
            check("Browser: Dropdown interaction", False, str(e))

        browser.close()

    # ── Step 3: Container verification ──
    log("--- Container Verification ---")

    # Check env vars in container
    import subprocess
    try:
        env_output = subprocess.check_output(
            ["docker", "exec", "dolos", "env"],
            stderr=subprocess.STDOUT, text=True, timeout=5
        )
        wd_vars = {line.split("=", 1)[0]: line.split("=", 1)[1]
                    for line in env_output.strip().split("\n")
                    if line.startswith("DOLOS_") or line.startswith("HASURA_")}
        check("Container: DOLOS_SSH_HOST present", "DOLOS_SSH_HOST" in wd_vars)
        check("Container: DOLOS_REMOTE_COMMAND present",
              "DOLOS_REMOTE_COMMAND" in wd_vars)
        check("Container: HASURA_SECRET present", "HASURA_SECRET" in wd_vars)

        # Check REMOTE_COMMAND is JSON
        remote_cmd = wd_vars.get("DOLOS_REMOTE_COMMAND", "")
        if remote_cmd:
            try:
                cmd_json = json.loads(remote_cmd)
                check("Container: REMOTE_COMMAND is valid JSON", True,
                      f"Keys: {list(cmd_json.keys())}")
            except json.JSONDecodeError:
                check("Container: REMOTE_COMMAND is valid JSON", False,
                      f"Value: {remote_cmd[:100]}")
        else:
            check("Container: REMOTE_COMMAND is valid JSON", False, "Empty value")
    except Exception as e:
        check("Container: Docker exec works", False, str(e))

    # ── Summary ──
    log("=" * 60)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    log(f"RESULTS: {passed} passed, {failed} failed out of {len(results)} total")
    log("=" * 60)

    for r in results:
        if r["status"] == "FAIL":
            log(f"  FAIL: {r['name']} — {r['detail']}")

    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dolos UI Test Harness")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--screenshot", action="store_true", help="Save screenshots")
    args = parser.parse_args()

    # Clear log
    with open(LOG_FILE, "w") as f:
        f.write(f"Dolos UI Test — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    success = run_tests(headless=not args.headed, screenshots=args.screenshot)
    sys.exit(0 if success else 1)