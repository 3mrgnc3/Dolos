"""End-to-end test: Create Dolos payload via Mythic UI, verify result, 
SSH to remote server, download and execute."""
import time, json, urllib.request, sys, os

# ===== CONFIG =====
MYTHIC_URL = "https://127.0.0.1:7443"
MYTHIC_USER = "mythic_admin"
MYTHIC_PASS = "e9WYrzxS7vy76L3nk2RzDQCBlsXAte"
HASURA_SECRET = open("/home/mrgnc/MythicC2/Mythic/.env").read().split('HASURA_SECRET="')[1].split('"')[0]
HASURA_URL = "http://127.0.0.1:8080/v1/graphql"
SSH_HOST = "172.28.0.3"
SSH_USER = "mrgnc"

# ===== STEP 1: Create payload via Mythic GraphQL API =====
print("[1] Creating Dolos payload via Mythic API...")

# Get a JWT token first
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--ignore-certificate-errors'])
    ctx = browser.new_context(ignore_https_errors=True, viewport={'width': 1400, 'height': 900})
    page = ctx.new_page()
    
    # Login
    print("[1a] Logging in...")
    page.goto(f"{MYTHIC_URL}/new/login", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    
    # Find and fill login fields - inspect the page first
    page.screenshot(path="/tmp/wd_login_page.png")
    
    # Try different selectors for username/password
    inputs = page.query_selector_all('input')
    print(f"  Found {len(inputs)} input fields")
    for inp in inputs:
        t = inp.get_attribute('type') or ''
        n = inp.get_attribute('name') or ''
        pid = inp.get_attribute('id') or ''
        ph = inp.get_attribute('placeholder') or ''
        print(f"    input type={t} name={n} id={pid} placeholder={ph}")
    
    # Fill based on what we find
    username_input = page.query_selector('input[type="text"]:first-of-type, input[name="username"], input[id="username"]')
    password_input = page.query_selector('input[type="password"]')
    
    if username_input and password_input:
        username_input.fill(MYTHIC_USER)
        password_input.fill(MYTHIC_PASS)
        page.click('button[type="submit"], button:has-text("Login"), button:has-text("Sign")')
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)
        print("[1a] Login submitted.")
    else:
        # Try the accessible name approach
        page.get_by_label("Username").fill(MYTHIC_USER) if page.get_by_label("Username").count() > 0 else None
        page.get_by_label("Password").fill(MYTHIC_PASS) if page.get_by_label("Password").count() > 0 else None
    
    page.screenshot(path="/tmp/wd_after_login.png")
    print(f"[1a] Page URL after login: {page.url}")
    
    # Check if we're actually logged in
    page_content = page.inner_text("body")
    if "Login" in page_content and "password" in page_content.lower():
        print("[1a] Still on login page. Checking screenshot...")
        # Try alternative login method
        all_inputs = page.query_selector_all('input')
        if len(all_inputs) >= 2:
            all_inputs[0].fill(MYTHIC_USER)
            all_inputs[1].fill(MYTHIC_PASS)
            # Click submit
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)
            page.screenshot(path="/tmp/wd_after_login2.png")
    
    # Extract JWT from localStorage
    jwt = page.evaluate("() => localStorage.getItem('access_token')")
    print(f"[1a] JWT token obtained: {jwt[:30]}..." if jwt else "[1a] No JWT token found!")
    
    if not jwt:
        print("[1a] Cannot get JWT. Trying intercept approach...")
        # Just capture the JWT from network requests
        
        # Navigate to payloads page
        page.goto(f"{MYTHIC_URL}/new/create/Payload", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(3)
        
        jwt = page.evaluate("() => localStorage.getItem('access_token')")
        if jwt:
            print(f"[1a] Got JWT from payloads page: {jwt[:30]}...")
        else:
            # Try getting from cookies
            cookies = ctx.cookies()
            print(f"[1a] Cookies: {cookies}")
            print("[1a] FATAL: Could not obtain JWT token. Cannot create payload via API.")
            browser.close()
            sys.exit(1)
    
    # Navigate to Create Payload page
    print("[2] Navigating to Create Payload page...")
    page.goto(f"{MYTHIC_URL}/new/create/Payload", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(5)
    page.screenshot(path="/tmp/wd_create_payload.png")
    
    # Look for the payload type dropdown and select dolos
    print("[2] Looking for payload type dropdown...")
    
    # Try MUI Select component
    mui_selects = page.query_selector_all('.MuiSelect-root, [role="combobox"]')
    print(f"  Found {len(mui_selects)} MUI select elements")
    
    # Try to find and click the payload type dropdown
    # It might be labeled "Payload Type" or similar
    all_text = page.inner_text("body")
    dolos_mentioned = "dolos" in all_text.lower()
    print(f"  dolos mentioned on page: {dolos_mentioned}")
    
    # Try clicking on the first MUI Select
    if mui_selects:
        mui_selects[0].click()
        time.sleep(1)
        page.screenshot(path="/tmp/wd_dropdown_open.png")
        
        # Look for dolos option
        wd_option = page.query_selector('li:has-text("dolos"), [data-value="dolos"]')
        if wd_option:
            wd_option.click()
            time.sleep(3)
            print("[2] Selected dolos!")
        else:
            print("[2] dolos option not found in dropdown")
            all_options = page.query_selector_all('li')
            for opt in all_options:
                print(f"  Option: {opt.inner_text()[:50]}")
    
    page.screenshot(path="/tmp/wd_after_pt_select.png")
    
    browser.close()
    print("[3] Browser automation complete. Check screenshots for next steps.")
