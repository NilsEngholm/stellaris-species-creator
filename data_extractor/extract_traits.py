"""
Stellaris Species Traits Extractor

Reads every file in common/traits/, keeps species traits (leader traits are
skipped) and writes them to JSON with localised names, resolved costs,
modifiers and the conditions that gate them in the empire creator.

Each trait gets:
  kind                    "normal", "habitability" (climate preference, picked
                          via homeworld), "background" (machine/robot history),
                          or "intrinsic" (cost-0 class traits like Organic)
  selectable_at_creation  whether it shows up in the species creator trait list
  requirements            allowed/forbidden origins, civics, ethics, species
                          classes, homeworld planet classes and DLC

Usage: python -m data_extractor.extract_traits [stellaris_path] [output_file]
"""

import os
from collections import defaultdict
from typing import Any

from .common import cli_args, write_json
from .localization_parser import Localization
from .paradox_parser import Variables, as_list, get_all, iter_script_files, parse_stellaris_file

# Block-valued keys holding modifiers that only apply under a condition
TRIGGERED_MODIFIER_PREFIX = "triggered_"

# Scopes a modifier block can apply to, besides the pop/species itself
SCOPED_MODIFIER_KEYS = ("planet_modifier", "self_modifier", "army_modifier", "fleet_modifier")

REQUIREMENT_KEYS = {
    "allowed_origins": "origins",
    "forbidden_origins": "forbidden_origins",
    "allowed_civics": "civics",
    "forbidden_civics": "forbidden_civics",
    "allowed_ethics": "ethics",
    "forbidden_ethics": "forbidden_ethics",
    "species_class": "species_classes",
    "allowed_planet_classes": "planet_classes",
}


def is_leader_trait(key: str, data: dict[str, Any]) -> bool:
    return key.startswith("leader_trait") or "leader_class" in data or "leader_trait_type" in data


def is_species_trait(key: str, data: dict[str, Any]) -> bool:
    if is_leader_trait(key, data):
        return False
    return "allowed_archetypes" in data or "species_potential_add" in data or "cost" in data


def is_habitability_trait(key: str, data: dict[str, Any]) -> bool:
    return "ideal_planet_class" in data or (key.startswith("trait_pc_") and key.endswith("_preference"))


def is_percent_modifier(key: str, value: Any) -> bool:
    """
    Heuristic for how the game displays a modifier. The game hardcodes this per
    modifier type; `_mult` and habitability modifiers are percentages, as are
    small fractional values.
    """
    if key.endswith("_mult") or "habitability" in key:
        return True
    return isinstance(value, float) and abs(value) < 1


def format_modifier_value(key: str, value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    if is_percent_modifier(key, value):
        pct = round(value * 100, 2)
        pct = int(pct) if pct == int(pct) else pct
        return f"{'+' if pct > 0 else ''}{pct}%"
    return f"{'+' if value > 0 else ''}{value}"


def build_modifiers(block: Any, loc: Localization) -> list[dict[str, Any]]:
    """Turn a `modifier = { key = value ... }` block into display-ready rows."""
    if not isinstance(block, dict):
        return []
    rows = []
    for key, value in block.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue  # nested triggers (potential = {...}), custom_tooltip, etc.
        rows.append({
            "key": key,
            "name": loc.get(f"mod_{key}") or loc.get(key) or key,
            "value": value,
            "display": format_modifier_value(key, value),
        })
    return rows


def resolve_cost(raw: Any) -> tuple[int | float, Any]:
    """Return (base cost, conditional cost modifiers or None)."""
    if isinstance(raw, dict):
        extra = {k: v for k, v in raw.items() if k != "base"}
        return raw.get("base", 0), (extra or None)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return raw, None
    return 0, None


def extract_trait(key: str, data: dict[str, Any], source: str, loc: Localization,
                  script_vars: dict[str, Any] | None = None) -> dict[str, Any]:
    """`script_vars` are the @variables visible to this trait, used to fill $@variable$ in tooltips."""
    cost, cost_modifiers = resolve_cost(data.get("cost"))
    tags = as_list(data.get("tags"))
    initial = data.get("initial", True)
    habitability = is_habitability_trait(key, data)

    if habitability:
        kind = "habitability"
    elif "background" in tags:
        kind = "background"
    elif cost == 0:
        kind = "intrinsic"
    else:
        kind = "normal"

    requirements: dict[str, Any] = {}
    for game_key, out_key in REQUIREMENT_KEYS.items():
        values = as_list(data.get(game_key))
        if values:
            requirements[out_key] = values
    if data.get("host_has_dlc"):
        requirements["dlc"] = data["host_has_dlc"]

    triggered = []
    for block_key in data:
        if not block_key.startswith(TRIGGERED_MODIFIER_PREFIX) or not block_key.endswith("modifier"):
            continue
        for entry in get_all(data, block_key):
            mods = build_modifiers(entry, loc)
            if mods:
                triggered.append({"scope": block_key, "modifiers": mods})

    scoped = {k: build_modifiers(data[k], loc) for k in SCOPED_MODIFIER_KEYS if isinstance(data.get(k), dict)}

    tooltip_key = data.get("custom_tooltip_with_modifiers") or data.get("custom_tooltip")
    tooltip = loc.get(tooltip_key, local_vars=script_vars) if isinstance(tooltip_key, str) else None

    trait = {
        "id": key,
        "name": loc.name(key),
        "description": loc.description(key),
        "source_file": source,
        "kind": kind,
        "selectable_at_creation": initial is not False and kind in ("normal", "background"),
        "cost": cost,
        "cost_modifiers": cost_modifiers,
        "initial": initial is not False,
        "randomized": data.get("randomized", True) is not False,
        "allowed_archetypes": as_list(data.get("allowed_archetypes")),
        "opposites": as_list(data.get("opposites")),
        "prerequisites": as_list(data.get("prerequisites")),
        "tags": tags,
        "category": data.get("category"),
        "sorting_priority": data.get("sorting_priority"),
        "icon": data.get("icon"),
        "requirements": requirements,
        "modifiers": build_modifiers(data.get("modifier"), loc),
        "scoped_modifiers": {k: v for k, v in scoped.items() if v},
        "triggered_modifiers": triggered,
        "effects_tooltip": tooltip,
    }
    if habitability:
        trait["ideal_planet_class"] = data.get("ideal_planet_class") or key.removeprefix("trait_").removesuffix("_preference")
    if data.get("bound_to_planet_classes"):
        trait["bound_to_planet_classes"] = as_list(data["bound_to_planet_classes"])
    return trait


def disambiguate_names(traits: list[dict[str, Any]]) -> None:
    """Several traits share a display name across archetypes (e.g. robotic vs organic
    "Strong"). Add a `display_name` with the archetype so UIs can tell them apart."""
    by_name = defaultdict(list)
    for trait in traits:
        if trait["selectable_at_creation"]:
            by_name[trait["name"]].append(trait)
    for name, group in by_name.items():
        for trait in group:
            archetypes = trait["allowed_archetypes"]
            if len(group) > 1 and archetypes:
                trait["display_name"] = f"{name} ({archetypes[0].title()})"
            else:
                trait["display_name"] = name
    for trait in traits:
        trait.setdefault("display_name", trait["name"])


def extract_traits(stellaris_path: str, loc: Localization | None = None, variables: Variables | None = None) -> list[dict[str, Any]]:
    loc = loc or Localization(stellaris_path)
    variables = variables or Variables(stellaris_path)
    traits_dir = os.path.join(stellaris_path, "common", "traits")

    traits: dict[str, dict[str, Any]] = {}
    for path in iter_script_files(traits_dir):
        filename = os.path.basename(path)
        if "documentation" in filename:
            continue
        parsed = parse_stellaris_file(path)
        local_vars = Variables.locals_of(parsed)
        count = 0
        for key, value in parsed.items():
            if key.startswith("@") or not isinstance(value, dict):
                continue
            if not is_species_trait(key, value):
                continue
            value = variables.resolve(value, local_vars)
            script_vars = {**variables.globals, **local_vars}
            traits[key] = extract_trait(key, value, filename, loc, script_vars)  # later files override
            count += 1
        if count:
            print(f"  {filename}: {count} species traits")

    result = sorted(traits.values(), key=lambda t: (t["sorting_priority"] or 0, t["id"]))
    disambiguate_names(result)
    return result


def main() -> None:
    stellaris_path, output_file = cli_args("traits.json")
    traits = extract_traits(stellaris_path)
    selectable = sum(t["selectable_at_creation"] for t in traits)
    print(f"Extracted {len(traits)} species traits ({selectable} selectable at empire creation)")
    write_json(traits, output_file)


if __name__ == "__main__":
    main()
