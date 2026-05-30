from __future__ import annotations

from pathlib import Path
from typing import Any

from yaml_loader import load_yaml_file
from spec_validation import validate_tool_spec


ROOT = Path(__file__).resolve().parent.parent


class ToolPlugin:
    name = ""
    binary = ""
    spec_file = ""
    standard_options: list[dict[str, Any]] = []

    @property
    def spec(self) -> dict[str, Any]:
        path = ROOT / self.spec_file
        spec = load_yaml_file(path)
        validate_tool_spec(spec, path)
        return spec

    def build_args(self, argv: list[str], config: dict[str, Any]) -> list[str]:
        raise NotImplementedError

    def translate_native_args(self, argv: list[str]) -> list[str]:
        raise NotImplementedError(f"{self.name} does not support native-to-wrapper translation")

    def cleanup(self) -> None:
        pass


def split_passthrough(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" not in argv:
        return argv, []
    index = argv.index("--")
    return argv[:index], argv[index + 1 :]


def read_value(argv: list[str], index: int, flag: str) -> tuple[str, int]:
    next_index = index + 1
    if next_index >= len(argv):
        raise ValueError(f"{flag} requires a value")
    return argv[next_index], next_index


def config_defaults(config: dict[str, Any]) -> dict[str, Any]:
    defaults = config.get("defaults", {})
    if defaults is None:
        return {}
    if not isinstance(defaults, dict):
        raise ValueError("config 'defaults' must be an object")
    return defaults


def config_native_args(config: dict[str, Any]) -> list[str]:
    args = config.get("native_args", [])
    if args is None:
        return []
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise ValueError("config 'native_args' must be a list of strings")
    return args


def wrapper_options(spec: dict[str, Any]) -> list[dict[str, Any]]:
    wrapper = spec.get("wrapper", {})
    if not isinstance(wrapper, dict):
        return []
    options: list[dict[str, Any]] = []
    for group in wrapper.get("option_groups", []):
        options.extend(group.get("options", []))
    return options


def native_option_maps(spec: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    flags: dict[str, dict[str, Any]] = {}
    options_with_values: dict[str, dict[str, Any]] = {}
    for option in wrapper_options(spec):
        native = option.get("native")
        if not isinstance(native, str) or native in {"positional", "template"}:
            continue
        if option.get("argument") is False:
            flags[native] = option
        else:
            options_with_values[native] = option
    return flags, options_with_values


def expand_short_flag_clusters(args: list[str], known_flags: dict[str, dict[str, Any]]) -> list[str]:
    expanded: list[str] = []
    for arg in args:
        if len(arg) > 2 and arg.startswith("-") and not arg.startswith("--"):
            pieces = [f"-{char}" for char in arg[1:]]
            if all(piece in known_flags for piece in pieces):
                expanded.extend(pieces)
                continue
        expanded.append(arg)
    return expanded


def native_short_flags(spec: dict[str, Any]) -> set[str]:
    native = spec.get("native", {})
    if not isinstance(native, dict):
        return set()
    flags: set[str] = set()
    for option in native.get("options", []):
        flag = option.get("flag")
        if isinstance(flag, str) and len(flag) == 2 and flag.startswith("-"):
            flags.add(flag)
    return flags


def expand_known_short_flag_clusters(args: list[str], valid_flags: set[str]) -> list[str]:
    expanded: list[str] = []
    for arg in args:
        if len(arg) > 2 and arg.startswith("-") and not arg.startswith("--"):
            pieces = [f"-{char}" for char in arg[1:]]
            invalid = [piece for piece in pieces if piece not in valid_flags]
            if invalid:
                raise ValueError(f"unknown short option in cluster {arg}: {invalid[0]}")
            expanded.extend(pieces)
            continue
        expanded.append(arg)
    return expanded


def remove_options(args: list[str], flags: set[str]) -> list[str]:
    cleaned: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in flags:
            i += 1
            continue
        cleaned.append(arg)
        i += 1
    return cleaned


def with_passthrough(wrapper_args: list[str], passthrough: list[str]) -> list[str]:
    if not passthrough:
        return wrapper_args
    return [*wrapper_args, "--", *passthrough]
