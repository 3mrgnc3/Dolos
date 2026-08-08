# DEMO and TEST Encoder Tools for Remote Server

Deploy these to `C:\tools\` on the Windows remote server.

## encoder.py (C# cradle - primary shellcode→EXE encoder)

**Version: v2.3** - Uses CreateThread instead of delegate invocation.

Takes raw shellcode and produces a standalone x64 Windows PE executable using C# + csc.exe.

- Embeds shellcode via `.resources` (handles payloads >1MB)
- Uses `CreateThread` to run shellcode in a native thread (v2.3 fix - avoids CLR delegate interference)
- PE pass-through: if input is already a PE (MZ header), copies unchanged
- Outputs `ENCODING_SUCCESS:<input_size>:<output_size>:<type>` or `ENCODING_FAILED:<reason>`
- Validated with ~11MB Merlin shellcode: produces working EXE, shellcode executes via CreateThread

**Deploy:** Copy `encoder.py` to `C:\tools\encoder.py`
**Run:** `py.exe C:\tools\encoder.py <input> <output>`
**Requires:** `py.exe` in PATH, `csc.exe` at `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe` (built into Windows)
**Output:** Requires .NET Framework 4.x on the target machine (standard on Windows 10/11)

## passthrough_encoder.py (pipeline test encoder)

Copies input to output unchanged. Use only for testing the Dolos transfer pipeline
(upload → command → download → store) without doing any actual encoding.

- Detects and reports file type (PE/EXE, DLL, shellcode, ZIP, ELF)
- Same `ENCODING_SUCCESS/FAILED` output format as the real encoder

**Deploy:** Copy `passthrough_encoder.py` to `C:\tools\passthrough_encoder.py`
**Run:** `py.exe C:\tools\passthrough_encoder.py <input> <output>`

## donut.exe (EXE/DLL → shellcode converter)

**Direction: EXE → shellcode** (the OPPOSITE of encoder.py). Takes a PE executable and converts
it to position-independent shellcode. Useful for converting EXEs to shellcode format, not for
wrapping shellcode into an EXE.

**Deploy:** `donut.exe` to `C:\tools\donut.exe`
**Run:** `C:\tools\donut.exe -i <input.exe> -o <output.bin> -f 1`

## shellcode_test.py (testing harness)

Quick shellcode test harness. Reads a .bin file and executes it in memory via VirtualAlloc +
CreateThread with a configurable timeout. For verifying encoded shellcode works on the target.

**Deploy:** Copy `shellcode_test.py` to `C:\tools\shellcode_test.py`
**Run:** `py.exe C:\tools\shellcode_test.py <shellcode.bin> [timeout_seconds]`

**Warning:** Only run on test/development machines. Executes arbitrary shellcode.

