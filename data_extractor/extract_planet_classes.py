"""
Stellaris Planet Classes Extractor (homeworld / climate preference)

Reads common/planet_classes/ and outputs the colonizable planet classes a
species can live on, with their climate, whether they can be picked as a
homeworld in the empire creator (`initial = yes`), and the habitability trait
a species born there gets (e.g. pc_desert -> trait_pc_desert_preference).

Usage: python -m data_extractor.extract_planet_classes [stellaris_path] [output_file]
"""

import os
from typing import Any

from .common import cli_args, write_json
from .extract_traits import extract_traits
from .localization_parser import Localization
from .paradox_parser import parse_directory


def extract_planet_classes(stellaris_path: str, loc: Localization | None = None, traits: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    loc = loc or Localization(stellaris_path)
    if traits is None:
        traits = extract_traits(stellaris_path, loc)

    preference_traits = {t["ideal_planet_class"]: t for t in traits if t["kind"] == "habitability"}
    bound_traits: dict[str, list[str]] = {}
    for trait in traits:
        for pc in trait.get("bound_to_planet_classes", []):
            bound_traits.setdefault(pc, []).append(trait["id"])

    planet_classes = []
    for pc_id, (source, data) in parse_directory(os.path.join(stellaris_path, "common", "planet_classes")).items():
        if not isinstance(data, dict) or not pc_id.startswith("pc_"):
            continue
        colonizable = data.get("colonizable", False) is True
        trait = preference_traits.get(pc_id)
        if not colonizable and not trait and pc_id not in bound_traits:
            continue  # gas giants, asteroids, stars, ...

        habitability = {}
        if trait:
            for mod in trait["modifiers"]:
                if mod["key"].startswith("pc_") and mod["key"].endswith("_habitability"):
                    habitability[mod["key"].removesuffix("_habitability")] = mod["value"]

        planet_classes.append({
            "id": pc_id,
            "name": loc.name(pc_id),
            "description": loc.description(pc_id),
            "source_file": source,
            "climate": data.get("climate"),
            "selectable_as_homeworld": data.get("initial", False) is True,
            "colonizable": colonizable,
            "ideal": data.get("ideal", False) is True,
            "icon": data.get("icon"),
            "habitability_trait": trait["id"] if trait else None,
            "bound_traits": bound_traits.get(pc_id, []),
            # Habitability of other planet classes for a species with this preference
            "habitability": habitability,
        })
    return planet_classes


def main() -> None:
    stellaris_path, output_file = cli_args("planet_classes.json")
    planet_classes = extract_planet_classes(stellaris_path)
    selectable = sum(p["selectable_as_homeworld"] for p in planet_classes)
    print(f"Extracted {len(planet_classes)} habitable planet classes ({selectable} selectable as homeworld)")
    write_json(planet_classes, output_file)


if __name__ == "__main__":
    main()
