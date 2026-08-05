"""SSH/SFTP client, file transfer helpers, and session logging for Dolos.

Handles:
- SSH connection using env-var-only config (no build-param SSH fields)
- Key auth (ed25519/RSA/ECDSA) via DOLOS_SSH_PRIVATE_KEY, or password auth,
  or both — at least one required
- OS auto-detection (Windows vs Linux) for temp directory paths
- Random workdir generation per build
- SFTP directory creation, upload, download, and cleanup
- Remote command execution with timeout and log capture
- Success/failure detection (exit code, file existence, string indicators)
- File magic byte validation (PE, DLL, ZIP, JSON, etc.)
- Structured session logging (SSHSessionLog) with JSON artifact output
- Structured result dict for the build pipeline
"""

import io
import json
import logging
import os
import random
import string
import struct
import tempfile
import shutil
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

import paramiko

logger = logging.getLogger(__name__)

# ── Container log rotation ──
# mythic_container's root logger suppresses DEBUG/INFO. We add a
# RotatingFileHandler to the "dolos" logger so that DEBUG-level detail
# is captured to disk (with size limits and rotation) while only
# CRITICAL messages appear in docker logs.

DOLOS_LOG_DIR = os.environ.get("DOLOS_LOG_DIR", "/tmp/dolos")
DOLOS_LOG_MAX_MB = int(os.environ.get("DOLOS_LOG_MAX_MB", "50"))
DOLOS_LOG_MAX_BACKUPS = int(os.environ.get("DOLOS_LOG_MAX_BACKUPS", "3"))


def _setup_file_logging():
    """Add a RotatingFileHandler to the 'dolos' logger.

    Called once at module import. Creates /tmp/dolos/ (or DOLOS_LOG_DIR)
    if it doesn't exist, then attaches a rotating file handler that
    captures DEBUG and above. The handler rotates at DOLOS_LOG_MAX_MB MB
    and keeps DOLOS_LOG_MAX_BACKUPS backup files.

    This is safe to call even if the directory isn't writable — it just
    won't add the handler and logs a warning.
    """
    dolos_logger = logging.getLogger("dolos")

    # Don't add a duplicate handler if this module is reloaded
    if any(isinstance(h, RotatingFileHandler) for h in dolos_logger.handlers):
        return

    try:
        os.makedirs(DOLOS_LOG_DIR, exist_ok=True)
    except OSError:
        # Can't create log dir (e.g. read-only filesystem) — skip file logging
        logger.warning("Cannot create log directory %s, file logging disabled", DOLOS_LOG_DIR)
        return

    handler = RotatingFileHandler(
        filename=os.path.join(DOLOS_LOG_DIR, "dolos.log"),
        maxBytes=DOLOS_LOG_MAX_MB * 1024 * 1024,
        backupCount=DOLOS_LOG_MAX_BACKUPS,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    dolos_logger.addHandler(handler)
    logger.info("File logging enabled: %s (max %dMB, %d backups)",
                os.path.join(DOLOS_LOG_DIR, "dolos.log"),
                DOLOS_LOG_MAX_MB, DOLOS_LOG_MAX_BACKUPS)


_setup_file_logging()

# Environment variable names (SSH config is env-only now, no build-param overrides)
ENV_HOST = "DOLOS_SSH_HOST"
ENV_PORT = "DOLOS_SSH_PORT"
ENV_USER = "DOLOS_SSH_USERNAME"
ENV_PASS = "DOLOS_SSH_PASSWORD"
ENV_PRIV_KEY = "DOLOS_SSH_PRIVATE_KEY"
ENV_PUB_KEY = "DOLOS_SSH_PUBLIC_KEY"
ENV_COMMAND = "DOLOS_REMOTE_COMMAND"
ENV_TIMEOUT = "DOLOS_TIMEOUT"

# Literal defaults
DEFAULT_PORT = 22
DEFAULT_TIMEOUT = 300


# ---------------------------------------------------------------------------
# SSH Session Log — captures every SSH/SFTP event with timestamps
# ---------------------------------------------------------------------------

class SSHSessionLog:
    """Structured, timestamped log of every SSH/SFTP event during a build.

    Captures connection events, SFTP operations (mkdir, put, stat, get, remove),
    remote command execution (resolved command, stdout lines, stderr lines, exit code),
    internal decisions (workdir name, placeholder resolution, file magic),
    success/failure detection, and cleanup operations.

    Produces two outputs:
    1. JSON artifact — full, structured, machine-readable. Stored via
       SendMythicRPCFileCreate as <payload_name>.session.json. Searchable via
       GraphQL. Forensically linked to the payload UUID.
    2. Human-readable summary — compact text with key events and final status.
       Stored in resp.build_message.

    Verbosity is encoder-dependent: whatever the encoder outputs is captured.
    The operator can't control verbosity from Dolos, but everything is preserved.
    """

    def __init__(self):
        self.events: list[dict] = []
        self._start_time = datetime.now(timezone.utc)

    def _ts(self) -> str:
        """ISO 8601 timestamp with milliseconds."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _elapsed(self) -> str:
        """Elapsed time since session start, formatted as seconds with ms."""
        elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        return f"{elapsed:.3f}s"

    def _add(self, phase: str, level: str, message: str, **extra):
        """Add a timestamped event to the log."""
        event = {
            "timestamp": self._ts(),
            "elapsed": self._elapsed(),
            "phase": phase,
            "level": level,
            "message": message,
            **extra,
        }
        self.events.append(event)
        # Map session log level to Python logging level so file logs get
        # proper severity. Only errors go to docker logs (CRITICAL).
        _level_map = {"INFO": logger.info, "SFTP": logger.info, "CMD": logger.info,
                      "STDOUT": logger.debug, "STDERR": logger.warning,
                      "WARN": logger.warning, "ERROR": logger.error}
        _log_fn = _level_map.get(level, logger.info)
        _log_fn(f"[DOLOS-LOG] [{phase}] [{level}] {message}")

    # ── Connection events ──

    def connecting(self, host: str, port: int, username: str):
        self._add("connecting", "INFO", f"Connecting to {username}@{host}:{port}")

    def connected(self, host: str, port: int, remote_os: str):
        self._add("connecting", "INFO", f"Connected to {host}:{port} ({remote_os})",
                  remote_os=remote_os)

    def auth_success(self, username: str, auth_method: str = "password"):
        self._add("connecting", "INFO", f"{auth_method} auth succeeded for {username}")

    def sftp_test(self, success: bool, msg: str):
        level = "INFO" if success else "WARN"
        self._add("connecting", level, f"SFTP write test: {msg}", sftp_ok=success)

    def connection_failed(self, error: str):
        self._add("connecting", "ERROR", f"Connection failed: {error}")

    # ── Preparing events ──

    def creating_workdir(self, workdir: str, remote_os: str):
        self._add("preparing", "INFO", f"Creating workdir: {workdir}",
                  workdir=workdir, remote_os=remote_os)

    def workdir_created(self, workdir: str):
        self._add("preparing", "INFO", f"Workdir created: {workdir}")

    # ── Uploading events ──

    def uploading_file(self, local_name: str, remote_path: str, size: int):
        self._add("uploading", "SFTP", f"Uploading {local_name} ({size:,} bytes) → {remote_path}",
                  local_name=local_name, remote_path=remote_path, size_bytes=size)

    def upload_complete(self, local_name: str, size: int, elapsed: float):
        self._add("uploading", "SFTP",
                  f"Uploaded {local_name} ({size:,} bytes) in {elapsed:.1f}s",
                  local_name=local_name, size_bytes=size, elapsed_s=round(elapsed, 2))

    def upload_failed(self, local_name: str, error: str):
        self._add("uploading", "ERROR", f"Upload failed for {local_name}: {error}")

    # ── Processing events ──

    def running_command(self, command: str):
        self._add("processing", "CMD", f"Running encoder command",
                  command=command)

    def command_started(self, command: str):
        self._add("processing", "CMD", f"Command started", command=command)

    def command_stdout(self, line: str):
        self._add("processing", "STDOUT", line)

    def command_stderr(self, line: str):
        self._add("processing", "STDERR", line)

    def command_exit(self, exit_code: int, elapsed: float):
        self._add("processing", "CMD",
                  f"Command exited with code {exit_code} ({elapsed:.1f}s)",
                  exit_code=exit_code, elapsed_s=round(elapsed, 2))

    def command_timeout(self, timeout: int):
        self._add("processing", "ERROR", f"Command timed out after {timeout}s",
                  timeout=timeout)

    def command_failed(self, error: str):
        self._add("processing", "ERROR", f"Command execution failed: {error}")

    # ── Retrieving events ──

    def downloading_result(self, remote_path: str):
        self._add("retrieving", "SFTP", f"Downloading result: {remote_path}",
                  remote_path=remote_path)

    def result_downloaded(self, remote_path: str, size: int):
        self._add("retrieving", "SFTP",
                  f"Downloaded result ({size:,} bytes) from {remote_path}",
                  remote_path=remote_path, size_bytes=size)

    def result_missing(self, remote_path: str):
        self._add("retrieving", "WARN", f"Result file not found: {remote_path}",
                  remote_path=remote_path)

    # ── Cleaning events ──

    def cleanup_file(self, remote_path: str, success: bool, error: str = ""):
        level = "SFTP" if success else "WARN"
        msg = f"Removed {remote_path}" if success else f"Failed to remove {remote_path}: {error}"
        self._add("cleaning", level, msg, remote_path=remote_path, cleanup_ok=success)

    def cleanup_workdir(self, workdir: str, success: bool, error: str = ""):
        level = "SFTP" if success else "WARN"
        msg = f"Removed workdir {workdir}" if success else f"Failed to remove workdir {workdir}: {error}"
        self._add("cleaning", level, msg, workdir=workdir, cleanup_ok=success)

    # ── Validating events ──

    def validating(self, status: str, detail: str, exit_code: int,
                   input_size: int, output_size: int, magic_type: str,
                   success_string: str = "", failure_string: str = ""):
        self._add("validating", "INFO",
                  f"Validation: {status} — {detail}",
                  status=status, detail=detail, exit_code=exit_code,
                  input_size=input_size, output_size=output_size,
                  magic_type=magic_type,
                  success_string_found=bool(success_string),
                  failure_string_found=bool(failure_string))

    def magic_detected(self, magic_type: str, size: int):
        self._add("validating", "INFO", f"Detected file type: {magic_type} ({size:,} bytes)",
                  magic_type=magic_type, size_bytes=size)

    # ── Registering events ──

    def log_stored(self, filename: str, agent_file_id: str, size: int):
        self._add("registering", "INFO",
                  f"Session log stored: {filename} ({size:,} chars, id={agent_file_id})",
                  filename=filename, agent_file_id=agent_file_id)

    def log_store_failed(self, error: str):
        self._add("registering", "WARN", f"Failed to store session log: {error}")

    # ── Output ──

    def to_json(self, payload_uuid: str, encoder_label: str,
                wrapped_payload_uuid: str, input_size: int,
                output_size: int, final_status: str) -> str:
        """Produce the full JSON session log artifact."""
        doc = {
            "dolos_version": "0.9.0",
            "schema": "ssh_session_log_v1",
            "payload_uuid": payload_uuid,
            "wrapped_payload_uuid": wrapped_payload_uuid,
            "encoder": encoder_label,
            "input_size": input_size,
            "output_size": output_size,
            "final_status": final_status,
            "session_start": self._start_time.isoformat(),
            "session_end": datetime.now(timezone.utc).isoformat(),
            "event_count": len(self.events),
            "events": self.events,
        }
        return json.dumps(doc, indent=2, ensure_ascii=False)

    def to_summary(self) -> str:
        """Produce a compact human-readable summary of key events."""
        lines = []
        errors = [e for e in self.events if e["level"] in ("ERROR",)]
        warnings = [e for e in self.events if e["level"] == "WARN"]

        # Key events
        connect_events = [e for e in self.events if e["phase"] == "connecting"]
        if connect_events:
            connected = next((e for e in connect_events
                              if "Connected" in e["message"]), None)
            if connected:
                lines.append(f"Connected: {connected['message']}")

        cmd_events = [e for e in self.events if e["phase"] == "processing" and e["level"] == "CMD"]
        if cmd_events:
            exit_evt = next((e for e in cmd_events if "exited" in e["message"].lower()), None)
            if exit_evt:
                lines.append(f"Encoder: exit_code={exit_evt.get('exit_code', '?')}, "
                             f"elapsed={exit_evt.get('elapsed_s', '?')}s")

        # Stdout/stderr count
        stdout_lines = [e for e in self.events if e["level"] == "STDOUT"]
        stderr_lines = [e for e in self.events if e["level"] == "STDERR"]
        if stdout_lines:
            lines.append(f"Stdout: {len(stdout_lines)} lines")
        if stderr_lines:
            lines.append(f"Stderr: {len(stderr_lines)} lines")

        # Result
        result_events = [e for e in self.events if e["phase"] == "retrieving"]
        downloaded = next((e for e in result_events
                          if "Downloaded" in e.get("message", "")), None)
        if downloaded:
            lines.append(f"Result: {downloaded.get('size_bytes', '?'):,} bytes")

        # Validation
        val_events = [e for e in self.events if e["phase"] == "validating"]
        if val_events:
            lines.append(f"Status: {val_events[-1].get('status', '?')} — "
                         f"{val_events[-1].get('detail', '?')}")

        # Errors/warnings summary
        if errors:
            lines.append(f"Errors: {len(errors)}")
            for e in errors[:3]:
                lines.append(f"  - {e['message']}")
        if warnings:
            lines.append(f"Warnings: {len(warnings)}")

        return "\n".join(lines)


def _get_env_config() -> dict:
    """Read SSH configuration from environment variables.

    Returns dict with keys: host, port, username, password, private_key,
    public_key, timeout, auth_method ("key", "password", or "key+password")
    """
    host = os.environ.get(ENV_HOST, "").strip()
    port = int(os.environ.get(ENV_PORT, str(DEFAULT_PORT)))
    username = os.environ.get(ENV_USER, "").strip()
    password = os.environ.get(ENV_PASS, "").strip()
    private_key = os.environ.get(ENV_PRIV_KEY, "").strip()
    public_key = os.environ.get(ENV_PUB_KEY, "").strip()
    timeout = int(os.environ.get(ENV_TIMEOUT, str(DEFAULT_TIMEOUT)))

    has_key = bool(private_key)
    has_pass = bool(password)
    if has_key and has_pass:
        auth_method = "key+password"
    elif has_key:
        auth_method = "key"
    elif has_pass:
        auth_method = "password"
    else:
        auth_method = "none"

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "private_key": private_key,
        "public_key": public_key,
        "timeout": timeout,
        "auth_method": auth_method,
    }


def generate_ssh_keypair() -> tuple[str, str]:
    """Generate an ed25519 SSH keypair.

    NOTE: Not yet used in the build pipeline. Password auth is current method.
    Future: integrate key generation and transfer into install/build flow.

    Returns:
        (private_key_pem, public_key_string) tuple
    """
    key = paramiko.Ed25519Key.generate()
    # Private key as PEM
    private_io = io.StringIO()
    key.write_private_key(private_io)
    private_pem = private_io.getvalue()
    # Public key as OpenSSH format
    public_string = f"ssh-ed25519 {key.get_base64()} dolos"
    return private_pem, public_string


def _detect_remote_os(client: paramiko.SSHClient) -> str:
    """Auto-detect the remote OS by running 'ver' (Windows) or 'uname' (Linux)."""
    try:
        _stdin, stdout, stderr = client.exec_command("ver", timeout=5)
        output = stdout.read().decode("utf-8", "replace").lower()
        if "windows" in output:
            return "windows"
    except Exception:
        pass
    try:
        _stdin, stdout, stderr = client.exec_command("uname", timeout=5)
        output = stdout.read().decode("utf-8", "replace").lower()
        if output.strip():
            return "linux"
    except Exception:
        pass
    # Default to linux if detection fails
    return "linux"


def _workdir_root(target_os: str) -> str:
    """Per-OS root for temp directories. SFTP uses forward slashes even on Windows."""
    if target_os.lower().startswith("win"):
        return "C:/Windows/Temp"
    return "/tmp"


def generate_workdir_name() -> str:
    """Generate a random 6-character alphanumeric workdir name.

    Returns:
        Workdir name like 'wd_a3f7kx' (prefix 'wd_' + 6 random chars)
    """
    chars = string.ascii_lowercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"wd_{suffix}"


def detect_file_magic(data: bytes) -> str:
    """Detect file type from magic bytes. Returns a human-readable type string."""
    if len(data) < 2:
        return "empty"
    # PE/EXE/DLL (MZ header)
    if data[:2] == b"MZ":
        if len(data) >= 64:
            try:
                pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
                if pe_offset + 24 < len(data):
                    characteristics = struct.unpack_from("<H", data, pe_offset + 22)[0]
                    if characteristics & 0x2000:  # IMAGE_FILE_DLL
                        return "DLL"
            except Exception:
                pass
        return "PE/EXE"
    # ZIP/container (PK header)
    if data[:2] == b"PK":
        return "ZIP"
    # JSON
    if data[:1] in (b"{", b"["):
        return "JSON"
    # Shellcode indicators
    if len(data) >= 4:
        first4 = data[:4]
        if first4 == b"\x7fELF":
            return "ELF"
        if first4 == b"\xca\xfe\xba\xbe":
            return "MACHO"
    return f"unknown(0x{data[:4].hex()})" if len(data) >= 4 else f"unknown(0x{data[:2].hex()})"


def _load_private_key(key_content: str) -> paramiko.PKey:
    """Load an SSH private key from inline PEM content.

    Tries ed25519 first (preferred), then RSA, then ECDSA.
    Raises ValueError if no key format can parse the content.
    """
    key_content = key_content.strip()
    if not key_content:
        raise ValueError("Empty private key content")

    errors = []
    for loader_name, loader in [
        ("ed25519", lambda d: paramiko.Ed25519Key.from_private_key(io.StringIO(d))),
        ("rsa", lambda d: paramiko.RSAKey.from_private_key(io.StringIO(d))),
        ("ecdsa", lambda d: paramiko.ECDSAKey.from_private_key(io.StringIO(d))),
    ]:
        try:
            return loader(key_content)
        except Exception as e:
            errors.append(f"{loader_name}: {e}")

    raise ValueError(
        f"Could not load private key. Tried: {'; '.join(errors)}. "
        "Ensure DOLOS_SSH_PRIVATE_KEY contains a valid ed25519, RSA, or ECDSA key in PEM format."
    )


def _connect_ssh() -> paramiko.SSHClient:
    """Connect to SSH server using environment variable configuration.

    Auth priority:
      1. Key auth (DOLOS_SSH_PRIVATE_KEY) if configured
      2. Password auth (DOLOS_SSH_PASSWORD) if configured
    At least one auth method must be available.

    Returns:
        Connected paramiko.SSHClient

    Raises:
        ValueError if SSH_HOST is not configured or no auth method available
        paramiko exceptions on connection failure
    """
    config = _get_env_config()
    host = config["host"]
    port = config["port"]
    username = config["username"]
    password = config["password"]
    private_key_content = config["private_key"]
    auth_method = config["auth_method"]

    if not host:
        raise ValueError(
            "DOLOS_SSH_HOST is not configured. "
            "Set it in .env and reinstall the container. "
            "See /docs/agents/dolos/setup for help."
        )

    if auth_method == "none":
        raise ValueError(
            "No SSH auth method configured. Set DOLOS_SSH_PRIVATE_KEY (key auth) "
            "or DOLOS_SSH_PASSWORD (password auth) in .env. "
            "See /docs/agents/dolos/setup for help."
        )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Try key auth first, fall back to password
    pkey = None
    if private_key_content:
        pkey = _load_private_key(private_key_content)

    connect_kwargs = dict(
        hostname=host,
        port=port,
        username=username,
        timeout=20,
        allow_agent=False,
        look_for_keys=False,
    )
    if pkey:
        connect_kwargs["pkey"] = pkey
        # Also pass password as fallback for servers requiring both
        if password:
            connect_kwargs["password"] = password
    elif password:
        connect_kwargs["password"] = password

    client.connect(**connect_kwargs)
    return client


def _transfer_public_key(client: paramiko.SSHClient, username: str, public_key: str, remote_os: str) -> bool:
    """Transfer an SSH public key to the remote server's authorized_keys.

    On Windows (admin user): writes to C:\\ProgramData\\ssh\\administrators_authorized_keys
    On Linux/other: writes to ~/.ssh/authorized_keys
    """
    try:
        if remote_os.lower().startswith("win"):
            cmd = (
                f'powershell -Command "\\"{public_key}\\" | '
                f'Out-File -Append -Encoding ascii '
                f'C:\\\\ProgramData\\\\ssh\\\\administrators_authorized_keys"'
            )
            client.exec_command("mkdir C:\\ProgramData\\ssh 2>nul", timeout=10)
            client.exec_command("type nul > C:\\ProgramData\\ssh\\administrators_authorized_keys 2>nul", timeout=10)
            _stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
            exit_code = stdout.channel.recv_exit_status()
            return exit_code == 0
        else:
            client.exec_command("mkdir -p ~/.ssh && chmod 700 ~/.ssh", timeout=10)
            escaped_key = public_key.replace("'", "'\\''")
            cmd = f"echo '{escaped_key}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
            _stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
            exit_code = stdout.channel.recv_exit_status()
            return exit_code == 0
    except Exception:
        return False


def resolve_placeholders(command: str, workdir_cmd: str,
                         remote_filenames: dict,
                         extra_placeholders: dict = None) -> str:
    """Resolve {workdir}, {input}, {fileN}, {output} in the remote command template.

    workdir_cmd: the workdir path formatted for the remote shell
                 (backslashes on Windows, forward slashes on Linux).
    Placeholders {input}, {fileN}, {output} resolve to bare filenames —
    the operator controls path construction via {workdir} in their command.
    """
    result = command
    result = result.replace("{workdir}", workdir_cmd)
    for placeholder, filename in remote_filenames.items():
        result = result.replace("{" + placeholder + "}", filename)
    result = result.replace("{output}", "wd_out.bin")
    if extra_placeholders:
        for key, value in extra_placeholders.items():
            result = result.replace("{" + key + "}", str(value))
    return result


async def sftp_write_test(client: paramiko.SSHClient, sftp: paramiko.SFTPClient, remote_os: str) -> tuple[bool, str]:
    """Test SFTP write capability by uploading and deleting a small test file.

    Returns:
        (success, message) tuple
    """
    test_content = b"Dolos connectivity test"
    test_dir = _workdir_root(remote_os)
    test_path = test_dir + "/wd_test_connectivity.tmp"

    try:
        with sftp.open(test_path, "wb") as f:
            f.write(test_content)
        # Verify we can read it back
        read_back = sftp.stat(test_path)
        # Clean up
        sftp.remove(test_path)
        return True, "SFTP write test successful"
    except Exception as e:
        # Try to clean up if the file was created
        try:
            sftp.remove(test_path)
        except Exception:
            pass
        return False, f"SFTP write test failed: {e}"


async def transfer_and_execute(
    command: str,
    timeout: int,
    files: list[tuple[str, bytes]],
) -> dict:
    """Upload files, run remote command, download result. Returns structured dict.

    All SSH configuration comes from environment variables (DOLOS_SSH_*).
    No build parameters for SSH.

    Args:
        command: The resolved command string (placeholders already substituted)
        timeout: Command timeout in seconds
        files: list of (remote_filename, content_bytes). First entry is the
               payload file (mapped to {input}).

    Returns:
        dict with keys:
            exit_code: int
            stdout: str
            stderr: str
            output_bytes: bytes - downloaded output file content
            output_exists: bool
            magic_type: str - detected file type from magic bytes
            remote_os: str - "windows" or "linux"
            workdir: str - the remote workdir path used
            log: str - full command log
    """
    config = _get_env_config()
    host = config["host"]
    port = config["port"]
    username = config["username"]
    password = config["password"]
    private_key_content = config["private_key"]
    auth_method = config["auth_method"]

    default_result = {
        "exit_code": -1,
        "stdout": "",
        "stderr": "",
        "output_bytes": b"",
        "output_exists": False,
        "magic_type": "unknown",
        "remote_os": "unknown",
        "workdir": "",
        "log": "",
    }

    if not command:
        default_result["log"] = "No encoder command provided"
        return default_result

    if not host:
        default_result["log"] = "DOLOS_SSH_HOST is not configured"
        return default_result

    if auth_method == "none":
        default_result["log"] = "No SSH auth configured. Set DOLOS_SSH_PRIVATE_KEY or DOLOS_SSH_PASSWORD in .env."
        return default_result

    client = None
    local_dir = None

    try:
        # Connect — key auth preferred, password as fallback
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = dict(
            hostname=host,
            port=port,
            username=username,
            timeout=20,
            allow_agent=False,
            look_for_keys=False,
        )
        if private_key_content:
            connect_kwargs["pkey"] = _load_private_key(private_key_content)
            if password:
                connect_kwargs["password"] = password
        elif password:
            connect_kwargs["password"] = password

        client.connect(**connect_kwargs)

        remote_os = _detect_remote_os(client)
        default_result["remote_os"] = remote_os

        # Generate random workdir
        workdir_name = generate_workdir_name()
        workdir_root = _workdir_root(remote_os)
        workdir = workdir_root + "/" + workdir_name       # SFTP always uses /
        workdir_cmd = workdir.replace("/", "\\") if remote_os == "windows" else workdir
        default_result["workdir"] = workdir

        # Build remote filenames mapping for placeholder resolution
        remote_filenames = {}
        if files:
            remote_filenames["input"] = files[0][0]  # payload → {input}
        for i, (filename, _) in enumerate(files[1:], start=1):
            remote_filenames[f"file{i}"] = filename

        resolved_cmd = resolve_placeholders(command, workdir_cmd, remote_filenames)

        # Write files to local temp dir for SFTP upload
        local_dir = tempfile.mkdtemp(prefix="wd_")
        for filename, content in files:
            local_path = os.path.join(local_dir, filename)
            local_subdir = os.path.dirname(local_path)
            if local_subdir:
                os.makedirs(local_subdir, exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(content)

        sftp = client.open_sftp()

        # Create remote workdir
        try:
            sftp.mkdir(workdir)
        except IOError:
            # Directory might already exist or need parent creation
            if remote_os != "windows":
                client.exec_command(f'mkdir -p "{workdir}"', timeout=10)
            else:
                client.exec_command(f'mkdir "{workdir_cmd}"', timeout=10)
            import time
            time.sleep(0.5)

        # Upload all files
        for filename, _ in files:
            local_path = os.path.join(local_dir, filename)
            remote_path = workdir + "/" + filename
            sftp.put(local_path, remote_path)

        # Run the command
        _stdin, stdout, stderr = client.exec_command(resolved_cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")

        # Download the output file
        output_path = workdir + "/wd_out.bin"
        result_bytes = b""
        output_exists = False
        try:
            with sftp.open(output_path, "rb") as f:
                result_bytes = f.read()
                output_exists = True
        except IOError:
            pass

        # Detect file type
        magic_type = detect_file_magic(result_bytes) if result_bytes else "missing"

        # Cleanup remote files and workdir
        cleanup_errors = []
        for filename, _ in files:
            try:
                sftp.remove(workdir + "/" + filename)
            except Exception as e:
                cleanup_errors.append(f"remove {filename}: {e}")
        if output_exists:
            try:
                sftp.remove(output_path)
            except Exception as e:
                cleanup_errors.append(f"remove output: {e}")
        try:
            sftp.rmdir(workdir)
        except Exception as e:
            cleanup_errors.append(f"rmdir workdir: {e}")

        log = f"$ {resolved_cmd}\n[exit {exit_code}]\n{out}{err}"
        if cleanup_errors:
            log += f"\n[cleanup warnings: {'; '.join(cleanup_errors)}]"

        return {
            "exit_code": exit_code,
            "stdout": out,
            "stderr": err,
            "output_bytes": result_bytes,
            "output_exists": output_exists,
            "magic_type": magic_type,
            "remote_os": remote_os,
            "workdir": workdir,
            "log": log,
        }

    except Exception as e:
        logger.exception(f"Transfer error: {e}")
        return {
            **default_result,
            "log": f"transfer error: {e}",
            "stderr": str(e),
        }

    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass
        if local_dir:
            try:
                shutil.rmtree(local_dir)
            except Exception:
                pass


async def run_command(command: str, timeout: int = 120) -> tuple[int, str, str]:
    """Run a command on the external server using env-var SSH config.

    Auth priority: key (DOLOS_SSH_PRIVATE_KEY) if configured, then
    password (DOLOS_SSH_PASSWORD). At least one must be set.

    Returns (exit_code, stdout, stderr).
    """
    config = _get_env_config()
    host = config["host"]
    port = config["port"]
    username = config["username"]
    password = config["password"]
    private_key_content = config["private_key"]
    auth_method = config["auth_method"]

    if not host:
        raise ValueError("DOLOS_SSH_HOST is not configured.")
    if auth_method == "none":
        raise ValueError("No SSH auth configured. Set DOLOS_SSH_PRIVATE_KEY or DOLOS_SSH_PASSWORD.")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = dict(
        hostname=host,
        port=port,
        username=username,
        timeout=20,
        allow_agent=False,
        look_for_keys=False,
    )
    if private_key_content:
        connect_kwargs["pkey"] = _load_private_key(private_key_content)
        if password:
            connect_kwargs["password"] = password
    elif password:
        connect_kwargs["password"] = password

    client.connect(**connect_kwargs)
    try:
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        return exit_code, out, err
    finally:
        client.close()