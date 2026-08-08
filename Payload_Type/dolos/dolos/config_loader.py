"""Dolos Config Loader - loads encoder profiles from filesystem.

Walks DOLOS_CONFIG/encoders/, parses encoder_profile.json files,
resolves relative paths (SSH keys, bypass profiles), validates,
and provides lookup functions for the build pipeline.

DOLOS_CONFIG defaults to /Mythic/configs/ (inside Docker) and is
overridden for local development via environment variable.

Auto-scaffolds a sample config on first run if the directory is
missing or empty. Never overwrites existing operator config.
"""

import json
import logging
import os
import stat
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuration directory ──
# Docker-compose sets unset env vars to "" (not undefined), so use `or`
# instead of a default value - per project rule #9 in CLAUDE.md.
CONFIG_DIR = os.environ.get("DOLOS_CONFIG") or "/Mythic/configs"


@dataclass
class EncoderProfile:
    """A single encoder configuration loaded from encoder_profile.json."""

    label: str
    index: int
    command: str
    host: str
    port: int
    username: str
    password: str
    key_enabled: bool
    key_path: str                    # resolved absolute path to private key file
    key_content: str                 # loaded private key PEM content (empty string if not loaded)
    enabled: bool                    # if False, this profile is hidden from the UI entirely
    bypass_profiles_path: str        # resolved absolute path to bypass profiles dir ("" if none)
    bypass_profiles: list[str]       # display names e.g. "Balliskit / Cortex Bypass"
    bypass_stems: list[str]          # stem names e.g. "cortex_bypass_profile" for template resolution
    profile_dir: str                 # directory containing this encoder_profile.json
    timeout: int                     # command timeout in seconds (per-profile)
    success_string: str               # string in stdout confirming success
    fail_string: str                  # string in stdout/stderr indicating failure
    valid: bool
    validation_errors: list[str]


# ── Module-level cache ──
_profiles: Optional[list[EncoderProfile]] = None
_profile_mtimes: dict[str, float] = {}  # {path: mtime} for auto-reload


def _reset_cache():
    """Reset the profile cache. Useful for testing."""
    global _profiles, _profile_mtimes
    _profiles = None
    _profile_mtimes = {}


def _check_mtimes() -> bool:
    """Check if any config files have changed since last load.

    Returns True if reload is needed (new files, removed files, or modified files).
    This enables live config editing: operators can edit files in the
    bind-mounted dolos_profiles/ directory and changes take effect
    without restarting the container.

    Checks encoder_profile.json files AND all files under the config
    directory tree (bypass profiles, SSH keys, etc.) so that adding
    or removing a bypass_profiles directory triggers a reload.
    """
    config_dir_abs = os.path.abspath(CONFIG_DIR)
    if not os.path.isdir(config_dir_abs):
        return True

    encoders_dir = os.path.join(CONFIG_DIR, "encoders")
    current_files = _find_profile_files(encoders_dir)
    current_mtimes: dict[str, float] = {}

    for f in current_files:
        try:
            current_mtimes[f] = os.path.getmtime(f)
        except OSError:
            # File disappeared between listing and stat - trigger reload
            return True

    # Also track all files under the config directory (bypass profiles, etc.)
    for root, _dirs, files in os.walk(config_dir_abs):
        for fname in files:
            fpath = os.path.join(root, fname)
            # Skip the profile JSONs we already tracked above
            if fname == "encoder_profile.json":
                continue
            try:
                current_mtimes[fpath] = os.path.getmtime(fpath)
            except OSError:
                return True

    # New files or removed files
    if set(current_mtimes.keys()) != set(_profile_mtimes.keys()):
        return True

    # Modified files
    for path, mtime in current_mtimes.items():
        if _profile_mtimes.get(path) != mtime:
            return True

    return False


def _ensure_loaded() -> list[EncoderProfile]:
    """Load profiles if not already cached, or reload if files changed."""
    global _profiles
    if _profiles is None or _check_mtimes():
        _profiles = load_profiles()
    return _profiles


def _find_profile_files(encoders_dir: str) -> list[str]:
    """Find all encoder_profile.json files under the encoders directory."""
    results = []
    if not os.path.isdir(encoders_dir):
        return results
    for root, _dirs, files in os.walk(encoders_dir):
        for f in files:
            if f == "encoder_profile.json":
                results.append(os.path.join(root, f))
    return results


def _has_profiles(encoders_dir: str) -> bool:
    """Check if there are any encoder_profile.json files."""
    return len(_find_profile_files(encoders_dir)) > 0


def load_profiles() -> list[EncoderProfile]:
    """Walk DOLOS_CONFIG/encoders/ and load all encoder_profile.json files.

    Returns profiles sorted by index. Caches the result for subsequent calls.
    """
    global _profiles

    encoders_dir = os.path.join(CONFIG_DIR, "encoders")
    profile_files = _find_profile_files(encoders_dir)

    if not profile_files:
        logger.critical(
            "[DOLOS-CONFIG] No encoder_profile.json files found in %s "
            "- builds will fail until profiles are configured",
            encoders_dir,
        )
        _profiles = []
        return _profiles

    profiles = []
    seen_labels = set()

    for profile_path in profile_files:
        profile = _parse_profile(profile_path, seen_labels)
        if profile is not None:
            profiles.append(profile)
            seen_labels.add(profile.label)

    # Sort by index
    profiles.sort(key=lambda p: p.index)

    # Log summary
    valid_count = sum(1 for p in profiles if p.valid)
    enabled_count = sum(1 for p in profiles if p.enabled and p.valid)
    disabled_count = sum(1 for p in profiles if not p.enabled)
    invalid_count = len(profiles) - valid_count
    logger.critical(
        "[DOLOS-CONFIG] Loaded %d encoder profile(s): %d valid (%d enabled, %d disabled), %d with errors",
        len(profiles), valid_count, enabled_count, disabled_count, invalid_count,
    )
    for p in profiles:
        if not p.enabled:
            logger.info("[DOLOS-CONFIG]   %s [DISABLED]", p.label)
        elif p.valid:
            bypass_info = (
                f", {len(p.bypass_profiles)} bypass profile(s)"
                if p.bypass_profiles
                else ""
            )
            logger.critical("[DOLOS-CONFIG]   %s [VALID%s]", p.label, bypass_info)
        else:
            errors = "; ".join(p.validation_errors)
            logger.critical("[DOLOS-CONFIG]   %s [INVALID: %s]", p.label, errors)

    _profiles = profiles

    # Store mtimes for auto-reload detection
    global _profile_mtimes
    _profile_mtimes = {}
    for pf in profile_files:
        try:
            _profile_mtimes[pf] = os.path.getmtime(pf)
        except OSError:
            pass

    return _profiles


def _parse_profile(profile_path: str, seen_labels: set) -> Optional[EncoderProfile]:
    """Parse a single encoder_profile.json file into an EncoderProfile."""
    try:
        with open(profile_path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.critical("[DOLOS-CONFIG] Failed to parse %s: %s", profile_path, e)
        return None

    profile_dir = os.path.dirname(os.path.abspath(profile_path))

    # Normalize "lable" typo to "label"
    label = data.get("label") or data.get("lable") or ""
    if not label:
        logger.critical("[DOLOS-CONFIG] Profile %s has no label, skipping", profile_path)
        return None

    # Check for duplicate labels
    if label in seen_labels:
        logger.critical(
            "[DOLOS-CONFIG] Duplicate label '%s' in %s, skipping", label, profile_path,
        )
        return None

    index = data.get("index", 0)
    command = data.get("command", "")
    enabled = data.get("enabled", True)  # default to True if missing

    # SSH server config
    ssh = data.get("ssh_server", {})
    host = ssh.get("host", "")
    port = int(ssh.get("port", 22))
    username = ssh.get("username", "")
    password = ssh.get("password", "")

    # Key configuration
    keys = ssh.get("keys", {})
    key_enabled = keys.get("enabled", False)
    key_path_relative = keys.get("path", "")

    key_path = ""
    key_content = ""
    if key_enabled and key_path_relative:
        # Resolve relative to the profile JSON's directory
        key_path = os.path.normpath(os.path.join(profile_dir, key_path_relative))
        try:
            with open(key_path, "r") as f:
                key_content = f.read().strip()
            # Warn if world-readable (Unix only)
            try:
                mode = os.stat(key_path).st_mode
                if mode & stat.S_IROTH:
                    logger.critical(
                        "[DOLOS-CONFIG] WARNING: Key file %s is world-readable (mode %s)",
                        key_path, oct(mode & 0o777),
                    )
            except (OSError, AttributeError):
                pass
        except IOError as e:
            logger.critical("[DOLOS-CONFIG] Failed to read key file %s: %s", key_path, e)
            key_content = ""

    # Timeout (per-encoder, replaces the old env-var DOLOS_TIMEOUT)
    timeout = int(data.get("timeout", 300))

    # Success/fail strings (per-encoder, fixed constants that match the encoder's output)
    success_string = str(data.get("success_string", "ENCODING_SUCCESS"))
    fail_string = str(data.get("fail_string", "ENCODING_FAILED"))

    # Bypass profiles
    bypass_profiles_relative = data.get("bypass_profiles", "")
    bypass_profiles_path = ""
    bypass_profiles = []
    bypass_stems = []

    if bypass_profiles_relative:
        bypass_profiles_path = os.path.normpath(
            os.path.join(profile_dir, bypass_profiles_relative)
        )
        if os.path.isdir(bypass_profiles_path):
            # Derive the encoder project name from directory structure.
            # e.g. configs/encoders/balliskit/macropack/ -> root = "balliskit"
            encoders_dir = os.path.join(os.path.abspath(CONFIG_DIR), "encoders")
            rel_path = os.path.relpath(profile_dir, encoders_dir)
            # First component is the root encoder name (under encoders/)
            encoder_root = rel_path.split(os.sep)[0] if os.sep in rel_path else rel_path
            # Capitalize first letter for display
            encoder_display = (
                encoder_root[0].upper() + encoder_root[1:] if encoder_root else "Unknown"
            )

            for bp_file in sorted(os.listdir(bypass_profiles_path)):
                if bp_file.endswith(".json"):
                    stem = os.path.splitext(bp_file)[0]
                    bp_full_path = os.path.join(bypass_profiles_path, bp_file)

                    # Check bypass profile enabled flag (default True)
                    try:
                        with open(bp_full_path, "r") as f:
                            bp_data = json.load(f)
                        bp_enabled = bp_data.get("enabled", True)
                        if not bp_enabled:
                            logger.info(
                                "[DOLOS-CONFIG] Skipping disabled bypass profile: %s", bp_file
                            )
                            continue
                    except (json.JSONDecodeError, IOError) as e:
                        logger.warning(
                            "[DOLOS-CONFIG] Could not read bypass profile %s: %s, including anyway",
                            bp_full_path, e,
                        )

                    # Build display name: "Balliskit / Cortex Bypass"
                    # Strip common suffixes from the stem for readability
                    display_name = stem
                    for suffix in (
                        "_bypass_profile", "_bypass", "_profile",
                        "bypass_profile", "bypass", "profile",
                    ):
                        if display_name.lower().endswith(suffix):
                            display_name = display_name[: -len(suffix)]
                            break
                    # Remove trailing underscores after suffix removal
                    display_name = display_name.rstrip("_")
                    display_name = display_name.replace("_", " ").title()
                    full_display = f"{encoder_display} / {display_name} Bypass"
                    bypass_profiles.append(full_display)
                    bypass_stems.append(stem)

    # ── Validate ──
    validation_errors = []
    if not host:
        validation_errors.append("ssh_server.host is required")
    if not username:
        validation_errors.append("ssh_server.username is required")
    if not command:
        validation_errors.append("command is required")
    elif "{input}" not in command or "{output}" not in command:
        validation_errors.append(
            "command must contain {input} and {output} placeholders"
        )
    if not password and not key_enabled:
        validation_errors.append(
            "no auth method: set ssh_server.password or enable ssh_server.keys"
        )
    if key_enabled and not key_content:
        if key_path_relative:
            validation_errors.append(f"key file not readable or empty: {key_path}")
        else:
            validation_errors.append(
                "ssh_server.keys.enabled is true but keys.path is empty"
            )

    valid = len(validation_errors) == 0

    if not valid:
        for err in validation_errors:
            logger.critical("[DOLOS-CONFIG] Profile '%s': %s", label, err)

    return EncoderProfile(
        label=label,
        index=index,
        command=command,
        host=host,
        port=port,
        username=username,
        password=password,
        key_enabled=key_enabled,
        key_path=key_path,
        key_content=key_content,
        enabled=enabled,
        bypass_profiles_path=bypass_profiles_path,
        bypass_profiles=bypass_profiles,
        bypass_stems=bypass_stems,
        profile_dir=profile_dir,
        timeout=timeout,
        success_string=success_string,
        fail_string=fail_string,
        valid=valid,
        validation_errors=validation_errors,
    )


def _scaffold_sample_config():
    """Auto-create a sample config directory with boilerplate profile.

    Idempotent - never overwrites existing files.
    """
    config_dir = os.path.abspath(CONFIG_DIR)
    encoders_dir = os.path.join(config_dir, "encoders", "pyencoder")
    ssh_keys_dir = os.path.join(config_dir, "ssh_keys", "sample_server")

    os.makedirs(encoders_dir, exist_ok=True)
    os.makedirs(ssh_keys_dir, exist_ok=True)

    sample_profile = {
        "index": 99,
        "label": "SAMPLE_PyEncoder",
        "enabled": False,
        "command": "py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}",
        "ssh_server": {
            "host": "192.168.1.100",
            "port": 22,
            "username": "operator",
            "password": "",
            "keys": {"enabled": False, "path": ""},
        },
        "timeout": 300,
        "success_string": "ENCODING_SUCCESS",
        "fail_string": "ENCODING_FAILED",
        "bypass_profiles": "",
    }

    profile_path = os.path.join(encoders_dir, "encoder_profile.json")
    if not os.path.exists(profile_path):
        try:
            with open(profile_path, "w") as f:
                json.dump(sample_profile, f, indent=4)
            logger.critical("[DOLOS-CONFIG] Created sample profile at %s", profile_path)
        except IOError as e:
            logger.critical("[DOLOS-CONFIG] Failed to create sample profile: %s", e)
    else:
        logger.critical(
            "[DOLOS-CONFIG] Profile already exists at %s, not overwriting", profile_path
        )

    logger.critical("[DOLOS-CONFIG] Auto-generated sample config at %s", config_dir)
    logger.critical(
        "[DOLOS-CONFIG] Edit encoder_profile.json with your SSH credentials before building"
    )


def scaffold_if_needed():
    """Auto-scaffold sample config if the directory is missing or empty.

    Called from main.py before importing dolos to ensure config directory
    exists before config_loader reads profiles.
    """
    config_dir = os.path.abspath(CONFIG_DIR)
    encoders_dir = os.path.join(config_dir, "encoders")

    if not os.path.isdir(config_dir) or not _has_profiles(encoders_dir):
        _scaffold_sample_config()


# ── Public API ──────────────────────────────────────────────────────────


def get_encoder_choices() -> list[str]:
    """Return labels of enabled encoder profiles for Mythic dropdown.

    Disabled profiles (enabled=false) are excluded.
    Returns ["(no profiles configured)"] if no enabled profiles found.
    """
    profiles = _ensure_loaded()
    enabled = [p.label for p in profiles if p.enabled]
    if not enabled:
        return ["(no profiles configured)"]
    return enabled


def get_encoder_profile(label: str) -> Optional[EncoderProfile]:
    """Return the EncoderProfile for a given label, or None if not found.

    Returns disabled profiles too - callers should check .enabled.
    """
    profiles = _ensure_loaded()
    for p in profiles:
        if p.label == label:
            return p
    return None


def get_encoders_with_bypass() -> list[str]:
    """Return labels of enabled encoders that have at least one enabled bypass profile.

    Used for hide_conditions on the Bypass Profile dropdown.
    """
    profiles = _ensure_loaded()
    return [p.label for p in profiles if p.enabled and p.bypass_profiles]


def get_all_bypass_choices() -> list[str]:
    """Return all enabled bypass profile display names plus "(None)" for the dropdown.

    Only includes bypass profiles from enabled encoders.
    Returns ["(None)"] if no enabled bypass profiles exist.
    """
    profiles = _ensure_loaded()
    seen = set()
    result = []
    for p in profiles:
        if not p.enabled:
            continue
        for bp in p.bypass_profiles:
            if bp not in seen:
                seen.add(bp)
                result.append(bp)
    return result + ["(None)"]


def get_bypass_stem_for_display(label: str, display_name: str) -> Optional[str]:
    """Look up the bypass profile stem name for a given encoder and display name.

    E.g. get_bypass_stem_for_display("MacroPack_v1.9", "Balliskit / Cortex Bypass")
    returns "cortex_bypass_profile"
    """
    profiles = _ensure_loaded()
    for p in profiles:
        if p.label == label:
            for i, bp in enumerate(p.bypass_profiles):
                if bp == display_name:
                    return p.bypass_stems[i]
    return None


def get_bypass_stems_for(label: str) -> list[str]:
    """Return bypass profile stems for a specific encoder label."""
    profiles = _ensure_loaded()
    for p in profiles:
        if p.label == label:
            return p.bypass_stems
    return []