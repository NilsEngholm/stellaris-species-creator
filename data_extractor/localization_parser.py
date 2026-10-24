"""
Stellaris Localization Parser

Loads localisation/<language>/*.yml, resolves `$key$` references and strips
Stellaris text markup (colour codes, icons, scripted function calls).
"""

import os
import re
from typing import Any

_HEADER_RE = re.compile(r"^\s*l_[a-z_]+\s*:\s*$")
# key:0 "value"  /  key: "value"  /  key:12 "value" # comment
_ENTRY_RE = re.compile(r'^\s*([A-Za-z0-9_.\-\']+)\s*:\s*\d*\s*"(.*)"')
_VAR_RE = re.compile(r"\$([A-Za-z0-9_.\-]+)(\|[^$]*)?\$")
# $@scripted_variable$ or $@scripted_variable|%$ (value inserted from script)
_SCRIPT_VAR_RE = re.compile(r"\$(@[A-Za-z0-9_]+)(?:\|([^$]*))?\$")


def parse_localization_file(filepath: str) -> dict[str, str]:
    """Parse one localisation .yml file into {key: raw_text}."""
    entries: dict[str, str] = {}
    with open(filepath, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or _HEADER_RE.match(stripped):
                continue
            m = _ENTRY_RE.match(line)
            if not m:
                continue
            value = m.group(2)
            # The regex is greedy up to the last quote, which may belong to a
            # trailing comment: `key: "text" # see "foo"`
            comment = re.search(r'"\s+#', value)
            if comment:
                value = value[: comment.start()]
            entries[m.group(1)] = value
    return entries


class Localization:
    """All localisation strings for one language, with lookup helpers."""

    def __init__(self, stellaris_path: str, language: str = "english", variables: dict[str, Any] | None = None):
        self.entries: dict[str, str] = {}
        # Values for $@variable$ references, e.g. Variables(...).globals
        self.variables: dict[str, Any] = dict(variables or {})
        loc_dir = os.path.join(stellaris_path, "localisation", language)
        if not os.path.isdir(loc_dir):
            print(f"Warning: localisation directory not found: {loc_dir}")
            return

        # Files under replace/ override base strings, so load them last
        files, replace_files = [], []
        for root, _, names in os.walk(loc_dir):
            for name in sorted(names):
                if name.endswith(".yml"):
                    path = os.path.join(root, name)
                    is_replace = "replace" in os.path.relpath(root, loc_dir).split(os.sep)
                    (replace_files if is_replace else files).append(path)
        for path in sorted(files) + sorted(replace_files):
            self.entries.update(parse_localization_file(path))

    def __len__(self) -> int:
        return len(self.entries)

    def resolve(self, text: str, max_depth: int = 8) -> str:
        """Expand `$key$` / `$key|Y$` references to other localisation keys."""
        for _ in range(max_depth):
            changed = False

            def sub(m: re.Match) -> str:
                nonlocal changed
                key = m.group(1)
                if key in self.entries:
                    changed = True
                    return self.entries[key]
                return m.group(0)

            text = _VAR_RE.sub(sub, text)
            if not changed:
                break
        return text

    def get(self, key: str, default: str | None = None, clean: bool = True,
            local_vars: dict[str, Any] | None = None) -> str | None:
        """
        Look up a key, resolve references, and (by default) strip markup.
        `local_vars` supplies file-local @variables for $@variable$ references.
        """
        text = self.entries.get(key)
        if text is None:
            return default
        text = self.resolve(text)
        text = self.insert_variables(text, {**self.variables, **(local_vars or {})})
        return self.clean(text) if clean else text

    @staticmethod
    def insert_variables(text: str, variables: dict[str, Any]) -> str:
        def sub(m: re.Match) -> str:
            value = variables.get(m.group(1))
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return m.group(0)
            return format_number(value, m.group(2) or "")

        return _SCRIPT_VAR_RE.sub(sub, text)

    def name(self, key: str) -> str:
        """Display name for an id; falls back to a prettified id."""
        return self.get(key) or prettify_id(key)

    def description(self, key: str) -> str:
        return self.get(f"{key}_desc") or ""

    def clean(self, text: str) -> str:
        return clean_localized_text(text, self)


def format_number(value: float, fmt: str = "") -> str:
    """
    Format a number the way a localisation format suffix asks for:
    `%` multiplies by 100 and appends %, `+` forces a sign, a digit sets the
    number of decimals. Colour letters in the suffix (Y, G, R, ...) are ignored.
    """
    percent = "%" in fmt
    if percent:
        value = value * 100
    digits = next((int(c) for c in fmt if c.isdigit()), None)
    value = round(value, digits if digits is not None else 2)
    text = f"{value:.{digits}f}" if digits is not None else f"{value:g}"
    if "+" in fmt and value > 0:
        text = "+" + text
    return text + ("%" if percent else "")


def prettify_id(key: str) -> str:
    for prefix in ("trait_", "pc_"):
        if key.startswith(prefix):
            key = key[len(prefix):]
    return key.replace("_", " ").strip().title()


def clean_localized_text(text: str, loc: Localization | None = None) -> str:
    """Strip Stellaris markup and return plain text."""
    # Concept links: ['concept_foo', Display Text] -> Display Text
    text = re.sub(r"\['[^']*'\s*,\s*([^\]]+)\]", r"\1", text)

    # Concept links without display text: ['trait:trait_foo'] -> localised name
    def concept(m: re.Match) -> str:
        ref = m.group(1).split(":")[-1]
        if loc is not None:
            resolved = loc.get(ref)
            if resolved:
                return resolved
        return prettify_id(ref.removeprefix("concept_"))

    text = re.sub(r"\['([^']+)'\]", concept, text)

    # Scripted functions: [Root.GetSpeciesNamePlural] etc. have no static value
    text = re.sub(r"\[[^\]]*Get(Species)?Name(Plural|Adj)?[^\]]*\]", "this species", text)
    text = re.sub(r"\[[A-Za-z.]+\]", "", text)

    # Colour codes (§Y ... §!) and icons (£energy£, £pop|1£)
    text = re.sub(r"§.", "", text)
    text = re.sub(r"£[^£\s]+£", "", text)

    # Unresolved $VARIABLES$ / $@variables$
    text = _VAR_RE.sub("", text)
    text = _SCRIPT_VAR_RE.sub("", text)

    text = text.replace("\\n", "\n").replace('\\"', '"').replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
