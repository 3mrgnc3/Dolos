"""Dolos v2 - Mythic Wrapper PayloadType.

Wraps an existing payload, transfers via SSH/SFTP to an external encoder
server, runs the encoder command, returns the result.

Config: flat files in /Mythic/configs/ with NN_Type_Detail.ext naming.
SSH keys: resolved from Mythic User Secrets (self.secrets) with flat-file fallback.
Bypass refs: by filename (e.g. "00_Bypass_AMSI.json").
Tool files: matched by group number to encoder.
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

_CAPABILITIES_PATH = pathlib.Path(__file__).parent.parent / "agent_capabilities.json"
_VERSION = json.loads(_CAPABILITIES_PATH.read_text())["agent_version"]


async def _query_encoders(msg: PTRPCDynamicQueryBuildParameterFunctionMessage):
    choices = config_loader.get_encoder_choices()
    return PTRPCDynamicQueryBuildParameterFunctionMessageResponse(Success=True, Choices=choices)


async def _query_timeouts(msg: PTRPCDynamicQueryBuildParameterFunctionMessage):
    choices = []
    seen = set()
    for p in config_loader._ensure_loaded():
        if p.enabled and p.timeout not in seen:
            choices.append(str(p.timeout))
            seen.add(p.timeout)
    for t in [60, 120, 300, 600, 900, 1800]:
        if t not in seen:
            choices.append(str(t))
    return PTRPCDynamicQueryBuildParameterFunctionMessageResponse(
        Success=True, Choices=choices or ["300"]
    )


async def _query_bypass_profiles(msg: PTRPCDynamicQueryBuildParameterFunctionMessage):
    choices = config_loader.get_all_bypass_choices()
    return PTRPCDynamicQueryBuildParameterFunctionMessageResponse(Success=True, Choices=choices)


def _update_build_params():
    global _ENCODER_CHOICES, _BYPASS_CHOICES, _ENCODERS_WITH_BYPASS
    _ENCODER_CHOICES = config_loader.get_encoder_choices()
    _BYPASS_CHOICES = config_loader.get_all_bypass_choices()
    _ENCODERS_WITH_BYPASS = config_loader.get_encoders_with_bypass()

    _TIMEOUT_CHOICES = []
    _seen_timeouts = set()
    for p in config_loader._ensure_loaded():
        if p.enabled and p.timeout not in _seen_timeouts:
            _TIMEOUT_CHOICES.append(str(p.timeout))
            _seen_timeouts.add(p.timeout)
    for t in [60, 120, 300, 600, 900, 1800]:
        if t not in _seen_timeouts:
            _TIMEOUT_CHOICES.append(str(t))
    if not _TIMEOUT_CHOICES:
        _TIMEOUT_CHOICES = ["300"]

    for param in Dolos.build_parameters:
        if param.name == "Encoder":
            param.choices = _ENCODER_CHOICES
        elif param.name == "Timeout":
            param.choices = _TIMEOUT_CHOICES
        elif param.name == "Bypass Profile":
            param.choices = _BYPASS_CHOICES
            if _ENCODERS_WITH_BYPASS:
                param.hide_conditions = [HideCondition(
                    name="Encoder",
                    operand=HideConditionOperand.NotIN,
                    choices=_ENCODERS_WITH_BYPASS,
                )]
            else:
                param.hide_conditions = []


_ENCODER_CHOICES = config_loader.get_encoder_choices()
_BYPASS_CHOICES = config_loader.get_all_bypass_choices()
_ENCODERS_WITH_BYPASS = config_loader.get_encoders_with_bypass()


class Dolos(PayloadType):
    name = "dolos"
    file_extension = "bin"
    author = "@3mrgnc3"
    supported_os = ["SSH Server + Any OS"]
    wrapper = True
    wrapped_payloads = ["apollo", "merlin", "athena", "medusa", "hannibal", "freyja", "poopsie", "poseidon"]
    note = (
        f"Dolos v{_VERSION} | Wrapper payload — transfer to SSH server, run encoder, return result. "
        f"Config via paperclip-editable flat files in /Mythic/configs/. "
        f"SSH keys via User Settings → Secrets."
    )
    supports_dynamic_loading = False
    mythic_encrypts = True
    translation_container = None
    agent_type = AgentType.Wrapper
    agent_path = pathlib.Path(".") / "dolos"
    _icon_path = pathlib.Path(__file__).parent.parent / "dolos.svg"
    agent_icon_bytes = _icon_path.read_bytes() if _icon_path.exists() else b""
    c2_profiles = []

    build_parameters = [
        BuildParameter(
            name="Encoder",
            parameter_type=BuildParameterType.ChooseOne,
            description=(
                "Select an encoder profile. Configured via flat files in /Mythic/configs/ "
                "(paperclip-editable). Each profile specifies SSH server, command, bypass refs. "
                "Edits take effect without restart."
            ),
            choices=_ENCODER_CHOICES,
            dynamic_query_function=_query_encoders,
            group_name="Remote Command",
        ),
        BuildParameter(
            name="Bypass Profile",
            parameter_type=BuildParameterType.ChooseOne,
            description=(
                "Select a bypass profile for the chosen encoder. Only shown when encoder has bypass refs."
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
            parameter_type=BuildParameterType.ChooseOneCustom,
            description="Timeout in seconds for the remote encoder command.",
            choices=["300"],
            default_value="300",
            dynamic_query_function=_query_timeouts,
            required=False,
            group_name="Remote Command",
        ),
        BuildParameter(
            name="Regenerate Shellcode",
            parameter_type=BuildParameterType.Boolean,
            description=(
                "If the inner payload already has a Dolos build, auto-regenerate with new UUID."
            ),
            default_value=True,
            required=False,
            group_name="Deduplication",
        ),
    ]

    build_steps = [
        BuildStep(step_name="Rebuilding", step_description="Auto-regenerating shellcode"),
        BuildStep(step_name="Connecting", step_description="Verifying SSH connectivity and auth"),
        BuildStep(step_name="Preparing", step_description="Creating workdir and installing tools"),
        BuildStep(step_name="Uploading", step_description="Sending payload to remote server"),
        BuildStep(step_name="Processing", step_description="Running encoder command"),
        BuildStep(step_name="Retrieving", step_description="Downloading result from remote server"),
        BuildStep(step_name="Cleaning", step_description="Removing remote workdir"),
        BuildStep(step_name="Validating", step_description="Checking result integrity"),
        BuildStep(step_name="Registering", step_description="Storing session log and build result"),
    ]

    async def build(self) -> BuildResponse:
        resp = BuildResponse(status=BuildStatus.Error)
        session_log = SSHSessionLog()

        logger.critical("[DOLOS-BUILD] ========== build() START ==========")

        # ── 1. Collect build params ──
        encoder_label = (self.get_parameter("Encoder") or "").strip()
        bypass_display = (self.get_parameter("Bypass Profile") or "(None)").strip()
        timeout_override_raw = self.get_parameter("Timeout") or "0"
        timeout_override = int(timeout_override_raw) if timeout_override_raw else 0
        regenerate = self.get_parameter("Regenerate Shellcode") or False

        # ── Validate wrapped payload ──
        if not self.wrapped_payload:
            await self._step("Connecting", "No wrapped payload — select a payload to wrap", False)
            resp.build_message = "No wrapped payload. Select an existing payload in the Create Wrapper dialog."
            return resp

        if not encoder_label or encoder_label == "(no profiles configured)":
            await self._step("Connecting", "No encoder profile configured", False)
            resp.build_message = (
                "No encoder profiles configured. Create NN_Encoder_Label.json files "
                "in /Mythic/configs/ via the paperclip UI. See Dolos docs for format."
            )
            return resp

        # ── Load encoder profile ──
        profile = config_loader.get_encoder_profile(encoder_label)
        if profile is None:
            await self._step("Connecting", f"Encoder '{encoder_label}' not found", False)
            resp.build_message = f"Encoder '{encoder_label}' not found in configs."
            return resp

        if not profile.valid:
            errors = "; ".join(profile.validation_errors)
            await self._step("Connecting", f"Encoder '{encoder_label}' invalid: {errors}", False)
            resp.build_message = f"Encoder '{encoder_label}' invalid: {errors}"
            return resp

        if not profile.enabled:
            await self._step("Connecting", f"Encoder '{encoder_label}' disabled", False)
            resp.build_message = f"Encoder '{encoder_label}' is disabled. Enable it in the config."
            return resp

        timeout = timeout_override if timeout_override > 0 else profile.timeout
        success_string = profile.success_string
        failure_string = profile.fail_string

        # ── Resolve SSH key from Mythic User Secrets ──
        ssh_key_content = config_loader.resolve_ssh_key(profile, self.secrets)

        # ── Resolve bypass profile filename ──
        bypass_filename = None
        if bypass_display and bypass_display != "(None)":
            bypass_filename = config_loader.get_bypass_filename_for_display(encoder_label, bypass_display)

        await self._step("Connecting",
            f"Encoder: {encoder_label} | Input: {len(self.wrapped_payload):,} bytes | Timeout: {timeout}s",
            True)

        # ── Check deduplication ──
        already_wrapped = await self._check_already_wrapped()
        if already_wrapped:
            if regenerate:
                rebuild_ok = await self._rebuild_inner_payload(already_wrapped)
                if not rebuild_ok:
                    await self._step("Rebuilding", "Failed to regenerate — proceeding with original", False)
            else:
                await self._step("Rebuilding", "Already wrapped — re-wrapping as-is (Regenerate is OFF)", True)

        payload_bytes = self.wrapped_payload
        payload_size = len(payload_bytes)

        # ── SSH connection ──
        host = profile.host
        port = profile.port
        username = profile.username
        ssh_password = profile.password

        has_key = bool(ssh_key_content)
        has_pass = bool(ssh_password)
        if has_key and has_pass:
            auth_method = "key+password"
        elif has_key:
            auth_method = "key"
        elif has_pass:
            auth_method = "password"
        else:
            auth_method = "none"

        if not host:
            await self._step("Connecting", "ssh_host not configured", False)
            resp.build_message = "ssh_host is required in encoder profile."
            return resp

        if auth_method == "none":
            await self._step("Connecting", "No SSH auth configured", False)
            resp.build_message = (
                "No SSH auth. Set ssh_password or enable ssh_key_enabled with a "
                "Mythic User Secret (User Settings → Secrets)."
            )
            return resp

        logger.info(f"[DOLOS-BUILD] SSH: {username}@{host}:{port} auth={auth_method}")
        session_log.connecting(host, port, username)

        await self._step("Connecting", f"Connecting to {username}@{host}:{port} ({auth_method})…", True)

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            connect_kwargs = dict(
                hostname=host, port=port, username=username,
                timeout=20, allow_agent=False, look_for_keys=False,
            )
            if has_key:
                pkey = ssh_client._load_private_key(ssh_key_content)
                connect_kwargs["pkey"] = pkey
                if has_pass:
                    connect_kwargs["password"] = ssh_password
            elif has_pass:
                connect_kwargs["password"] = ssh_password

            client.connect(**connect_kwargs)
            logger.info(f"[DOLOS-BUILD] SSH connected to {host}:{port} via {auth_method}")
        except Exception as e:
            session_log.connection_failed(str(e))
            await self._step("Connecting", f"SSH connection failed: {e}", False)
            resp.build_message = f"SSH connection failed: {e}"
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
                await self._step("Connecting", f"SSH ✅ Auth ✅ SFTP ❌ {sftp_msg}", False)
                resp.build_message = f"SFTP write test failed: {sftp_msg}"
                client.close()
                return resp
            await self._step("Connecting", f"✅ SSH ✅ Auth ✅ SFTP — {remote_os}", True)
        except Exception as e:
            session_log.connection_failed(str(e))
            await self._step("Connecting", f"Connection verification failed: {e}", False)
            resp.build_message = f"Connection verification failed: {e}"
            if client:
                client.close()
            return resp

        # ── Prepare workdir ──
        workdir_name = ssh_client.generate_workdir_name()
        workdir_root = ssh_client._workdir_root(remote_os)
        workdir = workdir_root + "/" + workdir_name
        workdir_cmd = workdir.replace("/", "\\") if remote_os == "windows" else workdir

        session_log.creating_workdir(workdir, remote_os)
        await self._step("Preparing", f"Creating workdir: {workdir}", True)

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

        # ── Upload payload + supporting files ──
        remote_filenames = {"input": "wd_in.bin"}
        files: list[tuple[str, bytes]] = [("wd_in.bin", payload_bytes)]
        total_size = payload_size
        cleanup_files: list[str] = []

        # Upload bypass profile if selected (flat file from CONFIG_DIR)
        if bypass_filename:
            bp_path = os.path.join(config_loader.CONFIG_DIR, bypass_filename)
            if os.path.isfile(bp_path):
                try:
                    with open(bp_path, "rb") as f:
                        bp_content = f.read()
                    bp_name = bypass_filename  # use the flat filename
                    files.append((bp_name, bp_content))
                    total_size += len(bp_content)
                    cleanup_files.append(bp_name)
                    remote_filenames["bypass_profile"] = bp_name
                    logger.info(f"[DOLOS-BUILD] Added bypass file: {bp_name} ({len(bp_content):,} bytes)")
                except IOError as e:
                    logger.warning(f"[DOLOS-BUILD] Could not read bypass file {bp_path}: {e}")

        # Upload tool files for this encoder's group
        tool_files = config_loader.get_tool_files(encoder_label) if profile.install_tools else []
        install_script = config_loader.get_install_script(encoder_label, remote_os) if profile.install_tools else None

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

        # ── Install tools on remote ──
        if install_script or tool_files:
            await self._step("Preparing", f"Installing tools on {remote_os}…", True)

            # Upload tool files to workdir
            for tool_file in tool_files:
                tool_filename = os.path.basename(tool_file)
                if install_script and os.path.abspath(tool_file) == os.path.abspath(install_script):
                    continue  # uploaded separately
                try:
                    sftp.put(tool_file, workdir + "/" + tool_filename)
                    cleanup_files.append(tool_filename)
                    logger.info(f"[DOLOS-BUILD] Uploaded tool: {tool_filename}")
                except Exception as e:
                    logger.warning(f"[DOLOS-BUILD] Failed to upload tool {tool_filename}: {e}")

            # Run install script
            if install_script:
                install_script_name = os.path.basename(install_script)
                remote_install_path = workdir + "/" + install_script_name
                try:
                    sftp.put(install_script, remote_install_path)
                    cleanup_files.append(install_script_name)

                    if remote_os == "windows":
                        install_cmd = f'powershell.exe -ExecutionPolicy Bypass -File "{workdir_cmd}\\{install_script_name}"'
                    else:
                        install_cmd = f'chmod +x "{workdir}/{install_script_name}" && "{workdir}/{install_script_name}"'

                    logger.info(f"[DOLOS-BUILD] Running install: {install_cmd[:200]}")
                    session_log.running_command(install_cmd)

                    _stdin, install_stdout, install_stderr = client.exec_command(install_cmd, timeout=600)
                    install_exit = install_stdout.channel.recv_exit_status()
                    install_out = install_stdout.read().decode("utf-8", "replace")
                    install_err = install_stderr.read().decode("utf-8", "replace")

                    logger.info(f"[DOLOS-BUILD] Install exit: {install_exit}")
                    if install_out:
                        for line in install_out.splitlines():
                            session_log.command_stdout(line)
                    if install_err:
                        for line in install_err.splitlines():
                            session_log.command_stderr(line)

                    if install_exit != 0:
                        await self._step("Preparing", f"Install failed (exit {install_exit}): {install_err[:200]}", False)
                        resp.build_message = f"Tool install failed (exit {install_exit}): {install_err[:300]}"
                        try:
                            for f in cleanup_files:
                                sftp.remove(workdir + "/" + f)
                        except Exception:
                            pass
                        client.close()
                        return resp

                    await self._step("Preparing", f"✅ Tools installed on {remote_os}", True)
                except Exception as e:
                    await self._step("Preparing", f"Install failed: {e}", False)
                    resp.build_message = f"Tool install failed: {e}"
                    try:
                        for f in cleanup_files:
                            sftp.remove(workdir + "/" + f)
                    except Exception:
                        pass
                    client.close()
                    return resp
            else:
                logger.info("[DOLOS-BUILD] No install script for this OS — skipping")

        # ── Also upload the encoder script itself if install_tools is true ──
        # For PyEncoder, the 00_Tool_pyencoder_encode.py gets SFTP'd to workdir
        # and the install script copies it to C:\tools\dolos\encoder.py
        if profile.install_tools and tool_files:
            for tf in tool_files:
                tf_name = os.path.basename(tf)
                # The install script handles its own upload; encoder.py is uploaded separately
                # Check if this is the encoder script (matches *_encode.py or *.py pattern)
                if tf_name.endswith("_encode.py") or tf_name == "encoder.py":
                    try:
                        sftp.put(tf, workdir + "/" + tf_name)
                        cleanup_files.append(tf_name)
                        logger.info(f"[DOLOS-BUILD] Uploaded encoder script: {tf_name}")
                    except Exception as e:
                        logger.warning(f"[DOLOS-BUILD] Failed to upload {tf_name}: {e}")
        else:
            logger.info(f"[DOLOS-BUILD] No tool install configured for '{encoder_label}'")

        # ── Run encoder command ──
        encoder_command = profile.command

        # Resolve placeholders
        extra_placeholders = {"output": "wd_out.bin"}
        if bypass_filename:
            # bypass_profile resolves to the filename stem (without .json)
            bp_stem = os.path.splitext(bypass_filename)[0]
            extra_placeholders["bypass_profile"] = bp_stem

        resolved_cmd = ssh_client.resolve_placeholders(
            encoder_command, workdir_cmd, remote_filenames,
            extra_placeholders=extra_placeholders,
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
            await self._step("Processing", f"Command failed: {e}", False)
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

        # ── Retrieve output ──
        output_path = workdir + "/wd_out.bin"
        result_bytes = b""
        output_exists = False

        try:
            session_log.downloading_result(output_path)
            with sftp.open(output_path, "rb") as f:
                result_bytes = f.read()
                output_exists = True
            session_log.result_downloaded(output_path, len(result_bytes))
            logger.info(f"[DOLOS-BUILD] Retrieved {len(result_bytes)} bytes")
            await self._step("Retrieving", f"Downloaded {len(result_bytes):,} bytes", True)
        except IOError:
            session_log.result_missing(output_path)
            await self._step("Retrieving", "Output file not found", False)

        # ── Clean up ──
        try:
            for filename, _ in files:
                try:
                    sftp.remove(workdir + "/" + filename)
                except Exception:
                    pass
            for cpf in cleanup_files:
                try:
                    sftp.remove(workdir + "/" + cpf)
                except Exception:
                    pass
            if output_exists:
                try:
                    sftp.remove(output_path)
                except Exception:
                    pass
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

        # ── Validate ──
        magic_type = ssh_client.detect_file_magic(result_bytes) if result_bytes else "missing"
        session_log.magic_detected(magic_type, len(result_bytes))

        status = "SUCCESS"
        status_detail = ""
        success_indicated = success_string and success_string in out
        failure_indicated = failure_string and (failure_string in out or failure_string in err)

        if exit_code != 0 and not output_exists:
            status = "FAILURE"
            status_detail = f"Command failed (exit {exit_code}) and no output"
        elif failure_indicated:
            status = "WARNING" if output_exists else "FAILURE"
            status_detail = f"Fail indicator '{failure_string}' found"
        elif exit_code != 0 and output_exists:
            status = "WARNING"
            status_detail = f"Exit {exit_code} but output exists"
        elif not output_exists:
            status = "FAILURE"
            status_detail = "No output file produced"
        elif success_indicated:
            status = "SUCCESS"
            status_detail = "Success confirmed"
        else:
            status = "SUCCESS"
            status_detail = "Command completed"

        session_log.validating(status, status_detail, exit_code, payload_size, len(result_bytes),
                               magic_type, success_string if success_indicated else "",
                               failure_string if failure_indicated else "")

        validating_msg = f"{status}: {status_detail} | exit={exit_code} | {magic_type} | {payload_size:,}→{len(result_bytes):,}B"
        await self._step("Validating", validating_msg, status != "FAILURE")

        if status == "FAILURE":
            fail_filename = self.filename or "dolos_output.exe"
            await self._store_session_log(session_log, encoder_label, payload_size,
                                          len(result_bytes), status, fail_filename, resp)
            resp.build_message = f"{status}: {status_detail}\nstdout: {out[:500]}\nstderr: {err[:500]}"
            resp.build_stderr = f"{status}: {status_detail}"
            return resp

        # ── Build result ──
        result_filename = self.filename or "dolos_output.exe"
        base = os.path.splitext(result_filename)[0]
        ext_map = {"PE/EXE": ".exe", "DLL": ".dll", "ELF": ".elf", "MACHO": ".macho", "ZIP": ".zip", "JSON": ".json"}
        result_ext = ext_map.get(magic_type, os.path.splitext(result_filename)[1] or ".bin")
        download_filename = f"{base}{result_ext}"

        await self._store_session_log(session_log, encoder_label, payload_size,
                                      len(result_bytes), status, download_filename, resp)

        logger.info(f"[DOLOS-BUILD] Setting payload = {len(result_bytes)} bytes")
        resp.updated_filename = download_filename
        resp.status = BuildStatus.Success
        resp.payload = result_bytes
        status_prefix = f"⚠️ {status_detail}. " if status == "WARNING" else ""
        resp.build_message = (
            f"{status_prefix}Wrapped {payload_size:,} → {len(result_bytes):,} bytes ({magic_type}) "
            f"via {encoder_label}. Download: {resp.updated_filename}"
        )
        resp.build_stdout = out
        resp.build_stderr = err if status != "SUCCESS" else ""

        logger.critical(f"[DOLOS-BUILD] ========== build() COMPLETE, {len(result_bytes)} bytes ==========")
        return resp

    async def _check_already_wrapped(self) -> dict | None:
        if not self.wrapped_payload_uuid:
            return None
        from dolos.hasura import HasuraClient
        return HasuraClient().check_already_wrapped(self.wrapped_payload_uuid)

    async def _get_task_id(self, operation_id: int) -> int | None:
        from dolos.hasura import HasuraClient
        return HasuraClient().get_task_id(operation_id)

    async def _rebuild_inner_payload(self, dedup_info: dict) -> bool:
        try:
            inner_search = await SendMythicRPCPayloadSearch(
                MythicRPCPayloadSearchMessage(PayloadUUID=self.wrapped_payload_uuid))
        except Exception as e:
            logger.error(f"[DOLOS-BUILD] Failed to search inner payload: {e}")
            return False

        if not inner_search.Success or not inner_search.Payloads:
            logger.error(f"[DOLOS-BUILD] Inner payload not found: {inner_search.Error}")
            return False

        inner_payload = inner_search.Payloads[0]
        await self._step("Rebuilding",
            f"Rebuilding {inner_payload.PayloadType} payload (new UUID)…", True)

        task_id = await self._get_task_id(dedup_info["operation_id"])
        if not task_id:
            logger.error("[DOLOS-BUILD] Cannot find TaskID — rebuild failed")
            return False

        from mythic_container.MythicGoRPC.send_mythic_rpc_payload_create_from_scratch import (
            MythicRPCPayloadConfiguration as CreateConfig,
            MythicRPCPayloadConfigurationC2Profile as CreateC2,
            MythicRPCPayloadConfigurationBuildParameter as CreateBuildParam,
        )

        c2_profiles = [CreateC2(**p.to_json()) for p in (inner_payload.C2Profiles or [])]
        build_params = [CreateBuildParam(**p.to_json()) for p in (inner_payload.BuildParameters or [])]

        new_config = CreateConfig(
            Description=f"Auto-rebuilt for Dolos (from {inner_payload.Description or inner_payload.Filename})",
            PayloadType=inner_payload.PayloadType,
            C2Profiles=c2_profiles,
            BuildParameters=build_params,
            Commands=inner_payload.Commands,
            SelectedOS=inner_payload.SelectedOS,
            Filename=inner_payload.Filename,
        )

        try:
            create_result = await SendMythicRPCPayloadCreateFromScratch(
                MythicRPCPayloadCreateFromScratchMessage(TaskID=task_id, PayloadConfiguration=new_config))
        except Exception as e:
            logger.error(f"[DOLOS-BUILD] Failed to create inner payload: {e}")
            return False

        if not create_result.Success:
            logger.error(f"[DOLOS-BUILD] Inner rebuild failed: {create_result.Error}")
            return False

        new_uuid = create_result.NewPayloadUUID
        max_wait = 300
        elapsed = 0
        build_phase = ""

        await self._step("Rebuilding", f"Waiting for {inner_payload.PayloadType} build…", True)

        while elapsed < max_wait:
            await asyncio.sleep(2)
            elapsed += 2
            try:
                poll_result = await SendMythicRPCPayloadSearch(
                    MythicRPCPayloadSearchMessage(PayloadUUID=new_uuid))
            except Exception:
                continue
            if not poll_result.Success or not poll_result.Payloads:
                continue
            build_phase = poll_result.Payloads[0].BuildPhase
            if build_phase == "success":
                break
            elif build_phase == "error":
                return False

        if build_phase != "success":
            logger.error(f"[DOLOS-BUILD] Inner rebuild timed out ({max_wait}s, phase={build_phase})")
            return False

        new_payload = poll_result.Payloads[0]
        if not new_payload.AgentFileId:
            logger.error("[DOLOS-BUILD] New payload has no AgentFileId")
            return False

        try:
            file_result = await SendMythicRPCFileGetContent(
                MythicRPCFileGetContentMessage(AgentFileID=new_payload.AgentFileId))
        except Exception as e:
            logger.error(f"[DOLOS-BUILD] Failed to fetch new payload bytes: {e}")
            return False

        if not file_result.Success:
            logger.error(f"[DOLOS-BUILD] Failed to get payload content: {file_result.Error}")
            return False

        self.wrapped_payload = file_result.Content
        self.wrapped_payload_uuid = new_uuid
        await self._step("Rebuilding",
            f"✅ Regenerated {inner_payload.PayloadType} ({len(self.wrapped_payload):,} bytes)", True)
        return True

    async def _store_session_log(self, session_log, encoder_label, input_size,
                                  output_size, final_status, download_filename, resp):
        log_base = os.path.splitext(download_filename)[0]
        log_json = session_log.to_json(
            payload_uuid=self.uuid, encoder_label=encoder_label,
            wrapped_payload_uuid=self.wrapped_payload_uuid or "",
            input_size=input_size, output_size=output_size, final_status=final_status,
        )
        await self._step("Registering", f"Storing session log ({len(log_json):,} chars)…", True)
        try:
            log_create = await SendMythicRPCFileCreate(MythicRPCFileCreateMessage(
                PayloadUUID=self.uuid,
                FileContents=log_json.encode("utf-8"),
                Filename=f"{log_base}.session.json",
                IsDownloadFromAgent=True,
                Comment=f"Dolos: {encoder_label} | {input_size:,}→{output_size:,}B | {final_status}",
                DeleteAfterFetch=False,
            ))
            if log_create.Success:
                session_log.log_stored(f"{log_base}.session.json", log_create.AgentFileId, len(log_json))
            else:
                session_log.log_store_failed(log_create.Error or "unknown")
        except Exception as e:
            session_log.log_store_failed(str(e))

        summary = session_log.to_summary()
        try:
            await SendMythicRPCFileCreate(MythicRPCFileCreateMessage(
                PayloadUUID=self.uuid,
                FileContents=summary.encode("utf-8"),
                Filename=f"{log_base}.log",
                IsDownloadFromAgent=True,
                Comment=f"Dolos: {encoder_label} | {final_status}",
                DeleteAfterFetch=False,
            ))
        except Exception:
            pass

    async def _step(self, step_name: str, message: str, success: bool):
        await SendMythicRPCPayloadUpdatebuildStep(MythicRPCPayloadUpdateBuildStepMessage(
            PayloadUUID=self.uuid,
            StepName=step_name,
            StepStdout=message,
            StepSuccess=success,
        ))