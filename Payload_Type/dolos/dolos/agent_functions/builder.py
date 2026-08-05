"""Dolos — Mythic Wrapper PayloadType (v0.9.0).

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

import json
import logging
import os
import pathlib
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

Version = "0.9.0"


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
    file_extension = "exe"
    author = "@3mrgnc3"
    supported_os = [SupportedOS.Windows]
    wrapper = True
    # Payload types Dolos can wrap. Listed on the wrapper side because we can't
    # modify each agent's code to list Dolos. Mythic's sync deletion is commented
    # out, so these relationships persist. Add new agents here + reinstall.
    wrapped_payloads = ["apollo", "merlin", "athena", "medusa", "hannibal", "freyja", "poopsie", "poseidon"]
    note = (
        "Dolos v0.9.0 | The Craftsman of Lies — wrap an existing payload, "
        "transfer it to an external server over SSH/SFTP, run an encoder "
        "(C# cradle, Donut, ShellcodePack, custom), and return the result. "
        "Built-in C# cradle encoder (csc.exe). Full session logging. "
        "See docs for setup."
    )
    supports_dynamic_loading = False
    mythic_encrypts = True
    translation_container = None
    agent_type = AgentType.Wrapper
    agent_path = pathlib.Path(".") / "dolos"
    agent_icon_path = agent_path / "agent_functions" / "dolos.svg"
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
    ]
    build_steps = [
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
        logger.critical(f"[DOLOS-BUILD] wrapped_payload_uuid={self.wrapped_payload_uuid}")
        logger.critical(f"[DOLOS-BUILD] wrapped_payload size={len(self.wrapped_payload) if self.wrapped_payload else 0} bytes")
        logger.critical(f"[DOLOS-BUILD] filename={self.filename}")

        # ── 1. Collect build parameters ──

        encoder_label = (self.get_parameter("Encoder") or "").strip()
        timeout = int(self.get_parameter("Timeout") or 300)
        success_string = (self.get_parameter("Success String") or "").strip()
        failure_string = (self.get_parameter("Fail String") or "").strip()

        # ── Validate: wrapped payload must be present ──

        if not self.wrapped_payload:
            await self._step("Connecting", "No wrapped payload — select a payload to wrap", False)
            resp.build_message = "No wrapped payload. Select an existing payload in the Create Wrapper dialog."
            return resp

        if not encoder_label:
            await self._step("Connecting", "No encoder selected", False)
            resp.build_message = "Encoder is required — select an encoder command from the dropdown"
            return resp

        payload_bytes = self.wrapped_payload
        payload_size = len(payload_bytes)
        logger.critical(f"[DOLOS-BUILD] Input payload: {payload_size:,} bytes")

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

        logger.critical(f"[DOLOS-BUILD] SSH config: {username}@{host}:{port} auth={auth_method}")

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
            logger.critical(f"[DOLOS-BUILD] SSH connected to {host}:{port} via {auth_method}")
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
        logger.critical(f"[DOLOS-BUILD] Running encoder: {resolved_cmd[:200]}")

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
            logger.critical(f"[DOLOS-BUILD] Retrieved {len(result_bytes)} bytes from remote")
            await self._step("Retrieving", f"Downloaded {len(result_bytes):,} bytes from {output_path}", True)
        except IOError:
            session_log.result_missing(output_path)
            logger.critical(f"[DOLOS-BUILD] Output file NOT found at {output_path}")
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

        logger.critical(f"[DOLOS-BUILD] Setting resp.payload = {len(result_bytes)} bytes")

        # Set a descriptive download filename based on detected output type.
        # Without this, Mythic uses the default (e.g., "dolos.exe") regardless
        # of actual content. With magic detection, a DLL gets .dll, etc.
        resp.updated_filename = download_filename
        logger.critical(f"[DOLOS-BUILD] updated_filename = {resp.updated_filename} (magic: {magic_type})")

        status_prefix = ""
        if status == "WARNING":
            status_prefix = f"⚠️ {status_detail}. "

        resp.status = BuildStatus.Success
        resp.payload = result_bytes  # lowercase! — the v0.5.1 lesson
        logger.critical(f"[DOLOS-BUILD] resp.payload set, get_payload() = {len(resp.get_payload())} bytes")
        resp.build_message = (
            f"{status_prefix}Wrapped {payload_size:,} → {len(result_bytes):,} bytes ({magic_type}) "
            f"via {encoder_label}. Download: {resp.updated_filename}"
        )
        resp.build_stdout = out
        resp.build_stderr = err if status != "SUCCESS" else ""

        logger.critical(f"[DOLOS-BUILD] ========== build() COMPLETE, returning {len(result_bytes)} bytes ==========")
        return resp

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