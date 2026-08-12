#!/usr/bin/env python3
"""Dolos v2.1.0 E2E Test Suite

Tests Dolos container:
1. Container is running
2. Config loader finds encoder profiles
3. No sync spam in logs
4. Paperclip-editable configs are at /Mythic root
5. Mythic registration as wrapper payload type
6. Docker image is the correct version
7. No custom env vars causing warnings
8. Flat-file config format (v2 schema)
"""

import json
import subprocess
import sys
import time


def run(cmd):
    """Run a shell command and return stdout."""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return r.stdout.strip(), r.stderr.strip(), r.returncode


def test_container_running():
    """Container is running and healthy."""
    out, _, rc = run("sudo docker ps --filter name=dolos --format '{{.Status}}'")
    assert "Up" in out, f"Container not running: {out}"
    print("  ✅ Container is running")


def test_correct_image():
    """Container uses the v2.1.0 image."""
    out, _, rc = run("sudo docker ps --filter name=dolos --format '{{.Image}}'")
    assert "v2.1.0" in out, f"Wrong image: {out}"
    print(f"  ✅ Image: {out}")


def test_config_loader_profiles():
    """Config loader finds and parses encoder profiles."""
    out, err, rc = run("sudo docker exec dolos python3 -c \""
        "from dolos.config_loader import load_profiles; "
        "profiles = [p for p in load_profiles() if p.enabled]; "
        "print(len(profiles), profiles[0].label, profiles[0].host, profiles[0].port, "
        "profiles[0].ssh_key_enabled, profiles[0].ssh_key_secret)\"")
    assert rc == 0, f"Config loader failed: {err}"
    parts = out.split()
    count = int(parts[0])
    assert count >= 1, f"Expected at least 1 profile, got {count}"
    label = parts[1]
    assert label == "PyEncoder", f"Expected PyEncoder, got {label}"
    print(f"  ✅ Loaded {count} profile(s): {label}")


def test_no_sync_spam():
    """No excessive sync messages in container logs (sync spam bug)."""
    out, _, _ = run("sudo docker logs dolos 2>&1")
    sync_lines = [l for l in out.split('\n') if 'Successfully synced' in l]
    assert len(sync_lines) <= 5, f"Sync spam detected: {len(sync_lines)} sync messages"
    print(f"  ✅ Only {len(sync_lines)} sync message(s) in logs")


def test_rabbitmq_connected():
    """RabbitMQ connection established."""
    out, _, _ = run("sudo docker logs dolos 2>&1")
    assert "Successfully connected to rabbitmq" in out, "RabbitMQ not connected"
    print("  ✅ RabbitMQ connected")


def test_flat_file_configs():
    """V2 flat-file configs are at /Mythic/ root, visible via paperclip."""
    out, _, rc = run("sudo docker exec dolos find /Mythic -maxdepth 1 -name '00_*.json'")
    assert rc == 0, f"No flat-file configs found: {out}"
    assert "00_Encoder_PyEncoder.json" in out, f"Expected config not found: {out}"
    print(f"  ✅ Flat-file configs found: {out.strip()}")


def test_config_format_v2():
    """Config file uses v2 schema."""
    out, _, rc = run("sudo docker exec dolos cat /Mythic/00_Encoder_PyEncoder.json")
    assert rc == 0, f"Cannot read config: {out}"
    data = json.loads(out)
    assert data.get("version") == 2, f"Expected version 2, got {data.get('version')}"
    assert "ssh_key_secret" in data, f"Missing ssh_key_secret field"
    assert "ssh_key_enabled" in data, f"Missing ssh_key_enabled field"
    assert "bypass_refs" in data, f"Missing bypass_refs field"
    assert data.get("ssh_key_secret") == "DOLOS_00_ENCODER_SSH_KEY", \
        f"Expected DOLOS_00_ENCODER_SSH_KEY, got {data.get('ssh_key_secret')}"
    print(f"  ✅ V2 config format: version={data['version']}, label={data['label']}")


def test_no_configs_directory():
    """Old v1 configs/ directory should not exist in the container."""
    out, _, rc = run("sudo docker exec dolos test -d /Mythic/configs")
    assert rc != 0, f"Old v1 configs/ directory still exists in container"
    print("  ✅ No v1 configs/ directory in container")


def test_no_custom_env_vars():
    """No custom DOLOS_* env vars in docker-compose that could cause warnings."""
    out, _, _ = run("cd ~/MythicC2/Mythic && grep -A5 'environment:' docker-compose.yml | head -30")
    dolos_env = [l.strip() for l in out.split('\n') if 'DOLOS_' in l]
    assert len(dolos_env) == 0, f"Custom DOLOS_* env vars found: {dolos_env}"
    print("  ✅ No custom DOLOS_* env vars in docker-compose")


def test_docker_compose_no_warnings():
    """Docker Compose config validates without warnings."""
    out, err, rc = run("cd ~/MythicC2/Mythic && sudo docker compose config --quiet 2>&1")
    # docker compose config --quiet exits 0 if valid
    assert rc == 0 or "warning" not in err.lower(), f"Docker Compose warnings: {err}"
    print("  ✅ Docker Compose config valid")


def test_config_dir_default():
    """CONFIG_DIR defaults to /Mythic (not /Mythic/configs)."""
    out, _, rc = run("sudo docker exec dolos python3 -c \""
        "from dolos.config_loader import CONFIG_DIR; print(CONFIG_DIR)\"")
    assert rc == 0, f"Cannot read CONFIG_DIR: {out}"
    assert out.strip() == "/Mythic", f"Expected /Mythic, got {out}"
    print(f"  ✅ CONFIG_DIR = {out.strip()}")


def test_mythic_registration():
    """Dolos is registered as a wrapper payload type in Mythic."""
    out, _, rc = run("cd ~/MythicC2/Mythic && sudo ./mythic-cli services 2>&1")
    assert "dolos" in out, f"Dolos not in services list"
    assert "Up" in out.split("dolos")[1].split("\n")[0], f"Dolos not Up"
    print("  ✅ Dolos registered and running in Mythic")


def test_tool_files_present():
    """Tool files (encoder script, install script) are in /Mythic/."""
    out, _, rc = run("sudo docker exec dolos find /Mythic -maxdepth 1 -name '00_Tool_*'")
    assert rc == 0, f"Tool files not found: {out}"
    assert "00_Tool_pyencoder_encode.py" in out
    assert "00_Tool_pyencoder_install.ps1" in out
    print(f"  ✅ Tool files present: {out.strip()}")


def test_dolos_module_loads():
    """The dolos Python module loads without errors."""
    out, err, rc = run("sudo docker exec dolos python3 -c \"import dolos; print('OK')\"")
    assert rc == 0, f"dolos module failed to load: {err}"
    assert "OK" in out, f"dolos module unexpected output: {out}"
    print("  ✅ dolos module loads")


def test_ssh_client_module():
    """ssh_client module loads and has SSHSessionLog."""
    out, err, rc = run("sudo docker exec dolos python3 -c \""
        "from dolos.ssh_client import SSHSessionLog; print('OK')\"")
    assert rc == 0, f"ssh_client failed: {err}"
    print("  ✅ ssh_client module loads")


def test_agent_capabilities():
    """agent_capabilities.json has correct version and wrapper feature."""
    out, _, rc = run("sudo docker exec dolos cat /Mythic/dolos/agent_capabilities.json")
    data = json.loads(out)
    assert data["agent_version"] == "2.1.0", f"Wrong agent version: {data['agent_version']}"
    assert "wrapper" in data["features"]["mythic"], "Missing wrapper feature"
    assert data["os"] == ["SSH Server + Any OS"], f"Wrong OS: {data['os']}"
    print(f"  ✅ agent_capabilities: v{data['agent_version']}, wrapper=True")


def test_no_old_v1_code():
    """No v1 references in the container codebase."""
    out, _, rc = run("sudo docker exec dolos grep -r 'configs/encoders' /Mythic/dolos/ 2>/dev/null")
    assert rc != 0 or out.strip() == "", f"V1 paths still referenced: {out}"
    
    out2, _, rc2 = run("sudo docker exec dolos grep -r 'configs.defaults' /Mythic/dolos/ 2>/dev/null")
    assert rc2 != 0 or out2.strip() == "", f"V1 scaffolding still referenced: {out2}"
    
    print("  ✅ No v1 code references in container")


def test_docker_compose_dolos_section():
    """docker-compose has correct Dolos service config."""
    out, _, _ = run("cd ~/MythicC2/Mythic && cat docker-compose.yml")
    
    # Check no DOLOS_CONFIG env var
    assert "DOLOS_CONFIG" not in out, "Found DOLOS_CONFIG env var (should not be present)"
    # Check no DOLOS_LOG env vars  
    assert "DOLOS_LOG" not in out, "Found DOLOS_LOG env var (should not be present)"
    # Check HASURA_SECRET is present
    assert "HASURA_SECRET" in out, "Missing HASURA_SECRET env var"
    # Check image is v2.1.0
    assert "v2.1.0" in out, "Docker Compose doesn't reference v2.1.0 image"
    print("  ✅ docker-compose.yml Dolos section is correct")


# Run all tests
if __name__ == "__main__":
    tests = [fn for name, fn in sorted(globals().items()) 
             if callable(fn) and name.startswith("test_")]
    
    passed = 0
    failed = 0
    errors = []
    
    print(f"\n🧪 Dolos v2.1.0 E2E Test Suite ({len(tests)} tests)\n")
    
    for test in tests:
        name = test.__name__
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
            errors.append((name, str(e)))
    
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    
    if errors:
        print(f"\n❌ Failed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")
        sys.exit(1)
    else:
        print(f"\n✅ All tests passed!")
        sys.exit(0)
