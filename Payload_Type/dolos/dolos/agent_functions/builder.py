"""Dolos — Mythic Wrapper PayloadType.

Dolos is a **wrapper** payload type. It takes an existing built payload (selected
via Mythic's native "Create Wrapper" flow), transfers it to an external server
over SSH/SFTP, runs an encoder command, and returns the transformed result.

The input payload bytes arrive as ``self.wrapped_payload`` — provided natively
by Mythic. No file-dropdown, no GraphQL file lookup, no monkey-patch needed.

Build parameters:
  - Encoder (ChooseOne, static choices from DOLOS_REMOTE_COMMAND env var)
  - Timeout (Number, default 300)
  - Success String (String, default "ENCODING_SUCCESS")
  - Fail String (String, default "ENCODING_FAILED")

SSH config is environment-variables only (DOLOS_SSH_*).

All SSH/SFTP events are captured in an SSHSessionLog and stored as a JSON
artifact (<payload_name>.session.json) alongside the build result. This
provides forensically complete, timestamped logging of every operation.
"""

import asyncio
import json
import logging
import os
import pathlib
import ssl
import time
import tempfile
import shutil

import paramiko
import mythic_container.PayloadBuilder
from mythic_container.PayloadBuilder import *
from mythic_container.MythicCommandBase import *
from mythic_container.MythicRPC import *

from dolos import ssh_client
from dolos.ssh_client import SSHSessionLog

logger = logging.getLogger(__name__)
logging.getLogger("dolos").setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# Load version from agent_capabilities.json (single source of truth)
# ---------------------------------------------------------------------------
_CAPABILITIES_PATH = pathlib.Path(__file__).parent.parent / "agent_capabilities.json"
_VERSION = json.loads(_CAPABILITIES_PATH.read_text())["agent_version"]

# ---------------------------------------------------------------------------
# Load encoder choices from env at import time (no dynamic query needed)
# ---------------------------------------------------------------------------

def _load_encoder_choices() -> list[str]:
    """Read encoder labels from DOLOS_REMOTE_COMMAND env var."""
    raw = os.environ.get("DOLOS_REMOTE_COMMAND", "")
    if not raw:
        return ["PyEncoder_v1.0"]
    try:
        return list(json.loads(raw).keys())
    except Exception:
        return ["PyEncoder_v1.0"]


def _lookup_encoder_command(label: str) -> str:
    """Look up the full command string for an encoder label."""
    raw = os.environ.get("DOLOS_REMOTE_COMMAND", "")
    if not raw:
        return ""
    try:
        return json.loads(raw).get(label, "")
    except Exception:
        return ""


_ENCODER_CHOICES = _load_encoder_choices()


# ---------------------------------------------------------------------------
# PayloadType definition — a Mythic wrapper
# ---------------------------------------------------------------------------

class Dolos(PayloadType):
    """
    Dolos — "The Craftsman of Lies" — a Mythic wrapper payload.

    Takes an existing built payload (shellcode, EXE, etc.), transfers it to an
    external server over SSH, runs an encoder command, and returns the result.
    The wrapped payload's C2 is already embedded — no C2 profile selection needed.
    """

    name = "dolos"
    file_extension = "bin"
    author = "@3mrgnc3"
    supported_os = ["SSH Server + Any OS"]
    wrapper = True
    # Payload types Dolos can wrap. Listed on the wrapper side because we can't
    # modify each agent's code to list Dolos. Mythic's sync deletion is commented
    # out, so these relationships persist. Add new agents here + reinstall.
    wrapped_payloads = ["apollo", "merlin", "athena", "medusa", "hannibal", "freyja", "poopsie", "poseidon"]
    note = (
        f"Dolos v{_VERSION} | The Craftsman of Lies — wrap an existing payload, "
        "transfer it to an external server over SSH/SFTP, run an encoder "
        "(C# cradle, Donut, ShellcodePack, custom), and return the result. "
        "Built-in C# cradle encoder (csc.exe). Full session logging. "
        "Rotating file logs. See docs for setup."
    )
    supports_dynamic_loading = False
    mythic_encrypts = True
    translation_container = None
    agent_type = AgentType.Wrapper
    agent_path = pathlib.Path(".") / "dolos"
    # Load icon bytes relative to this module so it works regardless of CWD
    # (Docker CWD is /Mythic/, local debug CWD is the project root)
    _icon_path = pathlib.Path(__file__).parent.parent / "dolos.svg"
    agent_icon_bytes = _icon_path.read_bytes() if _icon_path.exists() else b""
    agent_code_path = agent_path / "agent_code"
    c2_profiles = []
    build_parameters = [
        BuildParameter(
            name="Encoder",
            parameter_type=BuildParameterType.ChooseOne,
            description=(
                "Select an encoder command. Configured in .env via "
                "DOLOS_REMOTE_COMMAND. Each option runs a specific "
                "command on the external server."
            ),
            choices=_ENCODER_CHOICES,
            group_name="Remote Command",
        ),
        BuildParameter(
            name="Timeout",
            parameter_type=BuildParameterType.Number,
            description="Timeout in seconds for the remote command.",
            default_value=300,
            required=False,
            group_name="Remote Command",
        ),
        BuildParameter(
            name="Success String",
            parameter_type=BuildParameterType.String,
            description=(
                "String to search for in stdout to confirm success. "
                "Critical for pipeline logic — determines when to initiate file transfer."
            ),
            default_value="ENCODING_SUCCESS",
            required=False,
            group_name="Remote Command",
        ),
        BuildParameter(
            name="Fail String",
            parameter_type=BuildParameterType.String,
            description=(
                "String to search for in stdout/stderr to detect failure. "
                "If found, the build is marked as failed regardless of exit code."
            ),
            default_value="ENCODING_FAILED",
            required=False,
            group_name="Remote Command",
        ),
        BuildParameter(
            name="Regenerate Shellcode",
            parameter_type=BuildParameterType.Boolean,
            description=(
                "If the selected shellcode has already been wrapped by Dolos, "
                "automatically regenerate it with the same configuration but a new UUID. "
                "When enabled (default), wrapping proceeds by rebuilding the inner payload. "
                "Disable this if you want the build to fail instead of auto-regenerating."
            ),
            default_value=True,
            required=False,
            group_name="Deduplication",
        ),
    ]
    build_steps = [
        BuildStep(step_name="Rebuilding", step_description="Auto-regenerating shellcode — inner payload already wrapped by Dolos"),
        BuildStep(step_name="Connecting", step_description="Verifying SSH connectivity, auth, and SFTP write test"),
        BuildStep(step_name="Preparing", step_description="Generating workdir and creating it on remote server"),
        BuildStep(step_name="Uploading", step_description="Sending wrapped payload to the remote workdir"),
        BuildStep(step_name="Processing", step_description="Running encoder command on remote server"),
        BuildStep(step_name="Retrieving", step_description="Downloading result file from remote server"),
        BuildStep(step_name="Cleaning", step_description="Removing remote workdir and all contents"),
        BuildStep(step_name="Validating", step_description="Checking exit code, success/fail indicators, and magic bytes"),
        BuildStep(step_name="Registering", step_description="Storing session log and build result in Mythic"),
    ]

    # -----------------------------------------------------------------------
    # Build pipeline
    # -----------------------------------------------------------------------

    async def build(self) -> BuildResponse:
        resp = BuildResponse(status=BuildStatus.Error)
        session_log = SSHSessionLog()

        logger.critical("[DOLOS-BUILD] ========== build() STARTED ==========")
        logger.info(f"[DOLOS-BUILD] wrapped_payload_uuid={self.wrapped_payload_uuid}")
        logger.info(f"[DOLOS-BUILD] wrapped_payload size={len(self.wrapped_payload) if self.wrapped_payload else 0} bytes")
        logger.info(f"[DOLOS-BUILD] filename={self.filename}")

        # ── 1. Collect build parameters ──

        encoder_label = (self.get_parameter("Encoder") or "").strip()
        timeout = int(self.get_parameter("Timeout") or 300)
        success_string = (self.get_parameter("Success String") or "").strip()
        failure_string = (self.get_parameter("Fail String") or "").strip()
        regenerate = self.get_parameter("Regenerate Shellcode") or False

        # ── Validate: wrapped payload must be present ──

        if not self.wrapped_payload:
            await self._step("Connecting", "No wrapped payload — select a payload to wrap", False)
            resp.build_message = "No wrapped payload. Select an existing payload in the Create Wrapper dialog."
            return resp

        if not encoder_label:
            await self._step("Connecting", "No encoder selected", False)
            resp.build_message = "Encoder is required — select an encoder command from the dropdown"
            return resp

        # ── Check: has this payload already been wrapped by Dolos? ──
        # Each inner payload UUID can only be wrapped once. If it already has a
        # successful Dolos build, we either fail (default) or auto-regenerate
        # the inner payload with a new UUID (if Regenerate Shellcode is enabled).

        already_wrapped = await self._check_already_wrapped()
        if already_wrapped:
            if regenerate:
                # Regenerate ON: auto-rebuild inner payload with new UUID
                logger.info(f"[DOLOS-BUILD] Inner payload {self.wrapped_payload_uuid} already has "
                            f"a successful Dolos build. Regenerate Shellcode enabled — "
                            f"rebuilding inner payload with new UUID.")
                rebuild_ok = await self._rebuild_inner_payload(already_wrapped)
                if not rebuild_ok:
                    await self._step("Rebuilding",
                        "Failed to regenerate shellcode — proceeding with original.",
                        False)
                    # Don't fail the build — just proceed with the original shellcode
                # else: self.wrapped_payload and self.wrapped_payload_uuid are now updated
            else:
                # Regenerate OFF: reuse the same shellcode, just proceed.
                # The operator explicitly chose to wrap the same shellcode again.
                logger.info(f"[DOLOS-BUILD] Inner payload {self.wrapped_payload_uuid} already has "
                            f"a successful Dolos build, but Regenerate Shellcode is OFF — "
                            f"proceeding with the same shellcode.")
                await self._step("Rebuilding",
                    f"Shellcode already wrapped — re-wrapping as-is (Regenerate Shellcode is OFF)",
                    True)

        payload_bytes = self.wrapped_payload
        payload_size = len(payload_bytes)
        logger.info(f"[DOLOS-BUILD] Input payload: {payload_size:,} bytes")

        # ── Resolve encoder command from label ──

        encoder_command = _lookup_encoder_command(encoder_label)
        if not encoder_command:
            await self._step("Connecting", f"Encoder '{encoder_label}' not found in configuration", False)
            resp.build_message = f"Encoder '{encoder_label}' not found in DOLOS_REMOTE_COMMAND"
            return resp

        await self._step("Connecting", f"Encoder: {encoder_label} | Input: {payload_size:,} bytes", True)

        # ── Get SSH config from environment ──

        ssh_config = ssh_client._get_env_config()
        host = ssh_config["host"]
        port = ssh_config["port"]
        username = ssh_config["username"]
        ssh_password = ssh_config["password"]
        ssh_private_key = ssh_config["private_key"]
        auth_method = ssh_config["auth_method"]

        if not host:
            await self._step("Connecting", "DOLOS_SSH_HOST not configured", False)
            resp.build_message = "SSH host not configured. Set DOLOS_SSH_HOST in .env and reinstall. See /docs/agents/dolos/setup for help."
            return resp

        if auth_method == "none":
            await self._step("Connecting", "No SSH auth configured", False)
            resp.build_message = "No SSH auth method configured. Set DOLOS_SSH_PRIVATE_KEY (key auth) or DOLOS_SSH_PASSWORD (password auth) in .env. See /docs/agents/dolos/setup for help."
            return resp

        logger.info(f"[DOLOS-BUILD] SSH config: {username}@{host}:{port} auth={auth_method}")

        # ── Verify SSH connectivity (Step 1: Connecting) ──

        session_log.connecting(host, port, username)
        auth_desc = f"{auth_method}" if auth_method != "key+password" else "key+password"
        await self._step("Connecting", f"Connecting to {username}@{host}:{port} ({auth_desc})…", True)

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Key auth preferred, password fallback
            connect_kwargs = dict(
                hostname=host, port=port, username=username,
                timeout=20, allow_agent=False, look_for_keys=False,
            )
            if ssh_private_key:
                pkey = ssh_client._load_private_key(ssh_private_key)
                connect_kwargs["pkey"] = pkey
                if ssh_password:
                    connect_kwargs["password"] = ssh_password
            elif ssh_password:
                connect_kwargs["password"] = ssh_password

            client.connect(**connect_kwargs)
            logger.info(f"[DOLOS-BUILD] SSH connected to {host}:{port} via {auth_method}")
        except Exception as e:
            session_log.connection_failed(str(e))
            await self._step("Connecting", f"SSH connection failed: {e}", False)
            resp.build_message = f"SSH connection failed: {e}. Check DOLOS_SSH_HOST/PORT/USERNAME and auth config (DOLOS_SSH_PRIVATE_KEY or DOLOS_SSH_PASSWORD) in .env."
            return resp

        sftp = None
        workdir = ""
        remote_os = "linux"

        try:
            remote_os = ssh_client._detect_remote_os(client)
            session_log.connected(host, port, remote_os)
            session_log.auth_success(username, auth_method)
            sftp = client.open_sftp()
            sftp_ok, sftp_msg = await ssh_client.sftp_write_test(client, sftp, remote_os)
            session_log.sftp_test(sftp_ok, sftp_msg)
            if not sftp_ok:
                await self._step("Connecting", f"✅ SSH ✅ Auth ❌ SFTP write: {sftp_msg}", False)
                resp.build_message = f"SFTP write test failed: {sftp_msg}"
                client.close()
                return resp
            await self._step("Connecting",
                f"✅ SSH ✅ Auth ✅ SFTP — connected to {remote_os}",
                True)
        except Exception as e:
            session_log.connection_failed(str(e))
            await self._step("Connecting", f"Connection verification failed: {e}", False)
            resp.build_message = f"Connection verification failed: {e}"
            if client:
                client.close()
            return resp

        # ── 2. Prepare workdir (Step 2: Preparing) ──

        workdir_name = ssh_client.generate_workdir_name()
        workdir_root = ssh_client._workdir_root(remote_os)
        workdir = workdir_root + "/" + workdir_name
        workdir_cmd = workdir.replace("/", "\\") if remote_os == "windows" else workdir

        session_log.creating_workdir(workdir, remote_os)
        await self._step("Preparing", f"Creating remote workdir: {workdir}", True)

        try:
            sftp.mkdir(workdir)
            session_log.workdir_created(workdir)
        except IOError:
            try:
                if remote_os.lower().startswith("win"):
                    client.exec_command(f'mkdir "{workdir_cmd}"', timeout=10)
                else:
                    client.exec_command(f'mkdir -p "{workdir}"', timeout=10)
                time.sleep(0.5)
                session_log.workdir_created(workdir)
            except Exception as e:
                await self._step("Preparing", f"Failed to create workdir: {e}", False)
                resp.build_message = f"Failed to create remote workdir: {e}"
                client.close()
                return resp

        # ── 3. Upload wrapped payload (Step 3: Uploading) ──

        remote_filenames = {"input": "wd_in.bin"}
        files: list[tuple[str, bytes]] = [("wd_in.bin", payload_bytes)]
        total_size = payload_size

        upload_start = time.time()
        session_log.uploading_file("wd_in.bin", f"{workdir}/{workdir_cmd}/wd_in.bin", total_size)
        await self._step("Uploading", f"Uploading wrapped payload ({total_size:,} bytes) to {workdir}", True)

        local_dir = tempfile.mkdtemp(prefix="dolos_")
        try:
            for filename, content in files:
                local_path = os.path.join(local_dir, filename)
                with open(local_path, "wb") as f:
                    f.write(content)
                sftp.put(local_path, workdir + "/" + filename)
            upload_elapsed = time.time() - upload_start
            session_log.upload_complete("wd_in.bin", total_size, upload_elapsed)
        except Exception as e:
            session_log.upload_failed("wd_in.bin", str(e))
            await self._step("Uploading", f"Upload failed: {e}", False)
            resp.build_message = f"Failed to upload files: {e}"
            try:
                for filename, _ in files:
                    sftp.remove(workdir + "/" + filename)
                sftp.rmdir(workdir)
            except Exception:
                pass
            client.close()
            return resp
        finally:
            try:
                shutil.rmtree(local_dir)
            except Exception:
                pass

        # ── 4. Run encoder command (Step 4: Processing) ──

        resolved_cmd = ssh_client.resolve_placeholders(encoder_command, workdir_cmd, remote_filenames)
        logger.info(f"[DOLOS-BUILD] Running encoder: {resolved_cmd[:200]}")

        session_log.running_command(resolved_cmd)
        await self._step("Processing", f"Running: {resolved_cmd[:120]}…", True)

        cmd_start = time.time()
        try:
            _stdin, stdout, stderr = client.exec_command(resolved_cmd, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            cmd_elapsed = time.time() - cmd_start

            session_log.command_started(resolved_cmd)
            for line in out.splitlines():
                session_log.command_stdout(line)
            for line in err.splitlines():
                session_log.command_stderr(line)
            session_log.command_exit(exit_code, cmd_elapsed)
        except Exception as e:
            session_log.command_failed(str(e))
            await self._step("Processing", f"Command execution failed: {e}", False)
            resp.build_message = f"Encoder command failed: {e}"
            try:
                for filename, _ in files:
                    sftp.remove(workdir + "/" + filename)
                sftp.remove(workdir + "/wd_out.bin")
                sftp.rmdir(workdir)
            except Exception:
                pass
            client.close()
            return resp

        # ── 5. Retrieve output (Step 5: Retrieving) ──

        output_path = workdir + "/wd_out.bin"
        result_bytes = b""
        output_exists = False

        try:
            session_log.downloading_result(output_path)
            with sftp.open(output_path, "rb") as f:
                result_bytes = f.read()
                output_exists = True
            session_log.result_downloaded(output_path, len(result_bytes))
            logger.info(f"[DOLOS-BUILD] Retrieved {len(result_bytes)} bytes from remote")
            await self._step("Retrieving", f"Downloaded {len(result_bytes):,} bytes from {output_path}", True)
        except IOError:
            session_log.result_missing(output_path)
            logger.info(f"[DOLOS-BUILD] Output file NOT found at {output_path}")
            await self._step("Retrieving", "Output file not found on remote server", False)

        # ── 6. Clean up remote workdir (Step 6: Cleaning) ──

        try:
            for filename, _ in files:
                try:
                    sftp.remove(workdir + "/" + filename)
                    session_log.cleanup_file(workdir + "/" + filename, True)
                except Exception as e:
                    session_log.cleanup_file(workdir + "/" + filename, False, str(e))
            if output_exists:
                try:
                    sftp.remove(output_path)
                    session_log.cleanup_file(output_path, True)
                except Exception as e:
                    session_log.cleanup_file(output_path, False, str(e))
            try:
                sftp.rmdir(workdir)
                session_log.cleanup_workdir(workdir, True)
            except Exception as e:
                session_log.cleanup_workdir(workdir, False, str(e))
        except Exception:
            pass

        await self._step("Cleaning", "Cleaned up remote workdir", True)

        try:
            client.close()
        except Exception:
            pass

        # ── 7. Validate result (Step 7: Validating) ──

        magic_type = ssh_client.detect_file_magic(result_bytes) if result_bytes else "missing"
        session_log.magic_detected(magic_type, len(result_bytes))

        status = "SUCCESS"
        status_detail = ""
        success_indicated = False
        failure_indicated = False

        if success_string and success_string in out:
            success_indicated = True
        if failure_string and (failure_string in out or failure_string in err):
            failure_indicated = True

        if exit_code != 0 and not output_exists:
            status = "FAILURE"
            status_detail = f"Command failed (exit {exit_code}) and no output file produced"
        elif failure_indicated:
            if output_exists:
                status = "WARNING"
                status_detail = f"Fail indicator '{failure_string}' found, but file exists — verify manually"
            else:
                status = "FAILURE"
                status_detail = f"Fail indicator '{failure_string}' found in output"
        elif exit_code != 0 and output_exists:
            status = "WARNING"
            status_detail = f"Command exited with code {exit_code} but output file exists — verify result"
        elif not output_exists:
            status = "FAILURE"
            status_detail = "Command completed but no output file produced"
        elif success_indicated:
            status = "SUCCESS"
            status_detail = "Success confirmed"
        else:
            status = "SUCCESS"
            status_detail = "Command completed successfully"

        session_log.validating(status, status_detail, exit_code, payload_size, len(result_bytes),
                               magic_type, success_string if success_indicated else "",
                               failure_string if failure_indicated else "")

        validating_msg = (
            f"Status: {status} — {status_detail} | "
            f"Exit code: {exit_code} | "
            f"File type: {magic_type} | "
            f"Size: {payload_size:,}→{len(result_bytes):,} bytes"
        )
        await self._step("Validating", validating_msg, status != "FAILURE")

        if status == "FAILURE":
            # Store session log even on failure
            fail_filename = self.filename or "dolos_output.exe"
            await self._store_session_log(session_log, encoder_label, payload_size,
                                          len(result_bytes), status, fail_filename, resp)
            resp.build_message = (
                f"{status}: {status_detail}\n"
                f"stdout: {out[:500]}\n"
                f"stderr: {err[:500]}"
            )
            resp.build_stderr = f"{status}: {status_detail}"
            return resp

        # ── 8. Register session log and build result (Step 8: Registering) ──

        result_filename = self.filename or "dolos_output.exe"

        # Determine magic-aware extension for download filename
        base = os.path.splitext(result_filename)[0]
        ext_map = {
            "PE/EXE": ".exe",
            "DLL": ".dll",
            "ELF": ".elf",
            "MACHO": ".macho",
            "ZIP": ".zip",
            "JSON": ".json",
        }
        result_ext = ext_map.get(magic_type, os.path.splitext(result_filename)[1] or ".bin")
        download_filename = f"{base}{result_ext}"

        await self._store_session_log(session_log, encoder_label, payload_size,
                                      len(result_bytes), status, download_filename, resp)

        # ── Build result ──

        logger.info(f"[DOLOS-BUILD] Setting resp.payload = {len(result_bytes)} bytes")

        # Set a descriptive download filename based on detected output type.
        # Without this, Mythic uses the default (e.g., "dolos.exe") regardless
        # of actual content. With magic detection, a DLL gets .dll, etc.
        resp.updated_filename = download_filename
        logger.info(f"[DOLOS-BUILD] updated_filename = {resp.updated_filename} (magic: {magic_type})")

        status_prefix = ""
        if status == "WARNING":
            status_prefix = f"⚠️ {status_detail}. "

        resp.status = BuildStatus.Success
        resp.payload = result_bytes  # lowercase! — the v0.5.1 lesson
        logger.info(f"[DOLOS-BUILD] resp.payload set, get_payload() = {len(resp.get_payload())} bytes")
        resp.build_message = (
            f"{status_prefix}Wrapped {payload_size:,} → {len(result_bytes):,} bytes ({magic_type}) "
            f"via {encoder_label}. Download: {resp.updated_filename}"
        )
        resp.build_stdout = out
        resp.build_stderr = err if status != "SUCCESS" else ""

        logger.critical(f"[DOLOS-BUILD] ========== build() COMPLETE, returning {len(result_bytes)} bytes ==========")
        return resp

    # -----------------------------------------------------------------------
    # Hasura helpers — get operation-scoped TaskID for MythicRPC calls
    # -----------------------------------------------------------------------

    async def _get_task_id(self, operation_id: int) -> int | None:
        """Look up any TaskID in the given operation via Hasura.

        SendMythicRPCPayloadCreateFromScratch requires a TaskID to scope the build
        to the correct operation. We don't have a task context during build, so we
        look up any task in the same operation via Hasura GraphQL.

        Returns a TaskID (int) or None if no task found.
        """
        import urllib.request
        import urllib.error

        hasura_url = os.environ.get("HASURA_URL",
            "http://127.0.0.1:8080/v1/graphql" if os.environ.get("DOLOS_DEV_MODE")
            else "http://mythic_graphql:8080/v1/graphql")
        hasura_secret = os.environ.get("HASURA_SECRET", "")

        if not hasura_secret:
            logger.error("[DOLOS-BUILD] HASURA_SECRET not set — cannot look up TaskID")
            return None

        ssl_ctx = None
        if os.environ.get("DOLOS_DEV_MODE"):
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        headers = {
            "Content-Type": "application/json",
            "x-hasura-admin-secret": hasura_secret,
        }

        try:
            query = json.dumps({
                "query": '''
                query GetTaskForOperation($op_id: Int!) {
                  task(where: {operation_id: {_eq: $op_id}}, limit: 1, order_by: {id: desc}) {
                    id
                  }
                }''',
                "variables": {"op_id": operation_id}
            }).encode()

            req = urllib.request.Request(hasura_url, data=query, headers=headers)
            resp = urllib.request.urlopen(req, timeout=10, context=ssl_ctx)
            data = json.loads(resp.read())

            tasks = data.get("data", {}).get("task", [])
            if not tasks:
                logger.error(f"[DOLOS-BUILD] No tasks found in operation {operation_id} — cannot scope rebuild")
                return None

            task_id = tasks[0]["id"]
            logger.info(f"[DOLOS-BUILD] Found TaskID {task_id} in operation {operation_id}")
            return task_id

        except Exception as e:
            logger.error(f"[DOLOS-BUILD] Hasura TaskID lookup failed: {e}")
            return None

    # -----------------------------------------------------------------------
    # Shellcode deduplication — check and rebuild
    # -----------------------------------------------------------------------

    async def _check_already_wrapped(self):
        """Check if the wrapped payload UUID already has a successful Dolos build.

        Uses Hasura GraphQL to find Dolos payloads where wrapped_payload_id
        matches our inner payload. SendMythicRPCPayloadSearch can't do this —
        it requires a PayloadUUID or CallbackID and can't filter by wrapped_payload_id.
        Hasura can.

        Returns a dict with 'inner_id', 'inner_uuid', 'operation_id', and 'wrapper_uuid'
        if the inner payload already has a successful Dolos build, or None otherwise.
        """
        if not self.wrapped_payload_uuid:
            return None

        import urllib.request
        import urllib.error

        # In Docker: mythic_graphql resolves via Docker network
        # In local debug: must use 127.0.0.1
        hasura_url = os.environ.get("HASURA_URL",
            "http://127.0.0.1:8080/v1/graphql" if os.environ.get("DOLOS_DEV_MODE")
            else "http://mythic_graphql:8080/v1/graphql")
        hasura_secret = os.environ.get("HASURA_SECRET", "")

        if not hasura_secret:
            logger.warning("[DOLOS-BUILD] HASURA_SECRET not set — cannot check for "
                          "already-wrapped payloads. Proceeding without deduplication.")
            return None

        # Allow self-signed certs in dev mode
        ssl_ctx = None
        if os.environ.get("DOLOS_DEV_MODE"):
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        headers = {
            "Content-Type": "application/json",
            "x-hasura-admin-secret": hasura_secret,
        }

        try:
            # Step 1: Get the inner payload's database ID and operation_id from its UUID
            inner_uuid = self.wrapped_payload_uuid
            inner_query = json.dumps({
                "query": '''
                query GetInnerPayload($uuid: String!) {
                  payload(where: {uuid: {_eq: $uuid}}) {
                    id
                    operation_id
                  }
                }''',
                "variables": {"uuid": inner_uuid}
            }).encode()

            req1 = urllib.request.Request(hasura_url, data=inner_query, headers=headers)
            resp1 = urllib.request.urlopen(req1, timeout=10, context=ssl_ctx)
            inner_data = json.loads(resp1.read())

            inner_payloads = inner_data.get("data", {}).get("payload", [])
            if not inner_payloads:
                logger.info(f"[DOLOS-BUILD] Inner payload UUID {inner_uuid} not found in DB — "
                            "no dedup check possible")
                return None

            inner_id = inner_payloads[0]["id"]
            operation_id = inner_payloads[0]["operation_id"]
            logger.info(f"[DOLOS-BUILD] Inner payload UUID {inner_uuid} → DB id {inner_id}, "
                        f"operation_id {operation_id}")

            # Step 2: Find Dolos payloads that successfully wrap this inner payload
            wrap_query = json.dumps({
                "query": '''
                query FindDolosWrappers($inner_id: Int!) {
                  payload(where: {
                    payloadtype: {name: {_eq: "dolos"}},
                    wrapped_payload_id: {_eq: $inner_id},
                    build_phase: {_eq: "success"}
                  }, order_by: {id: desc}, limit: 1) {
                    id uuid build_phase
                  }
                }''',
                "variables": {"inner_id": inner_id}
            }).encode()

            req2 = urllib.request.Request(hasura_url, data=wrap_query, headers=headers)
            resp2 = urllib.request.urlopen(req2, timeout=10, context=ssl_ctx)
            wrap_data = json.loads(resp2.read())

            dolos_wrappers = wrap_data.get("data", {}).get("payload", [])

        except Exception as e:
            logger.warning(f"[DOLOS-BUILD] Hasura query failed (will proceed without dedup): {e}")
            return None

        if dolos_wrappers:
            wrapper = dolos_wrappers[0]
            logger.info(f"[DOLOS-BUILD] Inner payload {inner_uuid} (id={inner_id}) already has "
                        f"a successful Dolos build: payload {wrapper['uuid']} (id={wrapper['id']})")
            return {
                "inner_id": inner_id,
                "inner_uuid": inner_uuid,
                "operation_id": operation_id,
                "wrapper_uuid": wrapper["uuid"],
            }

        logger.info(f"[DOLOS-BUILD] Inner payload {inner_uuid} (id={inner_id}) has no existing Dolos builds — proceeding")
        return None

    async def _rebuild_inner_payload(self, dedup_info: dict) -> bool:
        """Rebuild the inner payload with the same configuration but a new UUID.

        Uses MythicRPC SendMythicRPCPayloadCreateFromScratch to trigger a new build
        of the inner payload with identical config. Polls until complete, then fetches
        the new bytes and updates self.wrapped_payload / self.wrapped_payload_uuid.

        Args:
            dedup_info: Dict from _check_already_wrapped() with keys:
                'inner_id', 'inner_uuid', 'operation_id', 'wrapper_uuid'

        Returns True if rebuild succeeded (self.wrapped_payload updated), False otherwise.
        """
        # Step 1: Search for the inner payload's configuration
        try:
            inner_search = await SendMythicRPCPayloadSearch(
                MythicRPCPayloadSearchMessage(
                    PayloadUUID=self.wrapped_payload_uuid,
                )
            )
        except Exception as e:
            logger.error(f"[DOLOS-BUILD] Failed to search for inner payload: {e}")
            return False

        if not inner_search.Success or not inner_search.Payloads:
            logger.error(f"[DOLOS-BUILD] Inner payload not found: {inner_search.Error}")
            return False

        inner_payload = inner_search.Payloads[0]
        logger.info(f"[DOLOS-BUILD] Found inner payload: type={inner_payload.PayloadType}, "
                    f"uuid={inner_payload.UUID}, "
                    f"os={inner_payload.SelectedOS}")

        await self._step("Rebuilding",
            f"Rebuilding {inner_payload.PayloadType} payload (same config, new UUID)…",
            True)

        # Step 2: Get a real TaskID for operation scoping
        # CreateFromScratch requires TaskID to scope the build to an operation.
        # TaskID=0 fails with "sql: no rows in result set" — Mythic can't find
        # the operation. We look up any task in the same operation via Hasura.
        task_id = await self._get_task_id(dedup_info["operation_id"])
        if not task_id:
            logger.error("[DOLOS-BUILD] Cannot find a TaskID for operation scoping — rebuild failed")
            return False

        logger.info(f"[DOLOS-BUILD] Using TaskID {task_id} for operation {dedup_info['operation_id']}")

        # Step 3: Create a new payload with the same configuration
        # The search result returns PayloadConfiguration objects from the search
        # module, but CreateFromScratch expects its own module's classes.
        # We use .to_json() to convert to plain dicts, then reconstruct.
        from mythic_container.MythicGoRPC.send_mythic_rpc_payload_create_from_scratch import (
            MythicRPCPayloadConfiguration as CreateConfig,
            MythicRPCPayloadConfigurationC2Profile as CreateC2,
            MythicRPCPayloadConfigurationBuildParameter as CreateBuildParam,
        )

        c2_profiles = [CreateC2(**profile.to_json()) for profile in (inner_payload.C2Profiles or [])]
        build_params = [CreateBuildParam(**param.to_json()) for param in (inner_payload.BuildParameters or [])]

        new_config = CreateConfig(
            Description=f"Auto-rebuilt for Dolos wrapping (from {inner_payload.Description or inner_payload.Filename})",
            PayloadType=inner_payload.PayloadType,
            C2Profiles=c2_profiles,
            BuildParameters=build_params,
            Commands=inner_payload.Commands,
            SelectedOS=inner_payload.SelectedOS,
            Filename=inner_payload.Filename,
        )

        try:
            create_result = await SendMythicRPCPayloadCreateFromScratch(
                MythicRPCPayloadCreateFromScratchMessage(
                    TaskID=task_id,
                    PayloadConfiguration=new_config,
                )
            )
        except Exception as e:
            logger.error(f"[DOLOS-BUILD] Failed to create new inner payload: {e}")
            return False

        if not create_result.Success:
            logger.error(f"[DOLOS-BUILD] Inner payload rebuild failed: {create_result.Error}")
            return False

        new_uuid = create_result.NewPayloadUUID
        logger.info(f"[DOLOS-BUILD] New inner payload created: {new_uuid}")

        # Step 3: Poll until the new build completes
        max_wait = 300  # 5 minutes
        poll_interval = 2  # seconds
        elapsed = 0
        build_phase = ""

        await self._step("Rebuilding",
            f"Waiting for {inner_payload.PayloadType} build to complete…",
            True)

        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            try:
                poll_result = await SendMythicRPCPayloadSearch(
                    MythicRPCPayloadSearchMessage(
                        PayloadUUID=new_uuid,
                    )
                )
            except Exception:
                continue  # Poll errors are transient

            if not poll_result.Success or not poll_result.Payloads:
                continue

            build_phase = poll_result.Payloads[0].BuildPhase
            logger.info(f"[DOLOS-BUILD] Rebuild poll: uuid={new_uuid}, "
                        f"phase={build_phase}, elapsed={elapsed}s")

            if build_phase == "success":
                break
            elif build_phase == "error":
                logger.error(f"[DOLOS-BUILD] Inner payload rebuild failed (error phase)")
                return False

        if build_phase != "success":
            logger.error(f"[DOLOS-BUILD] Inner payload rebuild timed out after {max_wait}s "
                        f"(phase={build_phase})")
            return False

        # Step 4: Fetch the new payload's bytes
        new_payload = poll_result.Payloads[0]
        if not new_payload.AgentFileId:
            logger.error("[DOLOS-BUILD] New payload has no AgentFileId — cannot fetch bytes")
            return False

        try:
            file_result = await SendMythicRPCFileGetContent(
                MythicRPCFileGetContentMessage(
                    AgentFileID=new_payload.AgentFileId,
                )
            )
        except Exception as e:
            logger.error(f"[DOLOS-BUILD] Failed to fetch new payload bytes: {e}")
            return False

        if not file_result.Success:
            logger.error(f"[DOLOS-BUILD] Failed to get new payload content: {file_result.Error}")
            return False

        # Step 5: Update self to use the new payload
        new_bytes = file_result.Content
        self.wrapped_payload = new_bytes
        self.wrapped_payload_uuid = new_uuid
        logger.info(f"[DOLOS-BUILD] Rebuilt inner payload: {new_uuid} ({len(new_bytes):,} bytes)")

        await self._step("Rebuilding",
            f"✅ Regenerated {inner_payload.PayloadType} payload ({len(new_bytes):,} bytes) — now wrapping new UUID",
            True)
        return True

    async def _store_session_log(self, session_log: SSHSessionLog,
                                  encoder_label: str, input_size: int,
                                  output_size: int, final_status: str,
                                  download_filename: str,
                                  resp: BuildResponse):
        """Store the session log as a JSON artifact in Mythic."""
        log_base = os.path.splitext(download_filename)[0]
        log_json = session_log.to_json(
            payload_uuid=self.uuid,
            encoder_label=encoder_label,
            wrapped_payload_uuid=self.wrapped_payload_uuid or "",
            input_size=input_size,
            output_size=output_size,
            final_status=final_status,
        )
        await self._step("Registering", f"Storing session log ({len(log_json):,} chars)…", True)

        try:
            log_create = await SendMythicRPCFileCreate(MythicRPCFileCreateMessage(
                PayloadUUID=self.uuid,
                FileContents=log_json.encode("utf-8"),
                Filename=f"{log_base}.session.json",
                IsDownloadFromAgent=True,
                Comment=f"Dolos: session log | {encoder_label} | {input_size:,}→{output_size:,} bytes | {final_status}",
                DeleteAfterFetch=False,
            ))
            if log_create.Success:
                session_log.log_stored(
                    f"{log_base}.session.json",
                    log_create.AgentFileId,
                    len(log_json),
                )
            else:
                session_log.log_store_failed(log_create.Error or "unknown error")
        except Exception as e:
            session_log.log_store_failed(str(e))

        # Also store a human-readable text log for backwards compatibility
        summary = session_log.to_summary()
        try:
            await SendMythicRPCFileCreate(MythicRPCFileCreateMessage(
                PayloadUUID=self.uuid,
                FileContents=summary.encode("utf-8"),
                Filename=f"{log_base}.log",
                IsDownloadFromAgent=True,
                Comment=f"Dolos: summary log | {encoder_label} | {final_status}",
                DeleteAfterFetch=False,
            ))
        except Exception:
            pass  # Non-critical

    async def _step(self, step_name: str, message: str, success: bool):
        """Helper to update a build step."""
        await SendMythicRPCPayloadUpdatebuildStep(MythicRPCPayloadUpdateBuildStepMessage(
            PayloadUUID=self.uuid,
            StepName=step_name,
            StepStdout=message,
            StepSuccess=success,
        ))