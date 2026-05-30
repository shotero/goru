from __future__ import annotations

import tempfile
from pathlib import Path
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


class SshPlugin(ToolPlugin):
    name = "ssh"
    binary = "ssh"
    spec_file = "tools/ssh/spec.yaml"
    ssh_config_keys = {
        "add_keys_to_agent": "AddKeysToAgent",
        "batch_mode": "BatchMode",
        "canonicalize_hostname": "CanonicalizeHostname",
        "certificate_file": "CertificateFile",
        "check_host_ip": "CheckHostIP",
        "compression": "Compression",
        "connect_timeout": "ConnectTimeout",
        "control_master": "ControlMaster",
        "control_path": "ControlPath",
        "control_persist": "ControlPersist",
        "dynamic_forward": "DynamicForward",
        "escape_char": "EscapeChar",
        "forward_agent": "ForwardAgent",
        "forward_x11": "ForwardX11",
        "host_key_alias": "HostKeyAlias",
        "hostname": "HostName",
        "identity_file": "IdentityFile",
        "identities_only": "IdentitiesOnly",
        "local_forward": "LocalForward",
        "log_level": "LogLevel",
        "password_authentication": "PasswordAuthentication",
        "port": "Port",
        "preferred_authentications": "PreferredAuthentications",
        "proxy_command": "ProxyCommand",
        "proxy_jump": "ProxyJump",
        "remote_command": "RemoteCommand",
        "remote_forward": "RemoteForward",
        "request_tty": "RequestTTY",
        "send_env": "SendEnv",
        "server_alive_interval": "ServerAliveInterval",
        "server_alive_count_max": "ServerAliveCountMax",
        "strict_host_key_checking": "StrictHostKeyChecking",
        "user": "User",
        "user_known_hosts_file": "UserKnownHostsFile",
        "verify_host_key_dns": "VerifyHostKeyDNS",
    }

    def __init__(self) -> None:
        self._temp_paths: list[Path] = []

    def build_args(self, argv: list[str], config: dict[str, Any]) -> list[str]:
        wrapper_args, passthrough = split_passthrough(argv)
        subcommands = self._subcommand_index()
        if not wrapper_args:
            raise ValueError(f"ssh requires a subcommand: {', '.join(subcommands)}")

        subcommand_name = wrapper_args[0]
        subcommand = subcommands.get(subcommand_name)
        if not subcommand:
            raise ValueError(f"unknown ssh subcommand: {subcommand_name}")
        if subcommand.get("positional") == "raw":
            return wrapper_args[1:] + passthrough

        defaults = config_defaults(config)
        values = self._default_values(defaults)
        positionals = self._parse_options(wrapper_args[1:], values)
        command = self._apply_positionals(subcommand_name, subcommand, positionals, passthrough, values, defaults)
        self._validate(subcommand_name, subcommand, values, command)

        native = self._base_native_args(subcommand, config)
        if subcommand.get("connection_options", True) is not False:
            native.extend(self._native_options(values))
        native.extend(self._template_args(subcommand.get("native_args", []), values))

        destination = values.get("destination")
        if subcommand.get("passthrough") == "before_destination":
            native.extend(passthrough)
        if destination:
            native.append(str(destination))
        if command:
            native.extend(command)
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
                    values[key] = value
            elif arg.startswith("--"):
                raise ValueError(f"unknown ssh wrapper option: {arg}")
            else:
                positionals.append(arg)
            i += 1
        return positionals

    def _apply_positionals(
        self,
        subcommand_name: str,
        subcommand: dict[str, Any],
        positionals: list[str],
        passthrough: list[str],
        values: dict[str, Any],
        defaults: dict[str, Any],
    ) -> list[str]:
        mode = subcommand.get("positional")
        if mode == "destination":
            self._set_destination(subcommand_name, positionals, values)
            if positionals:
                raise ValueError(f"ssh {subcommand_name} accepts only one destination positional argument")
            return []
        if mode == "destination_command":
            self._set_destination(subcommand_name, positionals, values)
            return passthrough or positionals
        if mode == "single_value":
            value_key = str(subcommand.get("value_key"))
            if len(positionals) > 1:
                raise ValueError(f"ssh {subcommand_name} accepts exactly one argument")
            values[value_key] = positionals[0] if positionals else defaults.get(subcommand.get("default_key"))
            if passthrough:
                raise ValueError(f"ssh {subcommand_name} does not accept passthrough arguments")
            return []
        raise ValueError(f"ssh subcommand '{subcommand_name}' has unsupported positional mode: {mode}")

    def _set_destination(self, subcommand_name: str, positionals: list[str], values: dict[str, Any]) -> None:
        if not values.get("destination") and positionals:
            values["destination"] = positionals.pop(0)
        elif values.get("destination") and positionals and subcommand_name != "exec":
            raise ValueError(f"ssh {subcommand_name} accepts either --destination or a positional destination, not both")

    def _validate(
        self,
        subcommand_name: str,
        subcommand: dict[str, Any],
        values: dict[str, Any],
        command: list[str],
    ) -> None:
        if subcommand.get("positional") == "destination" and not values.get("destination"):
            raise ValueError(f"ssh {subcommand_name} requires <destination> or --destination")
        if subcommand.get("positional") == "destination" and subcommand_name == "connect" and command:
            raise ValueError("ssh connect does not accept remote command arguments; use ssh exec")
        if subcommand.get("command") == "required" and not command:
            raise ValueError(f"ssh {subcommand_name} requires a command after -- or after the destination")
        for key in subcommand.get("required", []):
            if not values.get(key):
                raise ValueError(f"ssh {subcommand_name} requires --{str(key).replace('_', '-')}")
        if subcommand.get("positional") == "single_value":
            value_key = str(subcommand.get("value_key"))
            if not values.get(value_key):
                raise ValueError(f"ssh {subcommand_name} requires an argument")

    def _base_native_args(self, subcommand: dict[str, Any], config: dict[str, Any]) -> list[str]:
        if subcommand.get("connection_options", True) is False:
            return []
        native = config_native_args(config)
        ssh_config_path = self._native_ssh_config_path(config)
        if ssh_config_path:
            native.extend(["-F", ssh_config_path])
        return native

    def _native_options(self, values: dict[str, Any]) -> list[str]:
        native: list[str] = []
        for option in self._wrapper_options():
            native_arg = option.get("native")
            if not native_arg or native_arg in {"positional", "template"}:
                continue
            key = self._option_key(option)
            value = values.get(key)
            if option.get("argument") is False:
                if value:
                    native.append(str(native_arg))
            elif value:
                native.extend([str(native_arg), str(value)])
        return native

    def _template_args(self, args: list[Any], values: dict[str, Any]) -> list[str]:
        return [str(arg).format(**values) for arg in args]

    def cleanup(self) -> None:
        for path in self._temp_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self._temp_paths.clear()

    def _native_ssh_config_path(self, config: dict[str, Any]) -> str | None:
        if not self._is_ssh_config(config):
            return None
        rendered = self._render_ssh_config(config)
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, prefix="goru-ssh-", suffix=".config")
        with handle:
            handle.write(rendered)
        path = Path(handle.name)
        self._temp_paths.append(path)
        return str(path)

    def _is_ssh_config(self, config: dict[str, Any]) -> bool:
        return config.get("tool") == "ssh" and config.get("type") == "config"

    def _render_ssh_config(self, config: dict[str, Any]) -> str:
        lines = ["# Generated by goru from YAML ssh config"]
        global_options = config.get("global", {})
        if global_options:
            if not isinstance(global_options, dict):
                raise ValueError("ssh config 'global' must be a mapping")
            lines.extend(self._render_options(global_options))
            lines.append("")

        hosts = config.get("hosts", [])
        if isinstance(hosts, dict):
            host_items = [{"host": host, **options} for host, options in hosts.items()]
        elif isinstance(hosts, list):
            host_items = hosts
        else:
            raise ValueError("ssh config 'hosts' must be a mapping or list")

        for host in host_items:
            if not isinstance(host, dict):
                raise ValueError("each ssh config host must be a mapping")
            patterns = host.get("host") or host.get("name") or host.get("patterns")
            if not patterns:
                raise ValueError("each ssh config host requires 'host', 'name', or 'patterns'")
            if isinstance(patterns, list):
                host_patterns = " ".join(str(pattern) for pattern in patterns)
            else:
                host_patterns = str(patterns)
            lines.append(f"Host {host_patterns}")
            options = {key: value for key, value in host.items() if key not in {"host", "name", "patterns"}}
            lines.extend(f"  {line}" for line in self._render_options(options))
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _render_options(self, options: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        for key, value in options.items():
            native_key = self._native_config_key(key)
            if isinstance(value, list):
                for item in value:
                    lines.append(f"{native_key} {self._native_config_value(item)}")
            elif isinstance(value, dict):
                raise ValueError(f"ssh config option '{key}' must not be a nested mapping")
            else:
                lines.append(f"{native_key} {self._native_config_value(value)}")
        return lines

    def _native_config_key(self, key: str) -> str:
        normalized = key.replace("-", "_")
        if normalized in self.ssh_config_keys:
            return self.ssh_config_keys[normalized]
        return "".join(part.capitalize() for part in normalized.split("_"))

    def _native_config_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "yes" if value else "no"
        return str(value)

    def translate_native_args(self, argv: list[str]) -> list[str]:
        flags, options_with_values = native_option_maps(self.spec)
        wrapper_options: list[str] = []
        positionals: list[str] = []
        native_passthrough: list[str] = []
        query = None
        config = False
        no_command = False
        local_forward = None
        socks_listen = None
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg == "-Q":
                query, i = read_value(argv, i, arg)
            elif arg == "-G":
                config = True
            elif arg == "-N":
                no_command = True
            elif arg == "-L":
                local_forward, i = read_value(argv, i, arg)
            elif arg == "-D":
                socks_listen, i = read_value(argv, i, arg)
            elif arg in flags:
                wrapper_options.append(str(flags[arg]["flag"]))
            elif arg in options_with_values:
                value, i = read_value(argv, i, arg)
                wrapper_options.extend([str(options_with_values[arg]["flag"]), value])
            elif arg.startswith("-"):
                if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                    native_passthrough.extend([arg, argv[i + 1]])
                    i += 1
                else:
                    native_passthrough.append(arg)
            else:
                positionals.append(arg)
            i += 1

        if query is not None:
            return ["query", query]
        if not positionals:
            raise ValueError("cannot translate ssh command without a destination")
        destination = positionals[0]
        remote_command = positionals[1:]
        if config:
            return with_passthrough(["config", destination, *wrapper_options], native_passthrough)
        if local_forward:
            local, remote = self._split_local_forward(local_forward)
            return with_passthrough(["tunnel", destination, "--local", local, "--remote", remote, *wrapper_options], native_passthrough)
        if socks_listen:
            return with_passthrough(["socks", destination, "--listen", socks_listen, *wrapper_options], native_passthrough)
        if remote_command and not no_command:
            return with_passthrough(["exec", destination, *wrapper_options, "--", *remote_command], native_passthrough)
        return with_passthrough(["connect", destination, *wrapper_options], native_passthrough)

    def _split_local_forward(self, value: str) -> tuple[str, str]:
        parts = value.split(":", 1)
        if len(parts) != 2:
            raise ValueError("cannot translate ssh -L value; expected LOCAL:HOST:PORT")
        return parts[0], parts[1]


PLUGIN = SshPlugin()
