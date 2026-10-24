"""
Stellaris Name Lists Extractor

Reads common/name_lists/ and outputs the name lists offered in the species
creator's "Name List" picker: id, localised name, category (the species-type
grouping shown in the UI), whether it is selectable / used for random empires,
and how many names of each kind it contains.

Usage: python -m data_extractor.extract_name_lists [stellaris_path] [output_file]
"""

import os
from typing import Any

from .common import cli_args, condition_state, write_json
from .localization_parser import Localization
from .paradox_parser import parse_directory

NAME_SECTIONS = ("ship_names", "fleet_names", "army_names", "planet_names", "character_names")


def count_names(value: Any) -> int:
    """Count leaf name entries in a (possibly nested) name block."""
    if isinstance(value, dict):
        # `sequential_name` is a format string ("%O% Fleet"), not a name
        return sum(count_names(v) for k, v in value.items() if k not in ("weight", "sequential_name"))
    if isinstance(value, list):
        return sum(count_names(v) for v in value)
    return 1 if isinstance(value, str) else 0


def extract_name_lists(stellaris_path: str, loc: Localization | None = None) -> list[dict[str, Any]]:
    loc = loc or Localization(stellaris_path)
    name_lists = []
    for list_id, (source, data) in parse_directory(os.path.join(stellaris_path, "common", "name_lists")).items():
        if not isinstance(data, dict):
            continue
        name_lists.append({
            "id": list_id,
            "name": loc.get(f"name_list_{list_id}") or list_id,
            "source_file": source,
            "category": data.get("category"),
            "selectable": condition_state(data.get("selectable")),
            "randomized": condition_state(data.get("randomized")),
            "name_counts": {s: count_names(data.get(s)) for s in NAME_SECTIONS if s in data},
        })
    return name_lists


def main() -> None:
    stellaris_path, output_file = cli_args("name_lists.json")
    name_lists = extract_name_lists(stellaris_path)
    selectable = sum(n["selectable"] is not False for n in name_lists)
    print(f"Extracted {len(name_lists)} name lists ({selectable} selectable)")
    write_json(name_lists, output_file)


if __name__ == "__main__":
    main()
