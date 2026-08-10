"""Dolos v2 Config Loader - flat-file naming convention.

Loads encoder profiles from /Mythic/configs/ using the NN_Type_Detail.ext naming
convention. No directory traversal, no scaffolding, no SSH key files.

File naming: {NN}_{Type}_{Detail}.{ext}
  NN: two-digit sort order / group number
  Type: Encoder, Bypass, Tool
  Detail: human-readable label
  ext: .json for configs, .ps1/.sh/.py for scripts

SSH keys resolved via Mythic User Secrets (self.secrets in build()),
with flat-file fallback (any file in CONFIG_DIR matching the secret name).

Config hot-reload: mtime polling detects changes, triggers Mythic resync
so dropdowns update without container restart.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

CONFIG_DIR = os.environ.get("DOLOS_CONFIG") or "/Mythic/configs"

_FILE_PATTERN = re.compile(r"^(\d{2})_(Encoder|Bypass|Tool)_(.+)\.(json|ps1|sh|py)$")


@dataclass
class BypassProfile:
    filename: str
    label: str
    group: str
    enabled: bool
    config: dict


@dataclass
class EncoderProfile:
    filename: str
    label: str
    group: str
    command: str
    host: str
    port: int
    username: str
    password: str
    ssh_key_secret: str       # Mythic User Secret name
    ssh_key_enabled: bool
    ssh_key_content: str      # resolved at build time from self.secrets
    bypass_refs: list[str]    # filenames e.g. ["00_Bypass_AMSI.json"]
    bypass_profiles: list[BypassProfile]
    timeout: int
    success_string: str
    fail_string: str
    install_tools: bool
    enabled: bool
    valid: bool
    validation_errors: list[str]


# ── Module cache ──
_profiles: Optional[list[EncoderProfile]] = None
_config_mtimes: dict[str, float] = {}


def _reset_cache():
    global _profiles, _config_mtimes
    _profiles = None
    _config_mtimes = {}


def _scan_mtimes() -> dict[str, float]:
    mtimes = {}
    config_dir = os.path.abspath(CONFIG_DIR)
    if not os.path.isdir(config_dir):
        return mtimes
    for fname in os.listdir(config_dir):
        fpath = os.path.join(config_dir, fname)
        if os.path.isfile(fpath):
            try:
                mtimes[fpath] = os.path.getmtime(fpath)
            except OSError:
                pass
    return mtimes


def _check_mtimes() -> bool:
    current = _scan_mtimes()
    if set(current.keys()) != set(_config_mtimes.keys()):
        return True
    for path, mtime in current.items():
        if _config_mtimes.get(path) != mtime:
            return True
    return False


def _parse_filename(fname: str) -> Optional[tuple[str, str, str, str]]:
    m = _FILE_PATTERN.match(fname)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3), m.group(4)


def load_profiles() -> list[EncoderProfile]:
    global _profiles, _config_mtimes

    config_dir = os.path.abspath(CONFIG_DIR)
    if not os.path.isdir(config_dir):
        logger.critical("[DOLOS-CONFIG] Config directory %s does not exist", config_dir)
        _profiles = []
        return _profiles

    encoder_files = []
    bypass_files = []

    for fname in sorted(os.listdir(config_dir)):
        fpath = os.path.join(config_dir, fname)
        if not os.path.isfile(fpath):
            continue
        parsed = _parse_filename(fname)
        if parsed is None:
            continue
        group, ftype, detail, ext = parsed
        if ftype == "Encoder" and ext == "json":
            encoder_files.append((fname, fpath, group, detail))
        elif ftype == "Bypass" and ext == "json":
            bypass_files.append((fname, fpath, group, detail))

    if not encoder_files:
        logger.critical(
            "[DOLOS-CONFIG] No encoder profiles in %s. Create NN_Encoder_Label.json files.",
            config_dir,
        )
        _profiles = []
        _config_mtimes = _scan_mtimes()
        return _profiles

    bypass_by_group: dict[str, list[BypassProfile]] = {}
    for fname, fpath, group, detail in bypass_files:
        bp = _parse_bypass(fname, fpath, group, detail)
        if bp:
            bypass_by_group.setdefault(group, []).append(bp)

    profiles = []
    seen_labels = set()
    for fname, fpath, group, detail in encoder_files:
        profile = _parse_encoder(fname, fpath, group, detail, bypass_by_group.get(group, []))
        if profile and profile.label not in seen_labels:
            profiles.append(profile)
            seen_labels.add(profile.label)

    profiles.sort(key=lambda p: p.group)

    valid_count = sum(1 for p in profiles if p.valid)
    enabled_count = sum(1 for p in profiles if p.enabled and p.valid)
    logger.critical(
        "[DOLOS-CONFIG] Loaded %d encoder(s): %d valid (%d enabled)",
        len(profiles), valid_count, enabled_count,
    )
    for p in profiles:
        bypass_info = f", {len(p.bypass_profiles)} bypass" if p.bypass_profiles else ""
        status = "VALID" if p.valid else f"INVALID: {'; '.join(p.validation_errors)}"
        state = "ENABLED" if p.enabled else "DISABLED"
        logger.critical("[DOLOS-CONFIG]   %s [%s %s%s]", p.label, state, status, bypass_info)

    _profiles = profiles
    _config_mtimes = _scan_mtimes()
    return _profiles


def _parse_bypass(fname: str, fpath: str, group: str, detail: str) -> Optional[BypassProfile]:
    try:
        with open(fpath, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.critical("[DOLOS-CONFIG] Failed to parse %s: %s", fpath, e)
        return None
    return BypassProfile(
        filename=fname,
        label=data.get("label", detail.replace("_", " ").title()),
        group=group,
        enabled=data.get("enabled", True),
        config=data.get("config", {}),
    )


def _parse_encoder(
    fname: str, fpath: str, group: str, detail: str,
    group_bypasses: list[BypassProfile],
) -> Optional[EncoderProfile]:
    try:
        with open(fpath, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.critical("[DOLOS-CONFIG] Failed to parse %s: %s", fpath, e)
        return None

    version = data.get("version", 1)
    if version != 2:
        logger.critical(
            "[DOLOS-CONFIG] %s has version=%s, expected version=2. Update to v2 flat-file format.",
            fpath, version,
        )

    label = data.get("label") or detail.replace("_", " ")
    command = data.get("command", "")
    enabled = data.get("enabled", True)

    host = data.get("ssh_host", "")
    port = int(data.get("ssh_port", 22))
    username = data.get("ssh_username", "")
    password = data.get("ssh_password", "")

    # SSH key via Mythic User Secrets — no file paths
    ssh_key_secret = data.get("ssh_key_secret", "")
    ssh_key_enabled = data.get("ssh_key_enabled", False)

    timeout = int(data.get("timeout", 300))
    success_string = str(data.get("success_string", "ENCODING_SUCCESS"))
    fail_string = str(data.get("fail_string", "ENCODING_FAILED"))
    install_tools = bool(data.get("install_tools", False))

    # Bypass profiles by filename reference
    bypass_refs = data.get("bypass_refs", [])
    bypass_profiles = []
    config_dir = os.path.abspath(CONFIG_DIR)
    for ref in bypass_refs:
        ref_path = os.path.join(config_dir, ref)
        if os.path.isfile(ref_path):
            parsed = _parse_filename(ref)
            if parsed and parsed[1] == "Bypass":
                bp = _parse_bypass(ref, ref_path, parsed[0], parsed[2])
                if bp and bp.enabled:
                    bypass_profiles.append(bp)
        else:
            logger.warning("[DOLOS-CONFIG] Bypass ref '%s' not found", ref)

    # Validation
    validation_errors = []
    if not host:
        validation_errors.append("ssh_host is required")
    if not command:
        validation_errors.append("command is required")
    elif "{input}" not in command or "{output}" not in command:
        validation_errors.append("command must contain {input} and {output} placeholders")
    if not username:
        validation_errors.append("ssh_username is required")
    if not password and not ssh_key_enabled:
        validation_errors.append("no auth: set ssh_password or enable ssh_key_enabled")
    if ssh_key_enabled and not ssh_key_secret:
        validation_errors.append("ssh_key_enabled=true but ssh_key_secret is empty — set a Mythic User Secret name")

    valid = len(validation_errors) == 0
    if not valid:
        for err in validation_errors:
            logger.critical("[DOLOS-CONFIG] Profile '%s': %s", label, err)

    return EncoderProfile(
        filename=fname,
        label=label,
        group=group,
        command=command,
        host=host,
        port=port,
        username=username,
        password=password,
        ssh_key_secret=ssh_key_secret,
        ssh_key_enabled=ssh_key_enabled,
        ssh_key_content="",  # resolved at build time
        bypass_refs=bypass_refs,
        bypass_profiles=bypass_profiles,
        timeout=timeout,
        success_string=success_string,
        fail_string=fail_string,
        install_tools=install_tools,
        enabled=enabled,
        valid=valid,
        validation_errors=validation_errors,
    )


def resolve_ssh_key(profile: EncoderProfile, secrets: dict) -> str:
    """Resolve SSH key from Mythic User Secrets with flat-file fallback.

    1. Mythic User Secrets (self.secrets dict) — per-operator, private
    2. Flat file in CONFIG_DIR matching ssh_key_secret name — paperclip-editable
    """
    if not profile.ssh_key_enabled or not profile.ssh_key_secret:
        return ""

    # Primary: Mythic User Secrets
    key_content = secrets.get(profile.ssh_key_secret, "")
    if key_content:
        logger.critical("[DOLOS-CONFIG] SSH key '%s' resolved from User Secrets", profile.ssh_key_secret)
        return key_content

    # Fallback: flat file in CONFIG_DIR
    key_path = os.path.join(os.path.abspath(CONFIG_DIR), profile.ssh_key_secret)
    if os.path.isfile(key_path):
        try:
            key_content = open(key_path, "r").read().strip()
            if key_content:
                logger.critical("[DOLOS-CONFIG] SSH key '%s' resolved from flat file", profile.ssh_key_secret)
                return key_content
        except IOError as e:
            logger.warning("[DOLOS-CONFIG] Failed to read key file %s: %s", key_path, e)

    logger.warning(
        "[DOLOS-CONFIG] SSH key '%s' not found in User Secrets or flat file. "
        "Add it in Mythic UI → User Settings → Secrets.",
        profile.ssh_key_secret,
    )
    return ""


def get_tool_files(label: str) -> list[str]:
    """Return tool file paths matching the encoder's group number."""
    profile = get_encoder_profile(label)
    if profile is None or not profile.install_tools:
        return []
    config_dir = os.path.abspath(CONFIG_DIR)
    tools = []
    for fname in sorted(os.listdir(config_dir)):
        parsed = _parse_filename(fname)
        if parsed and parsed[1] == "Tool" and parsed[0] == profile.group:
            fpath = os.path.join(config_dir, fname)
            if os.path.isfile(fpath):
                tools.append(fpath)
    return tools


def get_install_script(label: str, remote_os: str) -> str | None:
    """Return install script path for encoder's group and OS."""
    profile = get_encoder_profile(label)
    if profile is None or not profile.install_tools:
        return None
    config_dir = os.path.abspath(CONFIG_DIR)
    suffix = f"install_{remote_os}.ps1" if remote_os == "windows" else f"install_{remote_os}.sh"
    for fname in sorted(os.listdir(config_dir)):
        parsed = _parse_filename(fname)
        if parsed and parsed[1] == "Tool" and parsed[0] == profile.group:
            if fname.endswith(suffix):
                fpath = os.path.join(config_dir, fname)
                if os.path.isfile(fpath):
                    return fpath
    return None


# ── Public API ──

def _ensure_loaded() -> list[EncoderProfile]:
    global _profiles
    if _profiles is None or _check_mtimes():
        _profiles = load_profiles()
    return _profiles


def get_encoder_choices() -> list[str]:
    profiles = _ensure_loaded()
    enabled = [p.label for p in profiles if p.enabled]
    return enabled if enabled else ["(no profiles configured)"]


def get_encoder_profile(label: str) -> Optional[EncoderProfile]:
    profiles = _ensure_loaded()
    for p in profiles:
        if p.label == label:
            return p
    return None


def get_encoders_with_bypass() -> list[str]:
    return [p.label for p in _ensure_loaded() if p.enabled and p.bypass_profiles]


def get_all_bypass_choices() -> list[str]:
    seen = set()
    result = []
    for p in _ensure_loaded():
        if not p.enabled:
            continue
        for bp in p.bypass_profiles:
            if bp.label not in seen:
                seen.add(bp.label)
                result.append(bp.label)
    return result + ["(None)"]


def get_bypass_filename_for_display(label: str, display_name: str) -> Optional[str]:
    profiles = _ensure_loaded()
    for p in profiles:
        if p.label == label:
            for bp in p.bypass_profiles:
                if bp.label == display_name:
                    return bp.filename
    return None