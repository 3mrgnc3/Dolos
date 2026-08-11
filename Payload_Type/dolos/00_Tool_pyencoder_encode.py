"""Dolos PyEncoder - simple passthrough encoder for testing.

Reads input file, writes output file with success marker.
This is the encoder script that gets deployed to C:\tools\dolos\encoder.py
on the target Windows machine.

Usage: py.exe encoder.py <input_file> <output_file>
"""

import sys
import hashlib

def main():
    if len(sys.argv) != 3:
        print("ENCODING_FAILED: Usage: encoder.py <input> <output>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    try:
        with open(input_path, "rb") as f:
            data = f.read()

        # Passthrough: just copy the data to output
        # In production encoders, transform here (shellcode, donut, etc.)
        with open(output_path, "wb") as f:
            f.write(data)

        # Success marker - Dolos looks for this string
        print(f"ENCODING_SUCCESS len={len(data)} sha256={hashlib.sha256(data).hexdigest()[:16]}")

    except Exception as e:
        print(f"ENCODING_FAILED: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()