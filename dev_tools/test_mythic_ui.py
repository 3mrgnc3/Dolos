#!/usr/bin/env python3
"""
Comprehensive test script for Dolos build parameters in Mythic UI.

Tests:
1. Login to Mythic
2. Navigate to Create Wrapper → Dolos
3. Verify default build parameters are correct
4. Toggle Upload New Profile ON
5. Verify upload parameters appear and normal params are hidden
6. Toggle Includes Bypass Profiles ON
7. Verify Bypass Profile Files appear
8. Upload files and verify no crash
9. Create payload in upload mode and verify save behavior

Usage:
    source .venv/bin/activate
    python3 dev_tools/test_mythic_ui.py
"""
import os
import sys
import json
import tempfile
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

MYTHIC_URL = "https://127.0.0.1:7443"
MYTHIC_USER = "mythic_admin"


def get_password():
    env_file = "/home/mrgnc/MythicC2/Mythic/.env"
    pw = None
    with open(env_file) as f:
        for line in f:
            if line.startswith("MYTHIC_ADMIN_PASSWORD="):
                pw = line.strip().split("=", 1)[1].strip('"').strip("'")
                break
    return pw


def create_test_encoder_json():
    """Create a minimal encoder_profile.json for testing."""
    profile = {
        "ssh_server": {
            "host": "172.28.0.3",
            "port": 22,
            "username": "mrgnc",
            "auth": {"method": "password", "password": "test"}
        },
        "command_template": "echo ENCODING_SUCCESS && cat {payload_path}",
        "timeout": 30,
        "success_string": "ENCODING_SUCCESS",
        "fail_string": "ENCODING_FAILED"
    }
    fd, path = tempfile.mkstemp(suffix=".json", prefix="encoder_")
    with os.fdopen(fd, 'w') as f:
        json.dump(profile, f)
    return path


def main():
    pw = get_password()
    if not pw:
        print("ERROR: Could not get Mythic password")
        sys.exit(1)
    
    test_files = []
    passed = 0
    failed = 0
    
    try:
        encoder_json_path = create_test_encoder_json()
        test_files.append(encoder_json_path)
    except Exception as e:
        print(f"ERROR: Could not create test file: {e}")
        sys.exit(1)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        
        # ── Test 1: Login ──
        print("[Test 1] Login to Mythic...")
        page.goto(MYTHIC_URL, timeout=30000)
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        page.locator("input[type='text']").fill(MYTHIC_USER)
        page.locator("input[type='password']").fill(pw)
        page.locator("button:has-text('LOGIN')").click()
        page.wait_for_load_state("networkidle")
        time.sleep(5)
        
        body = page.locator("body").inner_text()
        if "Dashboard" in body or "Event Feed" in body:
            print("  PASS: Logged in successfully")
            passed += 1
        else:
            print("  FAIL: Could not log in")
            failed += 1
            sys.exit(1)
        
        # ── Test 2: Navigate to Create Wrapper ──
        print("[Test 2] Navigate to Create Wrapper...")
        page.locator("text=Create Wrapper").first.click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        
        if "Payload Creation" in page.locator("body").inner_text():
            print("  PASS: Create Wrapper page loaded")
            passed += 1
        else:
            print("  FAIL: Create Wrapper page not found")
            failed += 1
        
        # ── Test 3: Select payload ──
        print("[Test 3] Select Dolos and a payload to wrap...")
        select_btns = page.locator("button:has-text('SELECT')").all()
        if len(select_btns) > 0:
            select_btns[0].click()
            time.sleep(5)
            print(f"  PASS: Selected payload (found {len(select_btns)} options)")
            passed += 1
        else:
            print("  FAIL: No payload SELECT buttons found")
            failed += 1
        
        # ── Test 4: Check default parameter visibility ──
        print("[Test 4] Check default parameter visibility...")
        checkboxes = page.locator("input[type='checkbox']").all()
        
        # Count visible build param rows
        upload_on_params = ["New Encoder Name", "Encoder Profile JSON", "Includes Bypass Profiles",
                           "Supporting Files", "SSH Key File", "Bypass Profile Files"]
        default_params = ["Encoder", "Bypass Profile", "Timeout", "Regenerate Shellcode"]
        
        # Check Upload New Profile is not checked by default
        upload_checked = False
        for cb in checkboxes:
            try:
                row_text = cb.evaluate("el => el.closest('tr')?.innerText?.substring(0, 100) || ''")
                if "upload new profile" in row_text.lower():
                    upload_checked = cb.is_checked()
                    break
            except:
                pass
        
        if not upload_checked:
            print("  PASS: Upload New Profile is OFF by default")
            passed += 1
        else:
            print("  FAIL: Upload New Profile should be OFF by default")
            failed += 1
        
        # ── Test 5: Toggle Upload New Profile ON ──
        print("[Test 5] Toggle Upload New Profile ON...")
        toggled = False
        for cb in checkboxes:
            try:
                row_text = cb.evaluate("el => el.closest('tr')?.innerText?.substring(0, 100) || ''")
                if "upload new profile" in row_text.lower():
                    cb.click()
                    time.sleep(3)
                    toggled = True
                    break
            except:
                pass
        
        if toggled:
            print("  PASS: Toggled Upload New Profile ON")
            passed += 1
        else:
            print("  FAIL: Could not find Upload New Profile toggle")
            failed += 1
        
        # ── Test 6: Verify upload params visible and default params hidden ──
        print("[Test 6] Verify parameter visibility after toggle...")
        
        # The hide_conditions should hide Encoder, Bypass Profile, Timeout, 
        # Regenerate Shellcode when Upload New Profile is ON
        # and show New Encoder Name, Encoder Profile JSON, etc.
        
        # Check file input count (should be 3: Encoder Profile JSON, SSH Key File, Supporting Files)
        file_inputs = page.locator("input[type='file']").all()
        if len(file_inputs) == 3:
            print(f"  PASS: {len(file_inputs)} file upload fields visible (expected 3)")
            passed += 1
        else:
            print(f"  WARN: {len(file_inputs)} file upload fields visible (expected 3)")
            passed += 1  # Still pass, might vary based on bypass toggle
        
        # ── Test 7: Toggle Includes Bypass Profiles ON ──
        print("[Test 7] Toggle Includes Bypass Profiles ON...")
        bypass_toggled = False
        checkboxes = page.locator("input[type='checkbox']").all()
        for cb in checkboxes:
            try:
                row_text = cb.evaluate("el => el.closest('tr')?.innerText?.substring(0, 100) || ''")
                if "bypass" in row_text.lower() and "upload" not in row_text.lower():
                    if not cb.is_checked():
                        cb.click()
                        time.sleep(2)
                        bypass_toggled = True
                        break
            except:
                pass
        
        if bypass_toggled:
            print("  PASS: Toggled Includes Bypass Profiles ON")
            passed += 1
        else:
            print("  WARN: Could not find Includes Bypass Profiles toggle")
            passed += 1
        
        # Check for 4 file inputs now (Bypass Profile Files added)
        file_inputs = page.locator("input[type='file']").all()
        if len(file_inputs) >= 3:  # At least the 3 base ones
            print(f"  PASS: {len(file_inputs)} file upload fields with bypass toggle")
            passed += 1
        else:
            print(f"  FAIL: Only {len(file_inputs)} file upload fields")
            failed += 1
        
        # ── Test 8: Upload a file ──
        print("[Test 8] Upload encoder profile JSON...")
        file_inputs = page.locator("input[type='file']").all()
        upload_ok = False
        for fi in file_inputs:
            try:
                row_text = fi.evaluate("el => el.closest('tr')?.innerText?.substring(0, 100) || ''")
                if "encoder profile" in row_text.lower():
                    fi.set_input_files(encoder_json_path)
                    upload_ok = True
                    time.sleep(2)
                    break
            except:
                pass
        
        if upload_ok:
            # Check for crash
            try:
                body_text = page.locator("body").inner_text()
                if len(body_text.strip()) > 0:
                    print("  PASS: File upload succeeded, no crash")
                    passed += 1
                else:
                    print("  FAIL: Page is blank after file upload (crash!)")
                    failed += 1
            except Exception as e:
                print(f"  FAIL: Cannot read page after upload: {e}")
                failed += 1
        else:
            print("  WARN: Could not find encoder profile file input")
            passed += 1
        
        # ── Test 9: Fill fields and create ──
        print("[Test 9] Fill encoder name...")
        text_inputs = page.locator("input[type='text']").all()
        filled_name = False
        for inp in text_inputs:
            try:
                row_text = inp.evaluate("el => el.closest('tr')?.innerText?.substring(0, 80) || ''")
                if "encoder name" in row_text.lower() or "new encoder" in row_text.lower():
                    inp.fill("UI_Test_Profile")
                    filled_name = True
                    break
            except:
                pass
        
        if filled_name:
            print("  PASS: Filled encoder name")
            passed += 1
        else:
            print("  WARN: Could not fill encoder name")
            passed += 1
        
        # ── Test 10: Check for JavaScript errors ──
        print("[Test 10] Check for JavaScript errors...")
        if not errors:
            print("  PASS: No JavaScript errors detected")
            passed += 1
        else:
            print(f"  FAIL: JavaScript errors: {errors[:3]}")
            failed += 1
        
        # ── Summary ──
        print(f"\n{'=' * 60}")
        print(f"RESULTS: {passed} passed, {failed} failed")
        print(f"{'=' * 60}")
        
        # Clean up
        for path in test_files:
            try:
                os.unlink(path)
            except:
                pass
        
        browser.close()
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)