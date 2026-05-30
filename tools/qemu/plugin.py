from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.base import ToolPlugin, config_defaults, config_native_args, read_value, split_passthrough, with_passthrough


class QemuPlugin(ToolPlugin):
    name = "qemu"
    binary = "qemu-system-x86_64"
    spec_file = "tools/qemu/spec.yaml"

    def build_command(self, argv: list[str], config: dict[str, Any]) -> list[str]:
        wrapper_args, passthrough = split_passthrough(argv)
        subcommands = self._subcommand_index()
        if not wrapper_args:
            raise ValueError(f"qemu requires a subcommand: {', '.join(subcommands)}")

        subcommand_name = wrapper_args[0]
        subcommand = subcommands.get(subcommand_name)
        if not subcommand:
            raise ValueError(f"unknown qemu subcommand: {subcommand_name}")

        defaults = config_defaults(config)
        values = self._default_values(defaults)
        positionals = self._parse_options(wrapper_args[1:], values)
        binary = self._binary_for_arch(str(values["arch"]))

        if subcommand.get("positional") == "raw":
            return [binary, *config_native_args(config), *positionals, *passthrough]

        self._apply_positionals(subcommand_name, subcommand, positionals, values)
        self._apply_subcommand_values(subcommand, values)
        self._validate(subcommand_name, subcommand, values)

        native = config_native_args(config)
        native.extend(str(arg) for arg in subcommand.get("native_args", []))
        native.extend(self._native_options(values))
        native.extend(passthrough)
        return [binary, *native]

    def build_args(self, argv: list[str], config: dict[str, Any]) -> list[str]:
        command = self.build_command(argv, config)
        return command[1:]

    def native_binaries(self) -> set[str]:
        return set(self._binaries().values())

    def _wrapper(self) -> dict[str, Any]:
        wrapper = self.spec.get("wrapper", {})
        if not isinstance(wrapper, dict):
            return {}
        return wrapper

    def _binaries(self) -> dict[str, str]:
        tool = self.spec.get("tool", {})
        binaries = tool.get("binaries", {}) if isinstance(tool, dict) else {}
        if not isinstance(binaries, dict):
            return {}
        return {str(arch): str(binary) for arch, binary in binaries.items()}

    def _binary_for_arch(self, arch: str) -> str:
        binaries = self._binaries()
        binary = binaries.get(arch)
        if not binary:
            known = ", ".join(sorted(binaries))
            raise ValueError(f"unsupported qemu architecture '{arch}'. Known architectures: {known}")
        return binary

    def _arch_for_binary(self, binary: str) -> str:
        binary_name = Path(binary).name
        for arch, candidate in self._binaries().items():
            if binary_name == candidate:
                return arch
        known = ", ".join(sorted(self._binaries().values()))
        raise ValueError(f"unknown qemu binary '{binary_name}'. Known binaries: {known}")

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
        values: dict[str, Any] = {"arch": defaults.get("arch", "x86_64")}
        for option in self._wrapper_options():
            key = self._option_key(option)
            if option.get("repeatable"):
                default = defaults.get(key, [])
                values[key] = list(default if isinstance(default, list) else [default]) if default else []
            elif option.get("argument") is False:
                values[key] = bool(defaults.get(key, False))
            else:
                values[key] = defaults.get(key, values.get(key))
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
                raise ValueError(f"unknown qemu wrapper option: {arg}")
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
        if mode == "none":
            if positionals:
                raise ValueError(f"qemu {subcommand_name} does not accept positional arguments")
            return
        if mode == "single_image":
            value_key = str(subcommand.get("value_key", "disk"))
            if positionals and values.get(value_key):
                raise ValueError(
                    f"qemu {subcommand_name} accepts either --{value_key.replace('_', '-')} or a positional image, not both"
                )
            if len(positionals) > 1:
                raise ValueError(f"qemu {subcommand_name} accepts exactly one image")
            if positionals:
                values[value_key] = positionals[0]
            return
        raise ValueError(f"qemu subcommand '{subcommand_name}' has unsupported positional mode: {mode}")

    def _apply_subcommand_values(self, subcommand: dict[str, Any], values: dict[str, Any]) -> None:
        for key, value in subcommand.get("set", {}).items():
            values[str(key)] = value

    def _validate(self, subcommand_name: str, subcommand: dict[str, Any], values: dict[str, Any]) -> None:
        for key in subcommand.get("required", []):
            value = values.get(key)
            if value is None or value == [] or value is False:
                raise ValueError(f"qemu {subcommand_name} requires --{str(key).replace('_', '-')}")

    def _native_options(self, values: dict[str, Any]) -> list[str]:
        native: list[str] = []
        for option in self._wrapper_options():
            key = self._option_key(option)
            if key == "arch":
                continue
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
        if isinstance(native_arg, list):
            return [str(part).format(value=value) for part in native_arg]
        if native_arg and value is None:
            return [str(native_arg)]
        if native_arg:
            return [str(native_arg), str(value)]
        return []

    def translate_native_args(self, argv: list[str]) -> list[str]:
        if not argv:
            return ["run"]
        arch = None
        native_args = argv
        if Path(argv[0]).name in self.native_binaries():
            arch = self._arch_for_binary(argv[0])
            native_args = argv[1:]
        wrapper_options: list[str] = []
        passthrough: list[str] = []
        disk = None
        cdrom = None
        monitor_stdio = False
        i = 0
        while i < len(native_args):
            arg = native_args[i]
            if arg == "-m":
                value, i = read_value(native_args, i, arg)
                wrapper_options.extend(["--memory", value])
            elif arg == "-smp":
                value, i = read_value(native_args, i, arg)
                wrapper_options.extend(["--cpus", value])
            elif arg == "-cpu":
                value, i = read_value(native_args, i, arg)
                wrapper_options.extend(["--cpu", value])
            elif arg == "-machine":
                value, i = read_value(native_args, i, arg)
                wrapper_options.extend(["--machine", value])
            elif arg == "-accel":
                value, i = read_value(native_args, i, arg)
                wrapper_options.extend(["--accel", value])
            elif arg == "-name":
                value, i = read_value(native_args, i, arg)
                wrapper_options.extend(["--name", value])
            elif arg == "-cdrom":
                cdrom, i = read_value(native_args, i, arg)
                wrapper_options.extend(["--cdrom", cdrom])
            elif arg == "-drive":
                value, i = read_value(native_args, i, arg)
                path = self._extract_file_value(value)
                if path:
                    disk = path
                    wrapper_options.extend(["--disk", path])
                else:
                    passthrough.extend(["-drive", value])
            elif arg == "-nographic":
                wrapper_options.append("--headless")
            elif arg == "-monitor":
                value, i = read_value(native_args, i, arg)
                if value == "stdio":
                    monitor_stdio = True
                    wrapper_options.append("--monitor")
                else:
                    passthrough.extend(["-monitor", value])
            elif arg == "-netdev":
                value, i = read_value(native_args, i, arg)
                wrapper_options.extend(["--netdev", value])
            elif arg == "-device":
                value, i = read_value(native_args, i, arg)
                wrapper_options.extend(["--device", value])
            elif arg.startswith("-"):
                passthrough.append(arg)
            else:
                passthrough.append(arg)
            i += 1

        if arch:
            wrapper_options = ["--arch", arch, *wrapper_options]
        if cdrom and disk:
            subcommand = "install"
        elif monitor_stdio:
            subcommand = "monitor"
        elif disk:
            subcommand = "boot"
            wrapper_options = self._remove_option(wrapper_options, "--disk")
            return with_passthrough([subcommand, disk, *wrapper_options], passthrough)
        else:
            subcommand = "run"
        return with_passthrough([subcommand, *wrapper_options], passthrough)

    def translate_native_command(self, tokens: list[str]) -> list[str]:
        return self.translate_native_args(tokens)

    def _extract_file_value(self, value: str) -> str | None:
        for part in value.split(","):
            if part.startswith("file="):
                return part.split("=", 1)[1]
        return value if "," not in value else None

    def _remove_option(self, args: list[str], flag: str) -> list[str]:
        cleaned: list[str] = []
        i = 0
        while i < len(args):
            if args[i] == flag:
                i += 2
                continue
            cleaned.append(args[i])
            i += 1
        return cleaned


PLUGIN = QemuPlugin()
