from __future__ import annotations

from typing import Any

from plugins.base import (
    ToolPlugin,
    config_defaults,
    config_native_args,
    native_option_maps,
    read_value,
    split_passthrough,
    with_passthrough,
)


class NodePlugin(ToolPlugin):
    name = "node"
    binary = "node"
    spec_file = "tools/node/spec.yaml"

    def build_args(self, argv: list[str], config: dict[str, Any]) -> list[str]:
        wrapper_args, passthrough = split_passthrough(argv)
        subcommands = self._subcommand_index()
        if not wrapper_args:
            raise ValueError(f"node requires a subcommand: {', '.join(subcommands)}")

        subcommand_name = wrapper_args[0]
        subcommand = subcommands.get(subcommand_name)
        if not subcommand:
            raise ValueError(f"unknown node subcommand: {subcommand_name}")
        if subcommand.get("positional") == "raw":
            return wrapper_args[1:] + passthrough

        defaults = config_defaults(config)
        values = self._default_values(defaults)
        positionals = self._parse_options(wrapper_args[1:], values)
        self._apply_positionals(subcommand_name, subcommand, positionals, values, defaults)
        self._apply_subcommand_values(subcommand, values)
        self._validate(subcommand_name, subcommand, values)

        native = config_native_args(config)
        native.extend(self._native_options(values))
        native.extend(self._template_args(subcommand.get("native_args", []), values))
        native.extend(passthrough)
        native.extend(str(arg) for arg in values.get("script_args", []))
        native.extend(str(source) for source in values.get("sources", []))
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
                values[key] = list(default if isinstance(default, list) else [default]) if default else []
            elif option.get("argument") is False:
                values[key] = bool(defaults.get(key, False))
            else:
                values[key] = defaults.get(key)
        values.setdefault("script_args", list(defaults.get("script_args", [])))
        values.setdefault("sources", list(defaults.get("sources", [])))
        return values

    def _parse_options(self, wrapper_args: list[str], values: dict[str, Any]) -> list[str]:
        options = self._option_index()
        positionals: list[str] = []
        i = 0
        while i < len(wrapper_args):
            arg = wrapper_args[i]
            option = options.get(arg)
            if positionals:
                positionals.append(arg)
            elif option:
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
                raise ValueError(f"unknown node wrapper option: {arg}")
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
        defaults: dict[str, Any],
    ) -> None:
        mode = subcommand.get("positional")
        if mode == "none":
            if positionals:
                raise ValueError(f"node {subcommand_name} does not accept positional arguments")
            return
        if mode == "sources":
            if positionals:
                values.setdefault("sources", []).extend(positionals)
            return
        if mode == "script_args":
            if positionals:
                values.setdefault("script_args", []).extend(positionals)
            return
        if mode == "single_value":
            value_key = str(subcommand.get("value_key"))
            if len(positionals) > 1:
                raise ValueError(f"node {subcommand_name} accepts at most one argument")
            values[value_key] = positionals[0] if positionals else defaults.get(subcommand.get("default_key"), values.get(value_key))
            return
        raise ValueError(f"node subcommand '{subcommand_name}' has unsupported positional mode: {mode}")

    def _apply_subcommand_values(self, subcommand: dict[str, Any], values: dict[str, Any]) -> None:
        for key, value in subcommand.get("set", {}).items():
            values[str(key)] = value

    def _validate(self, subcommand_name: str, subcommand: dict[str, Any], values: dict[str, Any]) -> None:
        if subcommand.get("positional") == "script_args" and not values.get("script_args"):
            raise ValueError(f"node {subcommand_name} requires a script or target")
        for key in subcommand.get("required", []):
            value = values.get(key)
            if value is None or value == [] or value is False:
                raise ValueError(f"node {subcommand_name} requires --{str(key).replace('_', '-')}")

    def _native_options(self, values: dict[str, Any]) -> list[str]:
        native: list[str] = []
        for option in self._wrapper_options():
            key = self._option_key(option)
            value = values.get(key)
            native_arg = option.get("native")
            template = option.get("template")
            if option.get("repeatable"):
                for item in value or []:
                    native.extend(self._native_value(native_arg, template, item))
            elif option.get("argument") is False:
                if value:
                    native.extend(self._native_value(native_arg, template, None))
            elif value:
                native.extend(self._native_value(native_arg, template, value))
        return native

    def _native_value(self, native_arg: Any, template: Any, value: Any) -> list[str]:
        if isinstance(template, list):
            return [str(part).format(value=value) for part in template]
        if native_arg and value is None:
            return [str(native_arg)]
        if native_arg:
            return [str(native_arg), str(value)]
        return []

    def _template_args(self, args: list[Any], values: dict[str, Any]) -> list[str]:
        return [str(arg).format(**values) for arg in args]

    def translate_native_args(self, argv: list[str]) -> list[str]:
        flags, options_with_values = native_option_maps(self.spec)
        subcommands = self._subcommand_index()
        native_subcommands = self._native_subcommand_index(subcommands)
        wrapper_options: list[str] = []
        passthrough: list[str] = []
        positionals: list[str] = []
        mode = self._default_subcommand_name(subcommands)
        i = 0
        while i < len(argv):
            arg = argv[i]
            if positionals:
                positionals.append(arg)
                i += 1
                continue
            split_value = self._split_long_value(arg)
            compact_value = self._split_compact_value(arg, options_with_values)
            if split_value and split_value[0] in options_with_values:
                flag, value = split_value
                wrapper_options.extend([str(options_with_values[flag]["flag"]), value])
            elif arg in native_subcommands:
                mode, value_key = native_subcommands[arg]
                if value_key:
                    value, i = read_value(argv, i, arg)
                    positionals.append(value)
            elif arg in options_with_values:
                value, i = read_value(argv, i, arg)
                wrapper_options.extend([str(options_with_values[arg]["flag"]), value])
            elif arg in flags:
                wrapper_options.append(str(flags[arg]["flag"]))
            elif compact_value:
                flag, value = compact_value
                wrapper_options.extend([str(options_with_values[flag]["flag"]), value])
            elif arg.startswith("-"):
                passthrough.append(arg)
            else:
                positionals.append(arg)
            i += 1
        return with_passthrough([mode, *wrapper_options, *positionals], passthrough)

    def _native_subcommand_index(self, subcommands: dict[str, dict[str, Any]]) -> dict[str, tuple[str, str | None]]:
        native_subcommands: dict[str, tuple[str, str | None]] = {}
        for name, subcommand in subcommands.items():
            native_args = subcommand.get("native_args", [])
            if len(native_args) == 1:
                native_subcommands[str(native_args[0])] = (name, None)
            elif len(native_args) == 2 and str(native_args[1]).startswith("{") and str(native_args[1]).endswith("}"):
                native_subcommands[str(native_args[0])] = (name, str(native_args[1]).strip("{}"))
        return native_subcommands

    def _default_subcommand_name(self, subcommands: dict[str, dict[str, Any]]) -> str:
        for name, subcommand in subcommands.items():
            if not subcommand.get("native_args") and subcommand.get("positional") != "raw":
                return name
        return next(iter(subcommands))

    def _split_long_value(self, arg: str) -> tuple[str, str] | None:
        if not arg.startswith("--") or "=" not in arg:
            return None
        flag, value = arg.split("=", 1)
        return flag, value

    def _split_compact_value(
        self,
        arg: str,
        options_with_values: dict[str, dict[str, Any]],
    ) -> tuple[str, str] | None:
        for flag in sorted(options_with_values, key=len, reverse=True):
            if arg.startswith(flag) and len(arg) > len(flag):
                return flag, arg[len(flag) :]
        return None


PLUGIN = NodePlugin()
