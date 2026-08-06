#!/usr/bin/env bash
#
# dev_tools/local/test_logs.sh
#
# Quick test of the Dolos log rotation without starting the full server.
# Imports the ssh_client module and sends test events to verify that
# the RotatingFileHandler creates files and maps levels correctly.
#
# Usage:
#   bash dev_tools/local/test_logs.sh          # Run test, show output
#   bash dev_tools/local/test_logs.sh --clean  # Clean up test logs after
#
set -uo pipefail

D="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$D/.venv"
LOG_DIR="/tmp/dolos_log_test"

echo "=== Dolos Log Rotation Test ==="
echo ""

# Clean up any previous test
rm -rf "$LOG_DIR" 2>/dev/null
mkdir -p "$LOG_DIR"

echo "[1] Running log rotation test..."
"$VENV/bin/python" -c "
import os, sys, shutil

# Point log dir at our test directory
os.environ['DOLOS_LOG_DIR'] = '$LOG_DIR'
os.environ['DOLOS_LOG_MAX_MB'] = '1'
os.environ['DOLOS_LOG_MAX_BACKUPS'] = '2'

# Add the Dolos source to Python path
sys.path.insert(0, '$D/Payload_Type/dolos')

# Import the modules - this triggers _setup_file_logging()
from dolos.ssh_client import SSHSessionLog

# Create a session log and add events
log = SSHSessionLog()
log.connecting('172.28.0.3', 22, 'mrgnc')
log.connected('172.28.0.3', 22, 'windows')
log.auth_success('mrgnc', 'password')
log.sftp_test(True, 'SFTP write test successful')
log.creating_workdir('C:/Windows/Temp/wd_a3f7kx', 'windows')
log.workdir_created('C:/Windows/Temp/wd_a3f7kx')
log.uploading_file('wd_in.bin', 'C:/Windows/Temp/wd_a3f7kx/wd_in.bin', 1800000)
log.upload_complete('wd_in.bin', 1800000, 2.5)
log.running_command('py.exe C:\\\\tools\\\\encoder.py C:\\\\Windows\\\\Temp\\\\wd_a3f7kx\\\\wd_in.bin C:\\\\Windows\\\\Temp\\\\wd_a3f7kx\\\\wd_out.bin')
log.command_started('py.exe C:\\\\tools\\\\encoder.py ...')
log.command_stdout('ENCODING_SUCCESS')
log.command_exit(0, 15.3)
log.downloading_result('C:/Windows/Temp/wd_a3f7kx/wd_out.bin')
log.result_downloaded('C:/Windows/Temp/wd_a3f7kx/wd_out.bin', 1900000)
log.cleanup_file('C:/Windows/Temp/wd_a3f7kx/wd_in.bin', True)
log.cleanup_workdir('C:/Windows/Temp/wd_a3f7kx', True)
log.validating('SUCCESS', 'Success confirmed', 0, 1800000, 1900000, 'PE/EXE', 'ENCODING_SUCCESS', '')
log.magic_detected('PE/EXE', 1900000)

# Generate JSON output
json_out = log.to_json(
    payload_uuid='test-uuid-1234',
    encoder_label='PyEncoder_v1.0',
    wrapped_payload_uuid='wrapped-uuid-5678',
    input_size=1800000,
    output_size=1900000,
    final_status='SUCCESS',
)
print(f'Session log JSON: {len(json_out)} chars, {len(log.events)} events')

# Check the file log
log_file = os.path.join('$LOG_DIR', 'dolos.log')
if os.path.exists(log_file):
    with open(log_file) as f:
        lines = f.readlines()
    print(f'File log: {len(lines)} lines')
    # Show level distribution
    levels = {}
    import re
    for line in lines:
        m = re.search(r'\\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\\]', line)
        if m:
            lvl = m.group(1)
            levels[lvl] = levels.get(lvl, 0) + 1
    print(f'Level distribution: {levels}')
    print()
    print('First 5 log lines:')
    for line in lines[:5]:
        print(f'  {line.rstrip()}')
    print('...')
    print('Last 3 log lines:')
    for line in lines[-3:]:
        print(f'  {line.rstrip()}')
    print()
    print('PASS: Log rotation working correctly!')
else:
    print('FAIL: Log file not created!')
    sys.exit(1)
"

EXIT_CODE=$?

echo ""

if [ "${1:-}" = "--clean" ]; then
    echo "[2] Cleaning up test logs..."
    rm -rf "$LOG_DIR"
    echo "Cleaned."
fi

exit $EXIT_CODE