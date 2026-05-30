from __future__ import annotations

from typing import Any

from plugins.base import (
    ToolPlugin,
    config_defaults,
    config_native_args,
    expand_short_flag_clusters,
    native_option_maps,
    read_value,
    split_passthrough,
    with_passthrough,
)


class TarPlugin(ToolPlugin):
    name = "tar"
    binary = "tar"
    spec_file = "tools/tar/spec.yaml"

    compression_flags = {"gzip": "-z", "bzip2": "-j", "xz": "-J", "lzma": "--lzma"}

    def build_args(self, argv: list[str], config: dict[str, Any]) -> list[str]:
        wrapper_args, passthrough = split_passthrough(argv)
        subcommands = self._subcommand_index()
        if not wrapper_args:
            raise ValueError(f"tar requires a subcommand: {', '.join(subcommands)}")

        subcommand_name = wrapper_args[0]
        subcommand = subcommands.get(subcommand_name)
        if not subcommand:
            raise ValueError(f"unknown tar subcommand: {subcommand_name}")
        if subcommand.get("positional") == "raw":
            return wrapper_args[1:] + passthrough

        values = self._default_values(config_defaults(config))
        paths = self._parse_options(wrapper_args[1:], values)
        for key, value in subcommand.get("set", {}).items():
            values[str(key)] = value
        if not values.get("file"):
            raise ValueError(f"tar {subcommand_name} requires --file")

        native = config_native_args(config)
        native.extend(str(arg) for arg in subcommand.get("native_args", []))
        native.extend(self._native_options(values))
        native.extend(passthrough)
        native.extend(paths)
        return native

    def _wrapper(self) -> dict[str, Any]:
        wrapper = self.spec.get("wrapper", {})
        if not isinstance(wrapper, dict):
            return {}
        return wrapper

    def _wrapper_options(self) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []
        for group in self._wrapper().get("option_groups", []):
            options.extend(group.get("options", []))
        return options

    def _option_index(self) -> dict[str, dict[str, Any]]:
        return {str(option["flag"]): option for option in self._wrapper_options()}

    def _subcommand_index(self) -> dict[str, dict[str, Any]]:
        return {
            str(subcommand["name"]): subcommand
            for subcommand in self._wrapper().get("subcommands", [])
            if subcommand.get("name")
        }

    def _option_key(self, option: dict[str, Any]) -> str:
        return str(option.get("key") or option["flag"][2:].replace("-", "_"))

    def _default_values(self, defaults: dict[str, Any]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for option in self._wrapper_options():
            key = self._option_key(option)
            if option.get("argument") is False:
                values[key] = bool(defaults.get(key, False))
            else:
                values[key] = defaults.get(key)
        return values

    def _parse_options(self, wrapper_args: list[str], values: dict[str, Any]) -> list[str]:
        options = self._option_index()
        paths: list[str] = []
        i = 0
        while i < len(wrapper_args):
            arg = wrapper_args[i]
            option = options.get(arg)
            if option:
                key = self._option_key(option)
                if option.get("argument") is False:
                    values[key] = True
                else:
                    value, i = read_value(wrapper_args, i, arg)
                    values[key] = value
            elif arg.startswith("--"):
                raise ValueError(f"unknown tar wrapper option: {arg}")
            else:
                paths.append(arg)
            i += 1
        return paths

    def _native_options(self, values: dict[str, Any]) -> list[str]:
        native: list[str] = []
        for option in self._wrapper_options():
            native_arg = option.get("native")
            if not native_arg:
                continue
            key = self._option_key(option)
            value = values.get(key)
            if native_arg == "template" and key == "compress":
                if value:
                    native.append(self._compress_flag(str(value)))
            elif option.get("argument") is False:
                if value:
                    native.append(str(native_arg))
            elif value:
                native.extend([str(native_arg), str(value)])
        return native

    def _compress_flag(self, kind: str) -> str:
        try:
            return self.compression_flags[kind]
        except KeyError as exc:
            choices = ", ".join(sorted(self.compression_flags))
            raise ValueError(f"unknown tar compression '{kind}'. Expected one of: {choices}") from exc

    def translate_native_args(self, argv: list[str]) -> list[str]:
        flags, options_with_values = native_option_maps(self.spec)
        native_args = expand_short_flag_clusters(
            argv,
            {**flags, **options_with_values, "-c": {}, "-x": {}, "-t": {}, "-z": {}, "-j": {}, "-J": {}},
        )
        mode = None
        wrapper_options: list[str] = []
        paths: list[str] = []
        native_passthrough: list[str] = []
        compression_by_flag = {"-z": "gzip", "-j": "bzip2", "-J": "xz", "--lzma": "lzma"}
        i = 0
        while i < len(native_args):
            arg = native_args[i]
            if arg in {"-c", "-x", "-t"}:
                mode = {"-c": "create", "-x": "extract", "-t": "list"}[arg]
            elif arg in compression_by_flag:
                wrapper_options.extend(["--compress", compression_by_flag[arg]])
            elif arg in flags:
                wrapper_options.append(str(flags[arg]["flag"]))
            elif arg in options_with_values:
                value, i = read_value(native_args, i, arg)
                wrapper_options.extend([str(options_with_values[arg]["flag"]), value])
            elif arg.startswith("-"):
                native_passthrough.append(arg)
            else:
                paths.append(arg)
            i += 1
        if not mode:
            raise ValueError("cannot translate tar command without -c, -x, or -t")
        return with_passthrough([mode, *wrapper_options, *paths], native_passthrough)


PLUGIN = TarPlugin()
