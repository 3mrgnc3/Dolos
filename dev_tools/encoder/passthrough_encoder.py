#!/usr/bin/env python3
"""
Dolos Passthrough Encoder — for pipeline testing only.

Copies input to output unchanged. Validates that the input is a valid file
and reports size. Use this to verify the Dolos transfer pipeline
(upload → run command → download → store in Mythic) works end-to-end.

For real encoding, deploy encoder.py (C# cradle) or a proprietary encoder.

Usage: passthrough_encoder.py <input_path> <output_path>

Output format (stdout, parseable by Dolos builder):
  ENCODING_SUCCESS:<input_size>:<output_size>:<type_info>
  ENCODING_FAILED:<reason>
"""

import sys
import os
import shutil
import struct
from datetime import datetime, timezone


def log(level, msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prefix = {"*": "*", "+": "+", "-": "-", "!": "!"}.get(level, "*")
    print("[{}] [{}] {}".format(ts, prefix, msg), flush=True)


def detect_type(data):
    if len(data) < 2:
        return "empty"
    if data[:2] == b"MZ":
        if len(data) >= 64:
            try:
                pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
                if pe_offset + 6 <= len(data):
                    machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
                    if machine == 0x8664:
                        return "PE/EXE->AMD64"
                    if machine == 0x14C:
                        return "PE/EXE->i386"
            except Exception:
                pass
        return "PE/EXE"
    if data[:2] == b"PK":
        return "ZIP"
    if len(data) >= 4 and data[:4] == b"\x7fELF":
        return "ELF"
    return "shellcode(0x{})".format(data[:4].hex() if len(data) >= 4 else data[:2].hex())


def main():
    if len(sys.argv) != 3:
        log("!", "Usage: passthrough_encoder.py <input_path> <output_path>")
        print("ENCODING_FAILED:invalid arguments")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    if not os.path.isfile(input_path):
        log("!", "Input file not found: {}".format(input_path))
        print("ENCODING_FAILED:input file not found")
        sys.exit(1)

    input_size = os.path.getsize(input_path)
    if input_size == 0:
        log("!", "Input file is empty")
        print("ENCODING_FAILED:input file is empty")
        sys.exit(1)

    log("*", "Passthrough encoder v1.0")
    log("*", "Input: {} ({} bytes)".format(input_path, input_size))

    # Read input
    with open(input_path, "rb") as f:
        data = f.read()

    file_type = detect_type(data)
    log("*", "Detected type: {}".format(file_type))

    # Copy to output unchanged
    shutil.copy2(input_path, output_path)
    output_size = os.path.getsize(output_path)

    log("+", "Output: {} ({} bytes, {})".format(output_path, output_size, file_type))
    print("ENCODING_SUCCESS:{}:{}:{}".format(input_size, output_size, file_type))
    sys.exit(0)


if __name__ == "__main__":
    main()