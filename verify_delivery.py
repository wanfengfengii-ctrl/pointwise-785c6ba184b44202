"""Run the original regression and SEEK HTTP verification as one checklist entry."""
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def main() -> int:
    commands = (
        [sys.executable, '-B', str(ROOT / 'check_project.py')],
        [sys.executable, '-B', str(ROOT / 'seek_scenarios.py')],
    )
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode
    print('DELIVERY VERIFY PASS: original regression and SEEK scenarios both passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
