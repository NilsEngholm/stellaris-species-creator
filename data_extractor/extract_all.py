"""
Extract all species-creator data from a Stellaris install.

Detects the game version from launcher-settings.json and writes to
output/versions/<version>/ (or output/ if the version can't be detected),
along with a manifest.json describing the run.

Usage: python -m data_extractor.extract_all [stellaris_path] [--output DIR]
"""

import argparse
import os
import time
from datetime import UTC, datetime

from .common import DEFAULT_OUTPUT_DIR, detect_game_version, find_stellaris_path, write_json
from .extract_name_lists import extract_name_lists
from .extract_planet_classes import extract_planet_classes
from .extract_species_archetypes import extract_species_archetypes
from .extract_species_classes import extract_species_classes
from .extract_traits import extract_traits
from .localization_parser import Localization
from .paradox_parser import Variables


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract Stellaris species data to JSON.")
    parser.add_argument("stellaris_path", nargs="?", help="Stellaris install directory (auto-detected if omitted)")
    parser.add_argument("--output", "-o", help="Output directory (default: output/versions/<game version>)")
    parser.add_argument("--language", default="english", help="Localisation language (default: english)")
    args = parser.parse_args(argv)

    stellaris_path = find_stellaris_path(args.stellaris_path)
    game_version = detect_game_version(stellaris_path)
    if args.output:
        output_dir = args.output
    elif game_version:
        output_dir = os.path.join(DEFAULT_OUTPUT_DIR, "versions", game_version)
    else:
        print("Warning: could not detect game version, writing to output/")
        output_dir = DEFAULT_OUTPUT_DIR

    print("=" * 70)
    print("STELLARIS SPECIES DATA EXTRACTOR")
    print("=" * 70)
    print(f"Source:       {stellaris_path}")
    print(f"Game version: {game_version or 'unknown'}")
    print(f"Output:       {output_dir}")
    started = time.monotonic()

    print("\n--- Loading localisation & scripted variables ---")
    variables = Variables(stellaris_path)
    loc = Localization(stellaris_path, args.language, variables.globals)
    print(f"  {len(loc)} localisation entries, {len(variables.globals)} scripted variables")

    print("\n--- Species archetypes ---")
    archetypes = extract_species_archetypes(stellaris_path, loc, variables)
    for a in archetypes.values():
        print(f"  {a['id']}: {a['trait_points']} points, {a['max_traits']} max traits")
    write_json(archetypes, os.path.join(output_dir, "species_archetypes.json"))

    print("\n--- Species traits ---")
    traits = extract_traits(stellaris_path, loc, variables)
    print(f"  {len(traits)} species traits ({sum(t['selectable_at_creation'] for t in traits)} selectable at creation)")
    write_json(traits, os.path.join(output_dir, "traits.json"))

    print("\n--- Species classes & portraits ---")
    classes, categories = extract_species_classes(stellaris_path, loc)
    print(f"  {len(classes)} species classes, {len(categories)} portrait categories, "
          f"{sum(len(c['portraits']) for c in categories)} portraits")
    write_json(classes, os.path.join(output_dir, "species_classes.json"))
    write_json(categories, os.path.join(output_dir, "portrait_categories.json"))

    print("\n--- Homeworld planet classes ---")
    planet_classes = extract_planet_classes(stellaris_path, loc, traits)
    print(f"  {len(planet_classes)} habitable planet classes "
          f"({sum(p['selectable_as_homeworld'] for p in planet_classes)} selectable as homeworld)")
    write_json(planet_classes, os.path.join(output_dir, "planet_classes.json"))

    print("\n--- Name lists ---")
    name_lists = extract_name_lists(stellaris_path, loc)
    print(f"  {len(name_lists)} name lists ({sum(n['selectable'] is not False for n in name_lists)} selectable)")
    write_json(name_lists, os.path.join(output_dir, "name_lists.json"))

    counts = {
        "species_archetypes": len(archetypes),
        "traits": len(traits),
        "species_classes": len(classes),
        "portrait_categories": len(categories),
        "planet_classes": len(planet_classes),
        "name_lists": len(name_lists),
    }
    write_json({
        "game_version": game_version,
        "language": args.language,
        "extracted_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": {f"{name}.json": count for name, count in counts.items()},
    }, os.path.join(output_dir, "manifest.json"))

    print("\n" + "=" * 70)
    print(f"EXTRACTION COMPLETE in {time.monotonic() - started:.1f}s -> {output_dir}/")
    print("=" * 70)


if __name__ == "__main__":
    main()
