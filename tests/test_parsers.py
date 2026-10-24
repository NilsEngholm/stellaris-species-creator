from data_extractor.localization_parser import clean_localized_text, format_number, parse_localization_file
from data_extractor.paradox_parser import VALUES_KEY, Repeated, Variables, as_list, get_all, parse_text


def test_scalars_and_blocks():
    data = parse_text("""
        # comment
        cost = 2
        ratio = 0.5
        negative = -3
        initial = yes
        randomized = no
        icon = "gfx/foo.dds"
        tags = { organic positive }
        modifier = { pop_happiness = 0.1 }
        empty = {}
    """)
    assert data == {
        "cost": 2,
        "ratio": 0.5,
        "negative": -3,
        "initial": True,
        "randomized": False,
        "icon": "gfx/foo.dds",
        "tags": ["organic", "positive"],
        "modifier": {"pop_happiness": 0.1},
        "empty": {},
    }


def test_repeated_keys_are_distinguishable_from_list_values():
    data = parse_text("t = { m = { a = 1 } m = { b = 2 } single = { x y } }")["t"]
    assert isinstance(data["m"], Repeated)
    assert get_all(data, "m") == [{"a": 1}, {"b": 2}]
    assert get_all(data, "single") == [["x", "y"]]
    assert get_all(data, "missing") == []


def test_operators_mixed_blocks_and_colors():
    data = parse_text("""
        trigger = { num_pops > 5 size <= 10 }
        mixed = { foo bar = yes }
        color = hsv { 0.5 0.2 0.8 }
        math = @[ x * 2 ]
    """)
    assert data["trigger"] == {"num_pops": {">": 5}, "size": {"<=": 10}}
    assert data["mixed"] == {"bar": True, VALUES_KEY: ["foo"]}
    assert data["color"] == {"hsv": [0.5, 0.2, 0.8]}
    assert data["math"] == "@[ x * 2 ]"


def test_tolerates_stray_and_missing_braces():
    assert parse_text("a = 1 } b = 2") == {"a": 1, "b": 2}
    assert parse_text("a = { b = 1") == {"a": {"b": 1}}


def test_as_list():
    assert as_list(None) == []
    assert as_list({}) == []
    assert as_list("x") == ["x"]
    assert as_list(["a", "b"]) == ["a", "b"]
    assert as_list(Repeated([["a"], ["b", "c"]])) == ["a", "b", "c"]


def test_variables_resolve_local_then_global():
    variables = Variables()
    variables.globals = {"@g": 3, "@chain": "@g"}
    local = {"@l": 1, "@g": 9}
    assert variables.resolve({"a": "@l", "b": ["@chain"], "c": "@missing"}, local) == {
        "a": 1, "b": [9], "c": "@missing",
    }
    assert variables.resolve("@chain") == 3


def test_parse_localization_file(tmp_path):
    path = tmp_path / "test_l_english.yml"
    path.write_text(
        '﻿l_english:\n'
        ' # comment\n'
        ' trait_a:0 "Alpha"\n'
        ' trait_a_desc: "Has \\"quotes\\"" # trailing "comment"\n'
        ' trait_b:12 "Beta"\n',
        encoding="utf-8",
    )
    assert parse_localization_file(str(path)) == {
        "trait_a": "Alpha",
        "trait_a_desc": 'Has \\"quotes\\"',
        "trait_b": "Beta",
    }


def test_clean_localized_text():
    raw = "§YBold§! £energy£\u00a0Energy: ['concept_x', Concept] [Root.GetSpeciesNamePlural] $UNKNOWN$\\nNext"
    assert clean_localized_text(raw) == "Bold Energy: Concept this species\nNext"


def test_format_number():
    assert format_number(-0.01, "%") == "-1%"
    assert format_number(0.1, "+%") == "+10%"
    assert format_number(0.005, "3") == "0.005"
    assert format_number(2, "") == "2"
