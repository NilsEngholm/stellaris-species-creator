"""
Paradox Script Parser

Parses Stellaris game files (Paradox Script, the `key = { ... }` format used
under common/) into plain Python dicts and lists.

Mapping rules:
  - `key = value`              -> {"key": value}
  - `key = { a b c }`          -> {"key": ["a", "b", "c"]}
  - `key = { x = 1 }`          -> {"key": {"x": 1}}
  - `key = {}`                 -> {"key": {}}
  - repeated keys              -> Repeated([v1, v2, ...])  (a list subclass, so
                                  it can be told apart from a real list value;
                                  use `get_all()` to read either shape)
  - `key > 5` (non-`=` ops)    -> {"key": {">": 5}}
  - mixed blocks `{ a b x = 1 }` -> {"x": 1, VALUES_KEY: ["a", "b"]}
  - `c = hsv { 0.1 0.2 0.3 }`  -> {"c": {"hsv": [0.1, 0.2, 0.3]}}
  - `yes`/`no`                 -> True/False, numbers -> int/float
  - `@var` references are kept as strings; resolve them with `Variables`.
"""

import os
import re
from collections.abc import Iterator
from typing import Any

# Bare values found in a block that otherwise has key = value pairs
VALUES_KEY = "__values__"

COLOR_SPACES = ("hsv", "hsv360", "rgb")

_TOKEN_RE = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<comment>\#[^\n]*)
    | (?P<string>"(?:[^"\\]|\\.)*"?)
    | (?P<math>@\[[^\]]*\])
    | (?P<op>==|!=|<=|>=|\?=|=|<|>)
    | (?P<brace>[{}])
    | (?P<word>[^\s{}=<>!?\#"]+|[!?])
    """,
    re.VERBOSE,
)

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+)$")


class Repeated(list):
    """All values of a key that appears more than once in the same block."""


class _Token:
    __slots__ = ("kind", "text")

    def __init__(self, kind: str, text: str):
        self.kind = kind
        self.text = text


def tokenize(text: str) -> list[_Token]:
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        value = m.group()
        if kind in ("ws", "comment"):
            continue
        if kind == "string":
            value = value[1:-1] if value.endswith('"') and len(value) > 1 else value[1:]
        tokens.append(_Token(kind, value))
    return tokens


def _convert_scalar(token: _Token) -> Any:
    if token.kind == "string":
        return token.text
    text = token.text
    if text == "yes":
        return True
    if text == "no":
        return False
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return text


class ParadoxParser:
    """Recursive-descent parser over a token list."""

    def __init__(self, text: str):
        self.tokens = tokenize(text)
        self.pos = 0

    def _peek(self, offset: int = 0) -> _Token | None:
        i = self.pos + offset
        return self.tokens[i] if i < len(self.tokens) else None

    def _next(self) -> _Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def parse(self) -> dict[str, Any]:
        result = self._parse_entries(top_level=True)
        return result if isinstance(result, dict) else {VALUES_KEY: result}

    def _parse_value(self) -> Any:
        token = self._next()
        if token.kind == "brace" and token.text == "{":
            return self._parse_entries(top_level=False)
        nxt = self._peek()
        if token.text.lower() in COLOR_SPACES and nxt is not None and nxt.text == "{":
            # `color = hsv { 0.5 0.2 0.8 }`
            self.pos += 1
            return {token.text.lower(): self._parse_entries(top_level=False)}
        return _convert_scalar(token)

    def _parse_entries(self, top_level: bool) -> dict[str, Any] | list[Any]:
        entries: dict[str, Any] = {}
        values: list[Any] = []

        while True:
            token = self._peek()
            if token is None:
                # End of file (an unclosed block is tolerated, like the game does)
                break
            if token.kind == "brace" and token.text == "}":
                self.pos += 1
                if top_level:
                    # Stray closing brace at top level (happens in vanilla files)
                    continue
                break

            nxt = self._peek(1)
            if token.kind == "brace":  # anonymous `{ ... }` inside a list
                self.pos += 1
                values.append(self._parse_entries(top_level=False))
            elif nxt is not None and nxt.kind == "op":
                key = token.text
                self.pos += 2
                if self._peek() is None:
                    break
                value = self._parse_value()
                if nxt.text != "=":
                    value = {nxt.text: value}
                _add(entries, key, value)
            elif nxt is not None and nxt.kind == "brace" and nxt.text == "{" and token.kind == "word":
                # `hsv { ... }` / `rgb { ... }` style: key directly followed by a block
                self.pos += 2
                _add(entries, token.text, self._parse_entries(top_level=False))
            else:
                self.pos += 1
                values.append(_convert_scalar(token))

        if values and not entries:
            return values
        if values:
            entries[VALUES_KEY] = values
        return entries


def _add(entries: dict[str, Any], key: str, value: Any) -> None:
    if key not in entries:
        entries[key] = value
    elif isinstance(entries[key], Repeated):
        entries[key].append(value)
    else:
        entries[key] = Repeated([entries[key], value])


def parse_text(text: str) -> dict[str, Any]:
    return ParadoxParser(text).parse()


def parse_stellaris_file(filepath: str) -> dict[str, Any]:
    """Parse a single Stellaris script file."""
    with open(filepath, encoding="utf-8-sig", errors="replace") as f:
        return parse_text(f.read())


def iter_script_files(directory: str) -> Iterator[str]:
    """Yield .txt files in a directory in game load order (sorted by name)."""
    if not os.path.isdir(directory):
        return
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if name.endswith(".txt") and os.path.isfile(path):
            yield path


def parse_directory(directory: str, skip_documentation: bool = True) -> dict[str, tuple[str, Any]]:
    """
    Parse every .txt file in a database directory and merge top-level entries.

    Returns {key: (source_filename, value)}. Later files override earlier ones,
    matching how the game loads databases. `@variables` are skipped.
    """
    merged: dict[str, tuple[str, Any]] = {}
    for path in iter_script_files(directory):
        filename = os.path.basename(path)
        if skip_documentation and "documentation" in filename:
            continue
        for key, value in parse_stellaris_file(path).items():
            if key.startswith("@") or key == VALUES_KEY:
                continue
            if isinstance(value, Repeated):
                value = value[-1]
            merged[key] = (filename, value)
    return merged


# --- Helpers for reading parsed data ---------------------------------------

def get_all(obj: Any, key: str) -> list[Any]:
    """All values for `key` in a parsed block, whether it appeared once or repeatedly."""
    if not isinstance(obj, dict) or key not in obj:
        return []
    value = obj[key]
    return list(value) if isinstance(value, Repeated) else [value]


def as_list(value: Any) -> list[Any]:
    """Normalise a `{ a b c }` / single value / missing value into a flat list."""
    if value is None or value == {}:
        return []
    if isinstance(value, Repeated):
        out = []
        for v in value:
            out.extend(as_list(v))
        return out
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return list(value.get(VALUES_KEY, []))
    return [value]


class Variables:
    """
    Resolves `@variable` references.

    Global variables come from common/scripted_variables/; file-local ones are
    the `@name = value` lines at the top of each script file and take
    precedence when passed as `local`.
    """

    def __init__(self, stellaris_path: str | None = None):
        self.globals: dict[str, Any] = {}
        if stellaris_path:
            for path in iter_script_files(os.path.join(stellaris_path, "common", "scripted_variables")):
                self.globals.update(self.locals_of(parse_stellaris_file(path)))

    @staticmethod
    def locals_of(parsed_file: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in parsed_file.items() if k.startswith("@")}

    def resolve(self, value: Any, local: dict[str, Any] | None = None, _depth: int = 0) -> Any:
        """Recursively replace @variables in a value (scalars, lists and dicts)."""
        if _depth > 10:
            return value
        if isinstance(value, str) and value.startswith("@"):
            if value.startswith("@["):
                return value  # inline math is left as-is
            if local and value in local:
                return self.resolve(local[value], local, _depth + 1)
            if value in self.globals:
                return self.resolve(self.globals[value], local, _depth + 1)
            return value
        if isinstance(value, Repeated):
            return Repeated(self.resolve(v, local, _depth) for v in value)
        if isinstance(value, list):
            return [self.resolve(v, local, _depth) for v in value]
        if isinstance(value, dict):
            return {k: self.resolve(v, local, _depth) for k, v in value.items()}
        return value


def to_json_safe(value: Any) -> Any:
    """Convert Repeated lists into plain lists so the result is JSON-serialisable."""
    if isinstance(value, dict):
        return {k: to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json_safe(v) for v in value]
    return value
