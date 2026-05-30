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


class TsharkPlugin(ToolPlugin):
    name = "tshark"
    binary = "tshark"
    spec_file = "tools/tshark/spec.yaml"

    def build_args(self, argv: list[str], config: dict[str, Any]) -> list[str]:
        wrapper_args, passthrough = split_passthrough(argv)
        subcommands = self._subcommand_index()
        if not wrapper_args:
            raise ValueError(f"tshark requires a subcommand: {', '.join(subcommands)}")

        subcommand_name = wrapper_args[0]
        subcommand = subcommands.get(subcommand_name)
        if not subcommand:
            raise ValueError(f"unknown tshark subcommand: {subcommand_name}")
        if subcommand.get("positional") == "raw":
            return wrapper_args[1:] + passthrough

        defaults = config_defaults(config)
        values = self._default_values(defaults)
        positionals = self._parse_options(wrapper_args[1:], values)
        self._apply_positionals(subcommand_name, subcommand, positionals, values, defaults)
        self._apply_subcommand_values(subcommand, values)
        self._validate(subcommand_name, subcommand, values)

        native = config_native_args(config)
        native.extend(self._template_args(subcommand.get("native_args", []), values))
        native.extend(self._native_options(values))
        native.extend(passthrough)
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
        values.setdefault("report", defaults.get("report", "fields"))
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
                raise ValueError(f"unknown tshark wrapper option: {arg}")
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
                raise ValueError(f"tshark {subcommand_name} does not accept positional arguments")
            return
        if mode == "single_source":
            if positionals and values.get("input"):
                raise ValueError(f"tshark {subcommand_name} accepts either --input or a positional file, not both")
            if len(positionals) > 1:
                raise ValueError(f"tshark {subcommand_name} accepts exactly one input file")
            if positionals:
                values["input"] = positionals[0]
            return
        if mode == "single_value":
            value_key = str(subcommand.get("value_key"))
            if len(positionals) > 1:
                raise ValueError(f"tshark {subcommand_name} accepts at most one argument")
            values[value_key] = positionals[0] if positionals else defaults.get(subcommand.get("default_key"), values.get(value_key))
            return
        raise ValueError(f"tshark subcommand '{subcommand_name}' has unsupported positional mode: {mode}")

    def _apply_subcommand_values(self, subcommand: dict[str, Any], values: dict[str, Any]) -> None:
        for key, value in subcommand.get("set", {}).items():
            values[str(key)] = value

    def _validate(self, subcommand_name: str, subcommand: dict[str, Any], values: dict[str, Any]) -> None:
        if subcommand.get("positional") == "single_source" and not values.get("input"):
            raise ValueError(f"tshark {subcommand_name} requires an input file")
        for key in subcommand.get("required", []):
            value = values.get(key)
            if value is None or value == [] or value is False:
                raise ValueError(f"tshark {subcommand_name} requires --{str(key).replace('_', '-')}")

    def _native_options(self, values: dict[str, Any]) -> list[str]:
        native: list[str] = []
        if values.get("read_filter"):
            native.append("-2")
        for option in self._wrapper_options():
            native_arg = option.get("native")
            if not native_arg:
                continue
            key = self._option_key(option)
            value = values.get(key)
            if native_arg == "template" and key == "duration":
                if value:
                    native.extend(["-a", f"duration:{value}"])
            elif option.get("repeatable"):
                for item in value or []:
                    native.extend([str(native_arg), str(item)])
            elif option.get("argument") is False:
                if value:
                    native.append(str(native_arg))
            elif value:
                native.extend([str(native_arg), str(value)])
        return native

    def _template_args(self, args: list[Any], values: dict[str, Any]) -> list[str]:
        return [str(arg).format(**values) for arg in args]

    def translate_native_args(self, argv: list[str]) -> list[str]:
        flags, options_with_values = native_option_maps(self.spec)
        wrapper_options: list[str] = []
        native_passthrough: list[str] = []
        report = None
        interfaces = False
        input_file = None
        output_format = None
        fields: list[str] = []
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg == "-D":
                interfaces = True
            elif arg == "-G":
                report, i = read_value(argv, i, arg)
            elif arg == "-r":
                input_file, i = read_value(argv, i, arg)
            elif arg == "-T":
                output_format, i = read_value(argv, i, arg)
                wrapper_options.extend(["--format", output_format])
            elif arg == "-e":
                field, i = read_value(argv, i, arg)
                fields.append(field)
                wrapper_options.extend(["--field", field])
            elif arg == "-E":
                value, i = read_value(argv, i, arg)
                wrapper_options.extend(["--field-option", value])
            elif arg == "-a":
                value, i = read_value(argv, i, arg)
                if value.startswith("duration:"):
                    wrapper_options.extend(["--duration", value.split(":", 1)[1]])
                else:
                    native_passthrough.extend(["-a", value])
            elif arg in flags:
                wrapper_options.append(str(flags[arg]["flag"]))
            elif arg in options_with_values:
                value, i = read_value(argv, i, arg)
                wrapper_options.extend([str(options_with_values[arg]["flag"]), value])
            elif arg.startswith("-"):
                native_passthrough.append(arg)
            else:
                native_passthrough.append(arg)
            i += 1

        if interfaces:
            return with_passthrough(["interfaces"], native_passthrough)
        if report is not None:
            return with_passthrough(["reports", report], native_passthrough)
        if input_file and output_format == "fields" and fields:
            return with_passthrough(["fields", input_file, *self._without_format_fields(wrapper_options)], native_passthrough)
        if input_file:
            return with_passthrough(["read", input_file, *wrapper_options], native_passthrough)
        return with_passthrough(["capture", *wrapper_options], native_passthrough)

    def _without_format_fields(self, args: list[str]) -> list[str]:
        cleaned: list[str] = []
        i = 0
        while i < len(args):
            if args[i] == "--format" and i + 1 < len(args) and args[i + 1] == "fields":
                i += 2
                continue
            cleaned.append(args[i])
            i += 1
        return cleaned


PLUGIN = TsharkPlugin()
