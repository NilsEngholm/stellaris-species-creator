"""Shared helpers: locating the game install, game version, and JSON output."""

import json
import os
import re
import sys
from typing import Any

from .paradox_parser import to_json_safe

DEFAULT_OUTPUT_DIR = "output"

_CANDIDATE_PATHS = [
    # Linux (native Steam, Flatpak Steam)
    "~/.steam/steam/steamapps/common/Stellaris",
    "~/.local/share/Steam/steamapps/common/Stellaris",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Stellaris",
    # macOS
    "~/Library/Application Support/Steam/steamapps/common/Stellaris",
    # Windows
    r"C:\Program Files (x86)\Steam\steamapps\common\Stellaris",
    r"C:\Program Files\Steam\steamapps\common\Stellaris",
    # WSL
    "/mnt/c/Program Files (x86)/Steam/steamapps/common/Stellaris",
]


def is_stellaris_dir(path: str) -> bool:
    return os.path.isdir(os.path.join(path, "common")) and os.path.isdir(os.path.join(path, "localisation"))


def find_stellaris_path(explicit: str | None = None) -> str:
    """
    Resolve the Stellaris install directory: explicit argument, then the
    STELLARIS_PATH environment variable, then common Steam locations.
    """
    candidates = [explicit] if explicit else []
    if os.environ.get("STELLARIS_PATH"):
        candidates.append(os.environ["STELLARIS_PATH"])
    if not explicit:
        candidates.extend(_CANDIDATE_PATHS)

    for candidate in candidates:
        path = os.path.expanduser(candidate)
        if is_stellaris_dir(path):
            return path

    if explicit:
        sys.exit(f"Error: '{explicit}' does not look like a Stellaris install (no common/ or localisation/).")
    sys.exit("Error: could not find Stellaris. Pass the install path as an argument or set STELLARIS_PATH.")


def detect_game_version(stellaris_path: str) -> str | None:
    """Return 'major.minor.patch' from launcher-settings.json (e.g. 'v4.5.2' -> '4.5.2')."""
    try:
        with open(os.path.join(stellaris_path, "launcher-settings.json"), encoding="utf-8") as f:
            raw = json.load(f).get("rawVersion", "")
    except (OSError, json.JSONDecodeError):
        return None
    m = re.search(r"\d+(\.\d+)+", raw)
    return m.group(0) if m else None


def write_json(data: Any, output_file: str) -> None:
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(to_json_safe(data), f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  -> {output_file}")


def cli_args(default_filename: str) -> tuple[str, str]:
    """Parse `<script> [stellaris_path] [output_file]` for the standalone extractors."""
    stellaris_path = find_stellaris_path(sys.argv[1] if len(sys.argv) > 1 else None)
    output_file = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DEFAULT_OUTPUT_DIR, default_filename)
    return stellaris_path, output_file


def condition_state(value: Any) -> bool | str:
    """Collapse a yes/no/trigger field into True, False or "conditional"."""
    if value is None or value is True:
        return True
    if value is False or value == {"always": False}:
        return False
    if value == {"always": True}:
        return True
    return "conditional"
