"""
Stellaris Species Classes & Portraits Extractor

Combines three databases:
  common/species_classes/      species classes (HUM, MAM, MACHINE, ...) and their archetype
  common/portrait_sets/        which portraits belong to which species class
  common/portrait_categories/  how portrait sets are grouped into tabs in the empire creator

plus gfx/portraits/portraits/ for each portrait's texture paths.

Outputs two files:
  species_classes.json      one entry per species class
  portrait_categories.json  creator tabs -> portraits (each tagged with its species class)

Usage: python -m data_extractor.extract_species_classes [stellaris_path] [output_dir]
"""

import os
import sys
from typing import Any

from .common import DEFAULT_OUTPUT_DIR, condition_state, find_stellaris_path, write_json
from .localization_parser import Localization
from .paradox_parser import as_list, get_all, iter_script_files, parse_directory, parse_stellaris_file


def find_dlc(trigger: Any) -> list[str]:
    """Collect DLC names referenced by host_has_dlc / local_has_dlc / has_*_dlc in a trigger."""
    found: list[str] = []
    if isinstance(trigger, dict):
        for key, value in trigger.items():
            if key in ("host_has_dlc", "local_has_dlc", "has_dlc") and isinstance(value, str):
                found.append(value)
            else:
                found.extend(find_dlc(value))
    elif isinstance(trigger, list):
        for item in trigger:
            found.extend(find_dlc(item))
    return list(dict.fromkeys(found))


def load_portrait_textures(stellaris_path: str) -> dict[str, list[str]]:
    """Texture paths per portrait id. Portrait groups (gendered/clothing variants
    under `portrait_groups`) use the textures of their `default` portrait."""
    textures: dict[str, list[str]] = {}
    group_defaults: dict[str, str] = {}
    portraits_dir = os.path.join(stellaris_path, "gfx", "portraits", "portraits")
    for path in iter_script_files(portraits_dir):
        parsed = parse_stellaris_file(path)
        for block in get_all(parsed, "portraits"):
            if not isinstance(block, dict):
                continue
            for portrait_id, data in block.items():
                if not isinstance(data, dict):
                    continue
                files = _texture_paths(data.get("character_textures")) or _texture_paths(data.get("texturefile"))
                if files:
                    textures[portrait_id] = files
        for block in get_all(parsed, "portrait_groups"):
            if not isinstance(block, dict):
                continue
            for group_id, data in block.items():
                if isinstance(data, dict) and isinstance(data.get("default"), str):
                    group_defaults[group_id] = data["default"]

    # Defaults can point at other groups, so follow the chain
    for group_id, default in group_defaults.items():
        seen = {group_id}
        while default in group_defaults and default not in textures and default not in seen:
            seen.add(default)
            default = group_defaults[default]
        if group_id not in textures and default in textures:
            textures[group_id] = textures[default]
    return textures


def _texture_paths(value: Any) -> list[str]:
    """All .dds paths in a texture field, including `tied_texture = { texture = ... }` entries."""
    if isinstance(value, str):
        return [value] if value.lower().endswith(".dds") else []
    if isinstance(value, dict):
        return [p for v in value.values() for p in _texture_paths(v)]
    if isinstance(value, list):
        return [p for v in value for p in _texture_paths(v)]
    return []


def _portrait(portrait_id: str, set_id: str, species_class: str | None, non_randomized: set[str],
              textures: dict[str, list[str]], playable: Any = None, randomizable: Any = None) -> dict[str, Any]:
    dlc = find_dlc(playable)
    return {
        "id": portrait_id,
        "species_class": species_class,
        "portrait_set": set_id,
        "playable": condition_state(playable),
        "randomizable": portrait_id not in non_randomized and condition_state(randomizable) is not False,
        "dlc": dlc[0] if len(dlc) == 1 else (dlc or None),
        "textures": textures.get(portrait_id, []),
    }


def extract_portrait_sets(stellaris_path: str, textures: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    sets = {}
    for set_id, (_, data) in parse_directory(os.path.join(stellaris_path, "common", "portrait_sets")).items():
        if not isinstance(data, dict):
            continue
        species_class = data.get("species_class")
        non_randomized = set(as_list(data.get("non_randomized_portraits")))
        portraits = [
            _portrait(portrait_id, set_id, species_class, non_randomized, textures)
            for portrait_id in as_list(data.get("portraits"))
        ]
        for cond in get_all(data, "conditional_portraits"):
            if isinstance(cond, dict):
                portraits.extend(
                    _portrait(portrait_id, set_id, species_class, non_randomized, textures,
                              cond.get("playable"), cond.get("randomizable"))
                    for portrait_id in as_list(cond.get("portraits"))
                )

        sets[set_id] = {"id": set_id, "species_class": species_class, "portraits": portraits}
    return sets


def extract_species_classes(stellaris_path: str, loc: Localization | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    loc = loc or Localization(stellaris_path)
    textures = load_portrait_textures(stellaris_path)
    portrait_sets = extract_portrait_sets(stellaris_path, textures)

    sets_by_class: dict[str, list[str]] = {}
    for portrait_set in portrait_sets.values():
        sets_by_class.setdefault(portrait_set["species_class"], []).append(portrait_set["id"])

    classes = []
    for class_id, (source, data) in parse_directory(os.path.join(stellaris_path, "common", "species_classes")).items():
        if not isinstance(data, dict):
            continue
        portrait_ids = [p["id"] for s in sets_by_class.get(class_id, []) for p in portrait_sets[s]["portraits"]]
        classes.append({
            "id": class_id,
            "name": loc.get(class_id) or class_id,
            "name_plural": loc.get(f"{class_id}_plural"),
            "source_file": source,
            "archetype": data.get("archetype", "BIOLOGICAL"),
            "playable": condition_state(data.get("playable")),
            "randomized": condition_state(data.get("randomized")),
            "gender": data.get("gender", True) is not False,
            "portrait_modding": data.get("portrait_modding", True) is not False,
            "traits": as_list(data.get("trait")),
            "graphical_culture": data.get("graphical_culture"),
            "uplifted_into": data.get("uplifted_into"),
            "possible": data.get("possible"),
            "playable_condition": data.get("playable") if condition_state(data.get("playable")) == "conditional" else None,
            "portrait_sets": sets_by_class.get(class_id, []),
            "portrait_count": len(portrait_ids),
        })

    categories = []
    for category_id, (_, data) in parse_directory(os.path.join(stellaris_path, "common", "portrait_categories")).items():
        if not isinstance(data, dict):
            continue
        name_key = data.get("name", category_id)
        set_ids = [s for s in as_list(data.get("sets")) if s in portrait_sets]
        portraits = [p for s in set_ids for p in portrait_sets[s]["portraits"]]
        categories.append({
            "id": category_id,
            "name": loc.get(name_key) or loc.get(f"{name_key}_plural") or name_key,
            "localization_key": name_key,
            "species_classes": list(dict.fromkeys(p["species_class"] for p in portraits if p["species_class"])),
            "portrait_sets": set_ids,
            "portraits": portraits,
        })

    return classes, categories


def main() -> None:
    stellaris_path = find_stellaris_path(sys.argv[1] if len(sys.argv) > 1 else None)
    output_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    classes, categories = extract_species_classes(stellaris_path)
    playable = sum(c["playable"] is not False for c in classes)
    print(f"Extracted {len(classes)} species classes ({playable} playable) and {len(categories)} portrait categories")
    write_json(classes, os.path.join(output_dir, "species_classes.json"))
    write_json(categories, os.path.join(output_dir, "portrait_categories.json"))


if __name__ == "__main__":
    main()
