"""
Stellaris Species Archetypes Extractor

Reads common/species_archetypes/ and outputs the trait budget for each
archetype (BIOLOGICAL, LITHOID, MACHINE, ROBOT, ...): trait points, max
traits, whether it is robotic, and which archetypes' traits it may also use.

`inherit_trait_points_from` / `inherit_traits_from` are followed so every
archetype ends up with concrete values.

Usage: python -m data_extractor.extract_species_archetypes [stellaris_path] [output_file]
"""

import os
from typing import Any

from .common import cli_args, write_json
from .localization_parser import Localization
from .paradox_parser import Variables, as_list, iter_script_files, parse_stellaris_file


def extract_species_archetypes(stellaris_path: str, loc: Localization | None = None, variables: Variables | None = None) -> dict[str, dict[str, Any]]:
    loc = loc or Localization(stellaris_path)
    variables = variables or Variables(stellaris_path)

    raw: dict[str, dict[str, Any]] = {}
    for path in iter_script_files(os.path.join(stellaris_path, "common", "species_archetypes")):
        parsed = parse_stellaris_file(path)
        local_vars = Variables.locals_of(parsed)
        for key, value in parsed.items():
            if not key.startswith("@") and isinstance(value, dict):
                raw[key] = variables.resolve(value, local_vars)

    def budget(key: str, field: str, seen: frozenset = frozenset()) -> Any:
        data = raw.get(key, {})
        if field in data or key in seen:
            return data.get(field)
        parent = data.get("inherit_trait_points_from")
        return budget(parent, field, seen | {key}) if parent else None

    archetypes = {}
    for key, data in raw.items():
        archetypes[key] = {
            "id": key,
            "name": loc.get(f"SPECIES_ARCHETYPE_{key}") or loc.get(key) or key.title(),
            "trait_points": budget(key, "species_trait_points"),
            "max_traits": budget(key, "species_max_traits"),
            "robotic": data.get("robotic", False) is True,
            "uses_modifiers": data.get("uses_modifiers", True) is not False,
            # Archetypes whose traits this one may also take (always includes itself)
            "trait_archetypes": [key] + [a for a in as_list(data.get("inherit_traits_from")) if a != key],
            "inherits_trait_points_from": data.get("inherit_trait_points_from"),
        }
    return archetypes


def main() -> None:
    stellaris_path, output_file = cli_args("species_archetypes.json")
    archetypes = extract_species_archetypes(stellaris_path)
    for a in archetypes.values():
        print(f"  {a['id']}: {a['trait_points']} points, {a['max_traits']} max traits")
    write_json(archetypes, output_file)


if __name__ == "__main__":
    main()
