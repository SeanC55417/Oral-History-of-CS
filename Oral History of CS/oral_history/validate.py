import subprocess
import sys
from pathlib import Path


def validate_record(path):
    """Run the installed MEDFORD validator; return an empty list on success."""
    project_root = Path(__file__).resolve().parents[1]
    record_path = Path(path).resolve()

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from MEDFORD import parse_args_and_go; parse_args_and_go()",
            "validate",
            str(record_path),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=60,
    )

    output = result.stdout + "\n" + result.stderr

    failed = (
        result.returncode != 0
        or "All validations passed!" not in result.stdout
        or "error" in output.lower()
        or "skipping validation" in output.lower()
    )

    if failed:
        message = output.strip()
        if not message:
            message = "MEDFORD validation failed."
        return [message]

    return []
