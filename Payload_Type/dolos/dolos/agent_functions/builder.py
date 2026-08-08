"""Dolos - Mythic Wrapper PayloadType.

Dolos is a **wrapper** payload type. It takes an existing built payload (selected
via Mythic's native "Create Wrapper" flow), transfers it to an external server
over SSH/SFTP, runs an encoder command, and returns the transformed result.

The input payload bytes arrive as ``self.wrapped_payload`` - provided natively
by Mythic. No file-dropdown, no GraphQL file lookup, no monkey-patch needed.

Build parameters:
  - Encoder (ChooseOne from encoder profiles in configs/)
  - Bypass Profile (ChooseOne, shown only when encoder has bypass profiles)
  - Timeout (Number, 0 = use encoder profile default)
  - Regenerate Shellcode (Boolean, default True)

Success/fail strings come from the encoder profile JSON, not the UI.

SSH config, encoder commands, and bypass profiles are loaded from
encoder_profile.json files in the configs/ directory (mounted at
/Mythic/configs/ inside Docker).
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
from mythic_container.PayloadBuilder import (
    PTRPCDynamicQueryBuildParameterFunctionMessage,
    PTRPCDynamicQueryBuildParameterFunctionMessageResponse,
)

from dolos import config_loader
from dolos.config_loader import EncoderProfile
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
# Build parameter choices - loaded from config and refreshed on disk changes.
#
# Mythic's React frontend does NOT call dynamic_query_function for build
# parameters - it only uses it for command parameters (tasking). So we can't
# rely on dynamic queries for dropdown choices.
#
# Instead, we watch the config directory for changes (via mtime polling in
# main.py) and force a Mythic payload type re-sync when config changes.
# This makes the UI update its dropdown choices without a container restart.
# ---------------------------------------------------------------------------


async def _query_encoders(
    msg: PTRPCDynamicQueryBuildParameterFunctionMessage,
) -> PTRPCDynamicQueryBuildParameterFunctionMessageResponse:
    """Dynamic query callback for Encoder dropdown.

    Called by Mythic when the user opens the Encoder dropdown.
    Returns current enabled encoder labels from config.
    """
    choices = config_loader.get_encoder_choices()
    return PTRPCDynamicQueryBuildParameterFunctionMessageResponse(
        Success=True, Choices=choices
    )


async def _query_bypass_profiles(
    msg: PTRPCDynamicQueryBuildParameterFunctionMessage,
) -> PTRPCDynamicQueryBuildParameterFunctionMessageResponse:
    """Dynamic query callback for Bypass Profile dropdown.

    Called by Mythic when the user opens the Bypass Profile dropdown.
    Returns all enabled bypass profile choices plus (None).
    """
    choices = config_loader.get_all_bypass_choices()
    return PTRPCDynamicQueryBuildParameterFunctionMessageResponse(
        Success=True, Choices=choices
    )


def _update_build_params():
    """Re-read config and update build parameter choices on the PayloadType."""
    global _ENCODER_CHOICES, _BYPASS_CHOICES, _ENCODERS_WITH_BYPASS
    _ENCODER_CHOICES = config_loader.get_encoder_choices()
    _BYPASS_CHOICES = config_loader.get_all_bypass_choices()
    _ENCODERS_WITH_BYPASS = config_loader.get_encoders_with_bypass()
    # Update the class-level build parameter choices
    for param in Dolos.build_parameters:
        if param.name == "Encoder":
            param.choices = _ENCODER_CHOICES
        elif param.name == "Bypass Profile":
            param.choices = _BYPASS_CHOICES
            if _ENCODERS_WITH_BYPASS:
                param.hide_conditions = [
                    HideCondition(
                        name="Encoder",
                        operand=HideConditionOperand.NotIN,
                        choices=_ENCODERS_WITH_BYPASS,
                    )
                ]
            else:
                param.hide_conditions = []


_ENCODER_CHOICES = config_loader.get_encoder_choices()
_BYPASS_CHOICES = config_loader.get_all_bypass_choices()
_ENCODERS_WITH_BYPASS = config_loader.get_encoders_with_bypass()


# ---------------------------------------------------------------------------
# PayloadType definition - a Mythic wrapper
# ---------------------------------------------------------------------------

class Dolos(PayloadType):
    """
    Dolos - "The Craftsman of Lies" - a Mythic wrapper payload.

    Takes an existing built payload (shellcode, EXE, etc.), transfers it to an
    external server over SSH, runs an encoder command, and returns the result.
    The wrapped payload's C2 is already embedded - no C2 profile selection needed.
    """

    name = "dolos"
    file_extension = "bin"
    author = "@3mrgnc3"
    supported_os = ["SSH Server + Any OS"]
    wrapper = True
    wrapped_payloads = ["apollo", "merlin", "athena", "medusa", "hannibal", "freyja", "poopsie", "poseidon"]
    note = (
        f"Dolos v{_VERSION} | The Craftsman of Lies - wrap an existing payload, "
        "transfer it to an external server over SSH/SFTP, run an encoder "
        "(C# cradle, Donut, ShellcodePack, custom), and return the result. "
        "Built-in C# cradle encoder (csc.exe). Full session logging. "
        "Rotating file logs. Per-profile SSH config. See docs for setup."
    )
    supports_dynamic_loading = False
    mythic_encrypts = True
    translation_container = None
    agent_type = AgentType.Wrapper
    agent_path = pathlib.Path(".") / "dolos"
    _icon_path = pathlib.Path(__file__).parent.parent / "dolos.svg"
    agent_icon_bytes = _icon_path.read_bytes() if _icon_path.exists() else b""
    agent_code_path = agent_path / "agent_code"
    c2_profiles = []
    build_parameters = [
        BuildParameter(
            name="Encoder",
            parameter_type=BuildParameterType.ChooseOne,
            description=(
                "Select an encoder profile. Configured in dolos_profiles/encoders/ "
                "on the Mythic host. Each profile specifies SSH server, command "
                "template, and optional bypass profiles. Edit profiles on disk "
                "and reload takes effect immediately."
            ),
            choices=_ENCODER_CHOICES,
            dynamic_query_function=_query_encoders,
            group_name="Remote Command",
        ),
        BuildParameter(
            name="Bypass Profile",
            parameter_type=BuildParameterType.ChooseOne,
            description=(
                "Select a bypass profile for the chosen encoder. "
                "Only shown when the encoder has bypass profiles configured. "
                "Choose (None) to skip bypass."
            ),
            choices=_BYPASS_CHOICES,
            default_value="(None)",
            dynamic_query_function=_query_bypass_profiles,
            hide_conditions=[
                HideCondition(
                    name="Encoder",
                    operand=HideConditionOperand.NotIN,
                    choices=_ENCODERS_WITH_BYPASS,
                )
            ] if _ENCODERS_WITH_BYPASS else [],
            group_name="Remote Command",
        ),
        BuildParameter(
            name="Timeout",
            parameter_type=BuildParameterType.Number,
            description=(
                "Timeout in seconds for the remote command. "
                "Set to 0 to use the encoder profile's default timeout. "
"Overriding here is for one-off builds; to change the default, "
                "edit the encoder_profile.json on the server."
            ),
            default_value=0,
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
        BuildStep(step_name="Rebuilding", step_description="Auto-regenerating shellcode - inner payload already wrapped by Dolos"),
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
        bypass_display = (self.get_parameter("Bypass Profile") or "(None)").strip()
        timeout_override = int(self.get_parameter("Timeout") or 0)
        regenerate = self.get_parameter("Regenerate Shellcode") or False

        # ── Validate: wrapped payload must be present ──

        if not self.wrapped_payload:
            await self._step("Connecting", "No wrapped payload - select a payload to wrap", False)
            resp.build_message = "No wrapped payload. Select an existing payload in the Create Wrapper dialog."
            return resp

        if not encoder_label or encoder_label == "(no profiles configured)":
            await self._step("Connecting", "No encoder profile configured", False)
            resp.build_message = (
                "No encoder profiles configured. Edit configs/encoders/encoder_profile.json "
                "with your SSH server details and encoder command. See /docs/agents/dolos/setup for help."
            )
            return resp

        # ── Load encoder profile from config ──

        profile = config_loader.get_encoder_profile(encoder_label)
        if profile is None:
            await self._step("Connecting", f"Encoder profile '{encoder_label}' not found", False)
            resp.build_message = f"Encoder profile '{encoder_label}' not found. Check configs/encoders/ directory."
            return resp

        if not profile.valid:
            errors = "; ".join(profile.validation_errors)
            await self._step("Connecting", f"Encoder profile '{encoder_label}' is invalid: {errors}", False)
            resp.build_message = f"Encoder profile '{encoder_label}' is invalid: {errors}"
            return resp

        if not profile.enabled:
            await self._step("Connecting", f"Encoder profile '{encoder_label}' is disabled", False)
            resp.build_message = f"Encoder profile '{encoder_label}' is disabled. Enable it in encoder_profile.json or choose a different encoder."
            return resp

        # Determine timeout: use profile default unless overridden by build param
        timeout = timeout_override if timeout_override > 0 else profile.timeout
        success_string = profile.success_string
        failure_string = profile.fail_string

        # Determine bypass profile stem for command placeholder
        bypass_stem = ""
        if bypass_display and bypass_display != "(None)":
            bypass_stem = config_loader.get_bypass_stem_for_display(encoder_label, bypass_display) or ""

        await self._step("Connecting", f"Encoder: {encoder_label} | Input: {len(self.wrapped_payload):,} bytes | Timeout: {timeout}s", True)

        # ── Check: has this payload already been wrapped by Dolos? ──

        already_wrapped = await self._check_already_wrapped()
        if already_wrapped:
            if regenerate:
                logger.info(f"[DOLOS-BUILD] Inner payload {self.wrapped_payload_uuid} already has "
                            f"a successful Dolos build. Regenerate Shellcode enabled - "
                            f"rebuilding inner payload with new UUID.")
                rebuild_ok = await self._rebuild_inner_payload(already_wrapped)
                if not rebuild_ok:
                    await self._step("Rebuilding",
                        "Failed to regenerate shellcode - proceeding with original.",
                        False)
                # else: self.wrapped_payload and self.wrapped_payload_uuid are now updated
            else:
                logger.info(f"[DOLOS-BUILD] Inner payload {self.wrapped_payload_uuid} already has "
                            f"a successful Dolos build, but Regenerate Shellcode is OFF - "
                            f"proceeding with the same shellcode.")
                await self._step("Rebuilding",
                    f"Shellcode already wrapped - re-wrapping as-is (Regenerate Shellcode is OFF)",
                    True)

        payload_bytes = self.wrapped_payload
        payload_size = len(payload_bytes)
        logger.info(f"[DOLOS-BUILD] Input payload: {payload_size:,} bytes")

        # ── Resolve encoder command ──

        encoder_command = profile.command

        # ── Get SSH config from profile ──

        ssh_config = ssh_client.get_ssh_config_from_profile(profile)
        host = ssh_config["host"]
        port = ssh_config["port"]
        username = ssh_config["username"]
        ssh_password = ssh_config["password"]
        ssh_private_key = ssh_config["private_key"]
        auth_method = ssh_config["auth_method"]

        if not host:
            await self._step("Connecting", "SSH host not configured in encoder profile", False)
            resp.build_message = (
                "SSH host not configured. Edit the encoder profile's ssh_server.host "
                "in configs/encoders/. See /docs/agents/dolos/setup for help."
            )
            return resp

        if auth_method == "none":
            await self._step("Connecting", "No SSH auth configured in encoder profile", False)
            resp.build_message = (
                "No SSH auth method configured. Set ssh_server.password or enable "
                "ssh_server.keys in the encoder profile. See /docs/agents/dolos/setup for help."
            )
            return resp

        logger.info(f"[DOLOS-BUILD] SSH config: {username}@{host}:{port} auth={auth_method}")

        # ── Verify SSH connectivity (Step 1: Connecting) ──

        session_log.connecting(host, port, username)
        auth_desc = f"{auth_method}" if auth_method != "key+password" else "key+password"
        await self._step("Connecting", f"Connecting to {username}@{host}:{port} ({auth_desc})…", True)

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

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
            resp.build_message = (
                f"SSH connection failed: {e}. Check the encoder profile's "
                "ssh_server config in configs/encoders/."
            )
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
                f"✅ SSH ✅ Auth ✅ SFTP - connected to {remote_os}",
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

        # ── 3. Upload wrapped payload + supporting files (Step 3: Uploading) ──

        remote_filenames = {"input": "wd_in.bin"}
        files: list[tuple[str, bytes]] = [("wd_in.bin", payload_bytes)]
        total_size = payload_size
        cleanup_files: list[str] = []  # extra files to remove from workdir after download

        # Upload supporting files (bypass profiles, configs, etc.) from the
        # encoder profile's bypass_profiles directory. These are SFTP'd to the
        # remote workdir so the encoder command can reference them.
        # {bypass_profile} resolves to the stem filename (e.g. "cortex_bypass_profile"),
        # so the encoder command template can use it as: C:\tools\{bypass_profile}.json
        # or relative to workdir: {workdir}\\{bypass_profile}.json
        if bypass_stem and profile.bypass_profiles_path:
            bp_filename = f"{bypass_stem}.json"
            bp_local_path = os.path.join(profile.bypass_profiles_path, bp_filename)
            if os.path.isfile(bp_local_path):
                try:
                    with open(bp_local_path, "rb") as f:
                        bp_content = f.read()
                    files.append((bp_filename, bp_content))
                    total_size += len(bp_content)
                    cleanup_files.append(bp_filename)
                    remote_filenames["bypass_profile"] = bp_filename
                    logger.info(f"[DOLOS-BUILD] Added supporting file: {bp_filename} ({len(bp_content):,} bytes)")
                except IOError as e:
                    logger.warning(f"[DOLOS-BUILD] Could not read supporting file {bp_local_path}: {e}")
                    # Non-fatal: encoder command may reference an absolute path on the server
                    # instead of the workdir copy

        upload_start = time.time()
        file_list_str = ", ".join(f[0] for f in files)
        session_log.uploading_file(file_list_str, f"{workdir}/", total_size)
        await self._step("Uploading", f"Uploading {len(files)} file(s) ({total_size:,} bytes) to {workdir}", True)

        local_dir = tempfile.mkdtemp(prefix="dolos_")
        try:
            for filename, content in files:
                local_path = os.path.join(local_dir, filename)
                with open(local_path, "wb") as f:
                    f.write(content)
                sftp.put(local_path, workdir + "/" + filename)
            upload_elapsed = time.time() - upload_start
            session_log.upload_complete(file_list_str, total_size, upload_elapsed)
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

        # Resolve placeholders in the command template
        resolved_cmd = ssh_client.resolve_placeholders(
            encoder_command, workdir_cmd, remote_filenames,
            extra_placeholders={"output": "wd_out.bin", "bypass_profile": bypass_stem} if bypass_stem else {"output": "wd_out.bin"},
        )
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
            # Clean up supporting files (bypass profiles, etc.)
            for cpf in cleanup_files:
                try:
                    sftp.remove(workdir + "/" + cpf)
                    session_log.cleanup_file(workdir + "/" + cpf, True)
                except Exception as e:
                    session_log.cleanup_file(workdir + "/" + cpf, False, str(e))
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
                status_detail = f"Fail indicator '{failure_string}' found, but file exists - verify manually"
            else:
                status = "FAILURE"
                status_detail = f"Fail indicator '{failure_string}' found in output"
        elif exit_code != 0 and output_exists:
            status = "WARNING"
            status_detail = f"Command exited with code {exit_code} but output file exists - verify result"
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
            f"Status: {status} - {status_detail} | "
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

        resp.updated_filename = download_filename
        logger.info(f"[DOLOS-BUILD] updated_filename = {resp.updated_filename} (magic: {magic_type})")

        status_prefix = ""
        if status == "WARNING":
            status_prefix = f"⚠️ {status_detail}. "

        resp.status = BuildStatus.Success
        resp.payload = result_bytes  # lowercase! - the v0.5.1 lesson
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
    # Shellcode deduplication - check and rebuild
    # -----------------------------------------------------------------------

    async def _check_already_wrapped(self) -> dict | None:
        """Check if the inner payload already has a successful Dolos build.
        Returns dedup_info dict or None."""
        if not self.wrapped_payload_uuid:
            return None
        from dolos.hasura import HasuraClient
        return HasuraClient().check_already_wrapped(self.wrapped_payload_uuid)

    async def _get_task_id(self, operation_id: int) -> int | None:
        """Look up any TaskID in the given operation for MythicRPC scoping."""
        from dolos.hasura import HasuraClient
        return HasuraClient().get_task_id(operation_id)

    async def _rebuild_inner_payload(self, dedup_info: dict) -> bool:
        """Rebuild inner payload with same config but new UUID via MythicRPC.
        dedup_info: dict from _check_already_wrapped() with operation_id etc.
        Returns True if self.wrapped_payload was updated, False otherwise."""
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

        task_id = await self._get_task_id(dedup_info["operation_id"])
        if not task_id:
            logger.error("[DOLOS-BUILD] Cannot find a TaskID for operation scoping - rebuild failed")
            return False

        logger.info(f"[DOLOS-BUILD] Using TaskID {task_id} for operation {dedup_info['operation_id']}")

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

        max_wait = 300
        poll_interval = 2
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
                continue

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

        new_payload = poll_result.Payloads[0]
        if not new_payload.AgentFileId:
            logger.error("[DOLOS-BUILD] New payload has no AgentFileId - cannot fetch bytes")
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

        new_bytes = file_result.Content
        self.wrapped_payload = new_bytes
        self.wrapped_payload_uuid = new_uuid
        logger.info(f"[DOLOS-BUILD] Rebuilt inner payload: {new_uuid} ({len(new_bytes):,} bytes)")

        await self._step("Rebuilding",
            f"✅ Regenerated {inner_payload.PayloadType} payload ({len(new_bytes):,} bytes) - now wrapping new UUID",
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