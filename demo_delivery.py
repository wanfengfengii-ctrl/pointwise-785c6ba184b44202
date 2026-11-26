"""Run the original HTTP demonstration followed by the SEEK trajectory."""
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def main() -> int:
    commands = (
        [sys.executable, '-B', '-m', 'tests.test_http', '--demo'],
        [sys.executable, '-B', str(ROOT / 'seek_scenarios.py')],
    )
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode
    print('DELIVERY DEMO PASS: original workflow and seek/readback trajectory completed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
