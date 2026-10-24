# Stellaris Species Creator — Data Extractor

Extracts everything the Stellaris species creator needs from a local game
install into JSON: traits, archetype trait budgets, species classes, portraits,
homeworld planet classes and name lists, with English (or any other)
localisation resolved to plain text.

Structure follows the [`stellaris_build` data-extractor](https://github.com/Evanok/stellaris_build/tree/master/data-extractor):
a generic Paradox script parser, a localisation parser, one `extract_*.py`
module per data type (each runnable on its own), and an `extract_all.py`
that writes versioned output.

## Requirements

- Python 3.14+ and [uv](https://docs.astral.sh/uv/)
- Stellaris installed. No third-party runtime dependencies.

## Usage

```bash
uv run stellaris-extract                       # auto-detect the install
uv run stellaris-extract "/path/to/Stellaris"  # explicit path
uv run stellaris-extract -o data/              # custom output dir
uv run stellaris-extract --language french
```

The install is found from, in order: the path argument, the `STELLARIS_PATH`
environment variable, then the usual Steam locations on Linux (native and
Flatpak), macOS, Windows and WSL.

Output goes to `output/versions/<game version>/` (version read from
`launcher-settings.json`):

| File | Contents |
| --- | --- |
| `traits.json` | All species traits (348 in 4.5.2, 163 selectable at creation) |
| `species_archetypes.json` | Trait points / max traits per archetype |
| `species_classes.json` | Species classes (HUM, MAM, MACHINE, ...) with archetype and playability |
| `portrait_categories.json` | Creator portrait tabs → portraits, each with species class, DLC and textures |
| `planet_classes.json` | Habitable planet classes, homeworld eligibility, habitability trait and matrix |
| `name_lists.json` | Name lists with category and selectability |
| `manifest.json` | Game version, language, timestamp, entry counts |

Each extractor can also run alone:

```bash
uv run python -m data_extractor.extract_traits [stellaris_path] [output_file]
uv run python -m data_extractor.extract_species_archetypes [stellaris_path] [output_file]
uv run python -m data_extractor.extract_species_classes [stellaris_path] [output_dir]
uv run python -m data_extractor.extract_planet_classes [stellaris_path] [output_file]
uv run python -m data_extractor.extract_name_lists [stellaris_path] [output_file]
```

## Data notes

### Traits

Every file in `common/traits/` is scanned (not a hardcoded list), so new DLC
trait files get picked up automatically. Leader traits are dropped. Rather than
filtering traits out, each one is classified so the consumer can decide:

- `kind`: `normal`, `habitability` (climate preference, set by homeworld),
  `background` (robot/machine history), or `intrinsic` (cost-0 class traits
  like Organic)
- `selectable_at_creation`: `initial` isn't `no` and kind is `normal`/`background`
- `requirements`: allowed/forbidden origins, civics, ethics, species classes,
  planet classes, and `dlc`. For example, cyborg traits are kept with
  `requirements.civics = ["civic_augmentation_bazaars"]`
- `display_name`: the name with an archetype suffix when two selectable traits
  share one, e.g. "Strong (Biological)" vs "Strong (Robot)"

```json
{
  "id": "trait_intelligent",
  "name": "Intelligent",
  "display_name": "Intelligent",
  "description": "This species is highly intelligent, and enjoys faster technological progress.",
  "kind": "normal",
  "selectable_at_creation": true,
  "cost": 2,
  "allowed_archetypes": ["BIOLOGICAL", "LITHOID"],
  "opposites": ["trait_nerve_stapled", "trait_erudite", "trait_enigmatic_intelligence_poor"],
  "requirements": {},
  "modifiers": [
    {"key": "researcher_jobs_bonus_workforce_mult", "name": "Job Efficiency for Researcher jobs", "value": 0.1, "display": "+10%"}
  ],
  "effects_tooltip": null
}
```

`cost` is the base cost. Conditional cost changes are in `cost_modifiers`.
`@variables` are resolved from both `common/scripted_variables/` and the
file-local definitions, including the ones inside tooltip text (`$@var|%$`).

### Portraits

`portrait_categories.json` matches the creator's tabs. Each portrait carries
its `species_class`. The Cybernetic, Synthetic, BioGenesis and Psionic tabs
contain portraits from several classes. `textures` lists the `.dds` paths
under the game directory, following portrait groups to their default
portrait. A few portraits are entity-only (their textures are in the 3D mesh)
and have an empty list.

### Conditions

Fields that can be `yes`, `no` or a trigger in game files (`playable`,
`selectable`, ...) come out as `true`, `false` or `"conditional"`. The raw
trigger is kept where it's useful, e.g. `possible` and `playable_condition` on
species classes.

## Architecture

```
data_extractor/
  paradox_parser.py            Paradox script tokenizer/parser, @variable resolution
  localization_parser.py       .yml loader, $key$ / $@var$ resolution, markup cleanup
  common.py                    install detection, game version, JSON output
  extract_traits.py
  extract_species_archetypes.py
  extract_species_classes.py   species classes + portrait sets/categories/textures
  extract_planet_classes.py
  extract_name_lists.py
  extract_all.py
tests/                         fixture-based tests + a real-install smoke test
```

How the parser maps game syntax to JSON:

- `key = { a b }` → list. `key = { x = 1 }` → object. `key = {}` → `{}`
- A key repeated in one block → a `Repeated` list (a `list` subclass). Use
  `get_all(block, key)` to read a key the same way whether it appears once or
  many times
- Comparisons `x > 5` → `{"x": {">": 5}}`. Colours `hsv { ... }` → `{"hsv": [...]}`
- Mixed blocks `{ a b = c }` keep their bare values under `"__values__"`
- It parses all 2,063 script files under `common/` in 4.5.2 without errors

## Development

```bash
uv run pytest
uvx ruff check .
```

`test_real_install` runs only when an install is found (or `STELLARIS_PATH` is set).

## Not yet extracted

- Icons and portrait images (DDS → PNG). The reference repo does this with Pillow.
  The JSON already has the source paths (`icon`, `textures`)
- Origins and civics, which gate some traits (referenced by id in `requirements`)
- Full name-list contents (only counts are extracted)

Stellaris and its data belong to Paradox Interactive.
