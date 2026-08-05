"""Automated end-to-end test: Create Dolos payload via Mythic UI, 
monitor build status, verify result file has content, and report outcome."""
import time, json, urllib.request
from playwright.sync_api import sync_playwright

MYTHIC_URL = "https://127.0.0.1:7443"

# Get Hasura secret for DB queries
with open("/home/mrgnc/MythicC2/Mythic/.env") as f:
    HASURA_SECRET = f.read().split('HASURA_SECRET="')[1].split('"')[0]

def check_newest_payload():
    """Check the newest Dolos payload's file size."""
    url = 'http://127.0.0.1:8080/v1/graphql'
    headers = {'x-hasura-admin-secret': HASURA_SECRET, 'Content-Type': 'application/json'}
    data = json.dumps({'query': '''{ payload(where:{payloadtype:{name:{_eq:"dolos"}}}, order_by:{id:desc}, limit:1) { id uuid build_phase build_message file_id filemeta { id size filename agent_file_id } } }'''}).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    resp = urllib.request.urlopen(req, timeout=10)
    result = json.loads(resp.read())
    if result['data']['payload']:
        p = result['data']['payload'][0]
        fm = p.get('filemeta', {})
        name = fm.get('filename', b'')
        if isinstance(name, str) and name.startswith('\\x'):
            try: name = bytes.fromhex(name[2:]).decode()
            except: pass
        return {
            'id': p['id'],
            'uuid': p['uuid'],
            'phase': p['build_phase'],
            'msg': p.get('build_message',''),
            'file_size': fm.get('size', -1),
            'file_name': name,
        }
    return None

def get_jwt_token(page):
    """Get JWT token from browser localStorage."""
    token = page.evaluate("() => localStorage.getItem('access_token')")
    return token

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, ignore_default_args=['--ignore-certificate-errors'], args=['--ignore-certificate-errors'])
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    
    print("[1] Logging in to Mythic...")
    page.goto(f"{MYTHIC_URL}/new/login", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    
    # Fill in login form
    username_field = page.locator('input[type="text"], input[name="username"]').first
    password_field = page.locator('input[type="password"]').first
    
    username_field.fill("mythic_admin")
    password_field.fill("e9WYrzxS7vy76L3nk2RzDQCBlsXAte")
    
    # Click login button
    login_btn = page.locator('button:has-text("Login"), button[type="submit"]').first
    login_btn.click()
    page.wait_for_load_state("networkidle", timeout=15000)
    print("[1] Logged in.")
    
    # Navigate to Create Payload
    print("[2] Navigating to Create Payload...")
    page.goto(f"{MYTHIC_URL}/new/create/Payload", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(3)  # Let the form fully render
    
    # Take a screenshot to see current state
    page.screenshot(path="/tmp/wd_step2_payload_form.png")
    
    # Select Dolos payload type
    print("[2] Selecting Dolos payload type...")
    # Look for dropdown or selection
    pt_select = page.locator('select, [role="combobox"], .MuiSelect-root').first
    if pt_select.is_visible():
        pt_select.click()
        time.sleep(1)
        # Find dolos option
        wd_option = page.locator('li:has-text("dolos"), option:has-text("dolos")').first
        if wd_option.is_visible():
            wd_option.click()
            time.sleep(2)
    else:
        # Try clicking on the payload type dropdown a different way
        # Look for the payload type label
        page.screenshot(path="/tmp/wd_step2_no_dropdown.png")
        print("  Cannot find payload type dropdown, trying alternative approach...")
    
    page.screenshot(path="/tmp/wd_step2_after_select.png")
    
    # Check current state of the page text
    page_text = page.inner_text("body")
    if "dolos" in page_text.lower():
        print("  Dolos found on page")
    else:
        print(f"  Page content (first 500): {page_text[:500]}")
    
    browser.close()
    print("Done with browser automation prep.")
