#!/usr/bin/env python3
"""Trigger a Dolos wrapper build via the Mythic UI and monitor the result.

Creates a Dolos payload that wraps the latest Apollo payload, then
polls until the build completes or fails. Checks debug logs and
Hasura for results.

Usage:
    python3 dev_tools/remote/test_build_trigger.py
"""
import json
import sys
import time
import urllib.request
import urllib.error

# ─── Config ──────────────────────────────────────────────────────────────

MYTHIC_URL = "https://127.0.0.1:7443"
GRAPHQL_URL = f"{MYTHIC_URL}/graphql/"

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
ADMIN_USER = "mythic_admin"
ADMIN_PASS = ENV["MYTHIC_ADMIN_PASSWORD"]
HASURA_SECRET = ENV["HASURA_SECRET"]
HASURA_URL = "http://127.0.0.1:8080/v1/graphql"

# ─── Helpers ─────────────────────────────────────────────────────────────

def mythic_graphql(query, variables=None, token=None):
    """Execute a GraphQL query/mutation against Mythic's GraphQL endpoint."""
    data = {"query": query}
    if variables:
        data["variables"] = variables
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(data).encode(),
        headers=headers,
    )
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  HTTP {e.code}: {body[:200]}")
        return json.loads(body) if body.startswith("{") else {"errors": [{"message": body}]}
    except Exception as e:
        return {"errors": [{"message": str(e)}]}


def hasura_query(query, variables=None):
    """Execute a GraphQL query against Hasura (read-only DB access)."""
    data = {"query": query}
    if variables:
        data["variables"] = variables
    req = urllib.request.Request(
        HASURA_URL,
        data=json.dumps(data).encode(),
        headers={
            "Content-Type": "application/json",
            "x-hasura-admin-secret": HASURA_SECRET,
        },
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())


def get_access_token():
    """Get a JWT access token from Mythic."""
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    data = json.dumps({"username": ADMIN_USER, "password": ADMIN_PASS}).encode()
    req = urllib.request.Request(
        f"{MYTHIC_URL}/auth",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=10, context=ctx)
    result = json.loads(resp.read())
    return result["access_token"]


def check_debug_log():
    """Read the last few lines of Dolos debug log."""
    try:
        with open("/tmp/dolos/dolos.log") as f:
            lines = f.readlines()
            return len(lines), lines[-5:] if lines else []
    except FileNotFoundError:
        return 0, []


# ─── Main ─────────────────────────────────────────────────────────────────

print("=== Dolos Build Trigger Test ===\n")

# Step 1: Check Dolos is online
print("[1] Checking Dolos registration in Mythic...")
result = hasura_query('{ payloadtype(where:{name:{_eq:"dolos"}}) { name wrapper note buildparameters { name parameter_type default_value } } }')
if result.get("errors"):
    print(f"  ERROR: {result['errors']}")
    sys.exit(1)

pt = result["data"]["payloadtype"][0]
print(f"  Name: {pt['name']}")
print(f"  Wrapper: {pt['wrapper']}")
print(f"  Note: {pt['note'][:60]}...")
print(f"  Build params: {', '.join(p['name'] for p in pt['buildparameters'])}")

# Step 2: Find an Apollo payload to wrap
print("\n[2] Finding a successful Apollo payload to wrap...")
result = hasura_query('{ payload(where:{build_phase:{_eq:"success"}, payloadtype:{name:{_eq:"apollo"}}}, limit:1, order_by:{id:desc}) { id uuid description } }')
if result.get("errors") or not result["data"]["payload"]:
    print("  No Apollo payloads found. You need to create one first in the Mythic UI.")
    sys.exit(1)

apollo = result["data"]["payload"][0]
print(f"  Wrapping Apollo payload: id={apollo['id']} uuid={apollo['uuid']}")
print(f"  Description: {apollo['description']}")

# Step 3: Get access token
print("\n[3] Getting Mythic access token...")
token = get_access_token()
print(f"  Token: {token[:30]}...")

# Step 4: Create the payload
print("\n[4] Creating Dolos wrapper payload...")
build_params = [
    {"name": "Encoder", "value": "PyEncoder_v1.0"},
    {"name": "Timeout", "value": "300"},
    {"name": "Success String", "value": "ENCODING_SUCCESS"},
    {"name": "Fail String", "value": "ENCODING_FAILED"},
]

result = mythic_graphql(
    """mutation CreatePayload($payload: payloadInput!) {
        createPayload(payload: $payload) {
            status
            error
            payload_uuid
        }
    }""",
    variables={"payload": {
        "description": "v0.9.2 local debug build test",
        "payload_type": "dolos",
        "operation_id": 1,
        "wrapped_payload_uuid": apollo["uuid"],
        "build_parameters": build_params,
    }},
    token=token,
)

if result.get("errors"):
    print(f"  ERROR: {json.dumps(result['errors'], indent=2)}")
    # Try alternative mutation format
    print("\n  Trying Hasura direct insert approach...")
    sys.exit(1)

create_result = result.get("data", {}).get("createPayload", {})
status = create_result.get("status", "unknown")
error = create_result.get("error", "")
payload_uuid = create_result.get("payload_uuid", "")

print(f"  Status: {status}")
if error:
    print(f"  Error: {error}")
if payload_uuid:
    print(f"  Payload UUID: {payload_uuid}")

# Step 5: Poll for build result
if payload_uuid:
    print(f"\n[5] Polling for build result (UUID: {payload_uuid})...")
    for i in range(30):
        time.sleep(2)
        result = hasura_query(
            '{ payload(where:{uuid:{_eq:"' + payload_uuid + '"}}) { id uuid build_phase build_message } }'
        )
        payload = result["data"]["payload"][0]
        phase = payload["build_phase"]
        msg = payload.get("build_message", "")[:100] if payload.get("build_message") else ""
        log_count, last_lines = check_debug_log()
        print(f"  [{i*2}s] phase={phase} log_lines={log_count} msg={msg}")
        if phase in ("success", "failed", "error"):
            break

    # Final check
    result = hasura_query(
        '{ payload(where:{uuid:{_eq:"' + payload_uuid + '"}}) { id uuid build_phase build_message } }'
    )
    payload = result["data"]["payload"][0]
    print(f"\n[6] Final result:")
    print(f"  Phase: {payload['build_phase']}")
    print(f"  Message: {(payload.get('build_message') or '')[:200]}")

    log_count, last_lines = check_debug_log()
    print(f"\n  Debug log: {log_count} lines written to /tmp/dolos/dolos.log")
    if last_lines:
        print("  Last 5 log lines:")
        for line in last_lines:
            print(f"    {line.rstrip()}")
else:
    print("\n  No payload UUID returned. Cannot poll for result.")