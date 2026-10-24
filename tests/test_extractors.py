"""
Extractor tests against a tiny fake Stellaris install (see `fake_game`).
`test_real_install` additionally runs against a real install when one is found.
"""

import json
import os

import pytest

from data_extractor.common import find_stellaris_path
from data_extractor.extract_all import main as extract_all
from data_extractor.extract_planet_classes import extract_planet_classes
from data_extractor.extract_species_archetypes import extract_species_archetypes
from data_extractor.extract_species_classes import extract_species_classes
from data_extractor.extract_traits import extract_traits

FILES = {
    "launcher-settings.json": '{"rawVersion": "v9.8.7"}',
    "common/scripted_variables/00_vars.txt": "@global_bonus = 0.25\n",
    "common/species_archetypes/00_species_archetypes.txt": """
        @points = 2
        BIOLOGICAL = { species_trait_points = @points species_max_traits = 5 }
        LITHOID = { inherit_trait_points_from = BIOLOGICAL }
        ROBOT = { species_trait_points = 0 species_max_traits = 4 robotic = yes inherit_traits_from = { MACHINE } }
    """,
    "common/traits/000_documentation_species_traits.txt": "trait_doc = { cost = 1 }",
    "common/traits/01_habitability.txt": """
        @primary = 0.8
        trait_pc_desert_preference = {
            allowed_archetypes = { BIOLOGICAL }
            modifier = { pc_desert_habitability = @primary pc_arid_habitability = 0.6 }
        }
    """,
    "common/traits/04_species_traits.txt": """
        @local_bonus = 0.1
        trait_intelligent = {
            cost = 2
            allowed_archetypes = { BIOLOGICAL LITHOID }
            opposites = { "trait_erudite" }
            tags = { organic positive }
            modifier = { researcher_jobs_bonus_workforce_mult = @local_bonus }
            custom_tooltip_with_modifiers = trait_intelligent_tt
        }
        trait_strong = { cost = 1 allowed_archetypes = { BIOLOGICAL } }
        trait_robot_strong = { cost = 1 allowed_archetypes = { ROBOT } }
        trait_organic = { cost = 0 initial = no allowed_archetypes = { BIOLOGICAL } }
        trait_gated = {
            cost = { base = 1 modifier = { mult = 0 has_country_flag = x } }
            allowed_archetypes = { BIOLOGICAL }
            allowed_civics = { civic_augmentation_bazaars }
            host_has_dlc = "Some DLC"
        }
        leader_trait_genius = { cost = 1 leader_class = { scientist } }
    """,
    "common/species_classes/00_species_classes.txt": """
        HUM = { archetype = BIOLOGICAL trait = "trait_organic" }
        PRE_HUM = { archetype = BIOLOGICAL playable = { always = no } }
        LITHOID = { archetype = LITHOID playable = { host_has_dlc = "Lithoids Species Pack" } }
    """,
    "common/portrait_sets/00_portrait_sets.txt": """
        humans = {
            species_class = HUM
            portraits = { "hum1" "hum2" }
            conditional_portraits = { playable = { local_has_dlc = "Some DLC" } portraits = { "hum3" } }
            non_randomized_portraits = { "hum2" }
        }
    """,
    "common/portrait_categories/00_portrait_categories.txt": "humanoids = { name = HUM sets = { humans } }",
    "gfx/portraits/portraits/00_portraits.txt": """
        portraits = {
            hum1 = { character_textures = { "gfx/hum1.dds" } }
            hum2 = { character_textures = { tied_texture = { texture = "gfx/hum2.dds" } } }
            hum3_m = { texturefile = "gfx/hum3.dds" }
        }
        portrait_groups = { hum3 = { default = hum3_m } }
    """,
    "common/planet_classes/00_planet_classes.txt": """
        pc_desert = { climate = "dry" initial = yes colonizable = yes }
        pc_arid = { climate = "dry" initial = yes colonizable = yes }
        pc_gas_giant = { colonizable = no }
    """,
    "common/name_lists/HUM1.txt": "HUM1 = { category = \"Humanoid\" ship_names = { generic = { A B } } }",
    "localisation/english/main_l_english.yml": (
        "l_english:\n"
        ' trait_intelligent:0 "Intelligent"\n'
        ' trait_intelligent_desc:0 "§LSmart.§!"\n'
        ' trait_intelligent_tt:0 "Research: +$@local_bonus|%$, global $@global_bonus|%$"\n'
        ' trait_strong:0 "Strong"\n'
        ' trait_robot_strong:0 "$trait_strong$"\n'
        ' mod_researcher_jobs_bonus_workforce_mult:0 "Researcher Output"\n'
        ' HUM:0 "Humanoid"\n'
        ' pc_desert:0 "Desert World"\n'
        ' name_list_HUM1:0 "Humanoid 1"\n'
    ),
}


@pytest.fixture
def fake_game(tmp_path):
    for rel, content in FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return str(tmp_path)


def by_id(items):
    return {item["id"]: item for item in items}


def test_archetypes(fake_game):
    archetypes = extract_species_archetypes(fake_game)
    assert archetypes["BIOLOGICAL"]["trait_points"] == 2
    assert archetypes["LITHOID"]["trait_points"] == 2
    assert archetypes["LITHOID"]["max_traits"] == 5
    assert archetypes["ROBOT"]["robotic"] is True
    assert archetypes["ROBOT"]["trait_archetypes"] == ["ROBOT", "MACHINE"]


def test_traits(fake_game):
    traits = by_id(extract_traits(fake_game))
    assert "leader_trait_genius" not in traits
    assert "trait_doc" not in traits

    smart = traits["trait_intelligent"]
    assert smart["name"] == "Intelligent"
    assert smart["description"] == "Smart."
    assert smart["selectable_at_creation"] is True
    assert smart["opposites"] == ["trait_erudite"]
    assert smart["modifiers"] == [{
        "key": "researcher_jobs_bonus_workforce_mult",
        "name": "Researcher Output",
        "value": 0.1,
        "display": "+10%",
    }]
    assert smart["effects_tooltip"] == "Research: +10%, global 25%"

    assert traits["trait_organic"]["kind"] == "intrinsic"
    assert traits["trait_organic"]["selectable_at_creation"] is False

    desert = traits["trait_pc_desert_preference"]
    assert desert["kind"] == "habitability"
    assert desert["ideal_planet_class"] == "pc_desert"
    assert desert["selectable_at_creation"] is False

    gated = traits["trait_gated"]
    assert gated["cost"] == 1
    assert gated["cost_modifiers"] is not None
    assert gated["requirements"] == {"civics": ["civic_augmentation_bazaars"], "dlc": "Some DLC"}

    # Same display name on two archetypes gets disambiguated
    assert traits["trait_strong"]["display_name"] == "Strong (Biological)"
    assert traits["trait_robot_strong"]["display_name"] == "Strong (Robot)"


def test_species_classes_and_portraits(fake_game):
    classes, categories = extract_species_classes(fake_game)
    classes = by_id(classes)
    assert classes["HUM"]["name"] == "Humanoid"
    assert classes["HUM"]["playable"] is True
    assert classes["HUM"]["portrait_count"] == 3
    assert classes["PRE_HUM"]["playable"] is False
    assert classes["LITHOID"]["playable"] == "conditional"

    (category,) = categories
    assert category["species_classes"] == ["HUM"]
    portraits = by_id(category["portraits"])
    assert portraits["hum1"]["textures"] == ["gfx/hum1.dds"]
    assert portraits["hum2"]["textures"] == ["gfx/hum2.dds"]
    assert portraits["hum2"]["randomizable"] is False
    assert portraits["hum3"]["textures"] == ["gfx/hum3.dds"]
    assert portraits["hum3"]["dlc"] == "Some DLC"
    assert portraits["hum3"]["playable"] == "conditional"


def test_planet_classes(fake_game):
    planets = by_id(extract_planet_classes(fake_game))
    assert set(planets) == {"pc_desert", "pc_arid"}
    assert planets["pc_desert"]["habitability_trait"] == "trait_pc_desert_preference"
    assert planets["pc_desert"]["habitability"] == {"pc_desert": 0.8, "pc_arid": 0.6}
    assert planets["pc_arid"]["habitability_trait"] is None


def test_extract_all_writes_versioned_output(fake_game, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    extract_all([fake_game])
    out = tmp_path / "output" / "versions" / "9.8.7"
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["game_version"] == "9.8.7"
    for filename in manifest["files"]:
        assert (out / filename).is_file()
    assert manifest["files"]["name_lists.json"] == 1


def test_real_install():
    """Smoke test against a real Stellaris install, if one can be found."""
    try:
        path = find_stellaris_path()
    except SystemExit:
        pytest.skip("no Stellaris install found (set STELLARIS_PATH to run)")
    traits = by_id(extract_traits(path))
    assert traits["trait_intelligent"]["name"] == "Intelligent"
    assert sum(t["selectable_at_creation"] for t in traits.values()) > 100
    classes, categories = extract_species_classes(path)
    assert any(c["id"] == "HUM" for c in classes)
    assert all(os.path.splitext(t)[1] == ".dds" for c in categories for p in c["portraits"] for t in p["textures"])
