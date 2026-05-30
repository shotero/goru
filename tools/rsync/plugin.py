from __future__ import annotations

from typing import Any

from plugins.base import (
    ToolPlugin,
    config_defaults,
    config_native_args,
    expand_known_short_flag_clusters,
    native_option_maps,
    native_short_flags,
    read_value,
    remove_options,
    split_passthrough,
    with_passthrough,
)


class RsyncPlugin(ToolPlugin):
    name = "rsync"
    binary = "rsync"
    spec_file = "tools/rsync/spec.yaml"

    def build_args(self, argv: list[str], config: dict[str, Any]) -> list[str]:
        wrapper_args, passthrough = split_passthrough(argv)
        subcommands = self._subcommand_index()
        if not wrapper_args:
            raise ValueError(f"rsync requires a subcommand: {', '.join(subcommands)}")

        subcommand_name = wrapper_args[0]
        subcommand = subcommands.get(subcommand_name)
        if not subcommand:
            raise ValueError(f"unknown rsync subcommand: {subcommand_name}")
        if subcommand.get("positional") == "raw":
            return wrapper_args[1:] + passthrough

        values = self._default_values(config_defaults(config))
        positionals = self._parse_options(wrapper_args[1:], values)
        self._apply_positionals(subcommand_name, subcommand, positionals, values)
        self._apply_subcommand_values(subcommand, values)
        self._validate(subcommand_name, subcommand, values)

        native = config_native_args(config)
        native.extend(str(arg) for arg in subcommand.get("native_args", []))
        native.extend(self._native_options(values))
        native.extend(passthrough)
        native.extend(str(source) for source in values.get("sources", []))
        if subcommand.get("positional") != "single_source":
            native.append(str(values["destination"]))
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
            if option.get("repeatable"):
                default = defaults.get(key, [])
                if default is None:
                    values[key] = []
                else:
                    values[key] = list(default if isinstance(default, list) else [default])
            elif option.get("argument") is False:
                values[key] = bool(defaults.get(key, False))
            else:
                values[key] = defaults.get(key)
        values.setdefault("sources", list(defaults.get("sources", [])))
        values.setdefault("destination", defaults.get("destination"))
        return values

    def _parse_options(self, wrapper_args: list[str], values: dict[str, Any]) -> list[str]:
        options = self._option_index()
        positionals: list[str] = []
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
                    if option.get("repeatable"):
                        values.setdefault(key, []).append(value)
                    else:
                        values[key] = value
            elif arg.startswith("--"):
                raise ValueError(f"unknown rsync wrapper option: {arg}")
            else:
                positionals.append(arg)
            i += 1
        return positionals

    def _apply_positionals(
        self,
        subcommand_name: str,
        subcommand: dict[str, Any],
        positionals: list[str],
        values: dict[str, Any],
    ) -> None:
        mode = subcommand.get("positional")
        if mode == "single_source":
            if positionals and values.get("sources"):
                raise ValueError(f"rsync {subcommand_name} accepts either --source or a positional source, not both")
            if positionals:
                values["sources"] = positionals
            return
        if mode == "sources_destination":
            if positionals:
                if values.get("destination"):
                    values.setdefault("sources", []).extend(positionals)
                elif values.get("sources") and len(positionals) == 1:
                    values["destination"] = positionals[0]
                else:
                    values.setdefault("sources", []).extend(positionals[:-1])
                    values["destination"] = positionals[-1]
            return
        raise ValueError(f"rsync subcommand '{subcommand_name}' has unsupported positional mode: {mode}")

    def _apply_subcommand_values(self, subcommand: dict[str, Any], values: dict[str, Any]) -> None:
        for key, value in subcommand.get("set", {}).items():
            values[str(key)] = value

    def _validate(self, subcommand_name: str, subcommand: dict[str, Any], values: dict[str, Any]) -> None:
        mode = subcommand.get("positional")
        sources = values.get("sources", [])
        if mode == "single_source" and len(sources) != 1:
            raise ValueError(f"rsync {subcommand_name} requires exactly one source")
        if mode == "sources_destination" and (not sources or not values.get("destination")):
            raise ValueError(f"rsync {subcommand_name} requires source ... destination")

    def _native_options(self, values: dict[str, Any]) -> list[str]:
        native: list[str] = []
        for option in self._wrapper_options():
            native_arg = option.get("native")
            if not native_arg or native_arg == "positional":
                continue

            key = self._option_key(option)
            value = values.get(key)
            if option.get("repeatable"):
                for item in value or []:
                    native.extend([str(native_arg), str(item)])
            elif option.get("argument") is False:
                if value:
                    native.append(str(native_arg))
            elif value:
                native.extend([str(native_arg), str(value)])
        return native

    def translate_native_args(self, argv: list[str]) -> list[str]:
        flags, options_with_values = native_option_maps(self.spec)
        native_args = expand_known_short_flag_clusters(argv, native_short_flags(self.spec))
        wrapper_options: list[str] = []
        positionals: list[str] = []
        native_passthrough: list[str] = []
        saw_delete = False
        saw_preview = False
        saw_list = False
        i = 0
        while i < len(native_args):
            arg = native_args[i]
            if arg == "--list-only":
                saw_list = True
            elif arg == "--itemize-changes":
                saw_preview = True
            elif arg == "--del":
                saw_delete = True
                wrapper_options.append("--delete")
            elif arg in flags:
                if arg == "-n":
                    saw_preview = True
                wrapper_options.append(str(flags[arg]["flag"]))
            elif arg in options_with_values:
                value, i = read_value(native_args, i, arg)
                wrapper_options.extend([str(options_with_values[arg]["flag"]), value])
            elif arg.startswith("-"):
                native_passthrough.append(arg)
            else:
                positionals.append(arg)
            i += 1

        if saw_list:
            subcommand = "list"
        elif saw_preview:
            subcommand = "preview"
            wrapper_options = remove_options(wrapper_options, {"--dry-run"})
        elif saw_delete and "--archive" in wrapper_options:
            subcommand = "mirror"
            wrapper_options = remove_options(wrapper_options, {"--archive", "--delete"})
        else:
            subcommand = "copy"
        return with_passthrough([subcommand, *positionals, *wrapper_options], native_passthrough)


PLUGIN = RsyncPlugin()
