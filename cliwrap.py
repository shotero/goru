#!/usr/bin/env python3
"""Sample central wrapper for standardizing existing CLI tools."""

from __future__ import annotations

import subprocess
import shlex
import sys
import textwrap
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from plugins import REGISTRY
from yaml_loader import dump_yaml, load_yaml_file


ROOT = Path(__file__).resolve().parent
console = Console()
error_console = Console(stderr=True, style="bold red")


def print_yaml(payload: Any) -> None:
    print(dump_yaml(payload), end="")


def print_structured(payload: Any, output_format: str) -> None:
    print_yaml(payload)


def mapped_tool(plugin) -> dict[str, Any]:
    wrapper = plugin.spec.get("wrapper", {})
    if not isinstance(wrapper, dict):
        return {}
    return wrapper


def tool_metadata(plugin) -> dict[str, Any]:
    tool = plugin.spec.get("tool", {})
    if not isinstance(tool, dict):
        return {}
    return tool


def native_metadata(plugin) -> dict[str, Any]:
    native = plugin.spec.get("native", {})
    if not isinstance(native, dict):
        return {}
    return native


def flatten_option_groups(tool_map: dict[str, Any]) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for group in tool_map.get("option_groups", []):
        options.extend(group.get("options", []))
    return options


def usage() -> str:
    tools = ", ".join(sorted(REGISTRY))
    return "\n".join(
        [
            "Usage:",
            "  goru [--yaml] list",
            "  goru [--yaml] help <tool>",
            "  goru [--yaml] spec <tool>",
            "  goru [--yaml] validate-specs",
            "  goru [--yaml] translate [--to wrapper|native] <command...>",
            "  goru [--yaml] run <tool> [standard-options] [-- native-args...]",
            "",
            f"Tools: {tools}",
            "",
            "Standard behavior:",
            "  --yaml        Emit wrapper output in YAML for list/help/spec and errors.",
            "  --config PATH Read defaults from a YAML config file.",
            "  --help        Show wrapper or tool-specific help.",
        ]
    )


def emit_error(message: str, code: str = "usage_error", status: int = 2, output_format: str = "text") -> None:
    payload = {"error": {"code": code, "message": message}, "status": status}
    if output_format != "text":
        print_structured(payload, output_format)
    else:
        error_console.print(f"goru: {message}")
    raise click.exceptions.Exit(status)


def load_config(path: str | None, tool_name: str | None = None) -> dict[str, Any]:
    candidates: list[Path] = []
    if path:
        candidate = Path(path)
        if not candidate.exists():
            raise ValueError(f"config file not found: {path}")
        return load_yaml_file(candidate)
    elif tool_name:
        if tool_name == "ssh":
            candidates.append(Path.cwd() / "ssh-config.yaml")
        candidates.append(Path.cwd() / f"{tool_name}-config.yaml")
        candidates.append(ROOT / f"{tool_name}-config.yaml")

    for candidate in candidates:
        if candidate.exists():
            config = load_yaml_file(candidate)
            if candidate.name == "ssh-config.yaml" and not declares_ssh_config(config):
                continue
            return config
    return {}


def declares_ssh_config(config: dict[str, Any]) -> bool:
    return config.get("type") == "ssh_config" or config.get("kind") == "ssh_config" or config.get("tool") == "ssh"


def get_plugin(tool_name: str):
    plugin = REGISTRY.get(tool_name)
    if plugin is None:
        known = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown tool '{tool_name}'. Known tools: {known}")
    return plugin


def render_help(plugin) -> dict[str, Any]:
    tool_map = mapped_tool(plugin)
    tool = tool_metadata(plugin)
    native = native_metadata(plugin)
    subcommands = tool_map.get("subcommands", [])
    return {
        "tool": tool.get("name", plugin.name),
        "binary": tool.get("binary", plugin.binary),
        "summary": tool.get("summary"),
        "usage": tool_map.get("usage", native.get("usage", [])),
        "standard_options": flatten_option_groups(tool_map) or plugin.standard_options,
        "option_groups": tool_map.get("option_groups", []),
        "subcommands": subcommands or getattr(plugin, "subcommands", []),
        "native_option_groups": native.get("option_groups", []),
        "native_options_count": len(native.get("options", [])),
    }


def subcommand_index(plugin) -> dict[str, dict[str, Any]]:
    return {
        str(subcommand["name"]): subcommand
        for subcommand in mapped_tool(plugin).get("subcommands", [])
        if subcommand.get("name")
    }


def render_subcommand_help(plugin, subcommand_name: str) -> dict[str, Any]:
    subcommands = subcommand_index(plugin)
    subcommand = subcommands.get(subcommand_name)
    if not subcommand:
        known = ", ".join(sorted(subcommands))
        raise ValueError(f"unknown {plugin.name} subcommand: {subcommand_name}. Known subcommands: {known}")

    usage_line = subcommand["usage"]
    if not usage_line.startswith("goru "):
        usage_line = f"goru run {tool_metadata(plugin).get('name', plugin.name)} {usage_line}"

    required_keys = set(subcommand.get("required", []))
    required_options = [
        option
        for option in flatten_option_groups(mapped_tool(plugin))
        if option.get("key") in required_keys
    ]

    return {
        "tool": tool_metadata(plugin).get("name", plugin.name),
        "binary": tool_metadata(plugin).get("binary", plugin.binary),
        "subcommand": subcommand_name,
        "description": subcommand["description"],
        "usage": [usage_line],
        "required_options": required_options,
        "option_groups": mapped_tool(plugin).get("option_groups", []),
        "subcommand_metadata": subcommand,
    }


def print_help(plugin) -> None:
    help_doc = render_help(plugin)
    console.print(f"[bold cyan]{help_doc['tool']}[/bold cyan]: wrapper for [green]{help_doc['binary']}[/green]")
    if help_doc["summary"]:
        console.print(help_doc["summary"], style="dim")
    console.print("")
    console.print("Usage", style="bold")
    for line in help_doc["usage"]:
        print_wrapped_line(line, indent=2, style="bold")
    console.print("")
    if help_doc["option_groups"]:
        console.print("Standard options", style="bold")
        for group in help_doc["option_groups"]:
            console.print(f"  {group['name']}:", style="bold")
            for option in group.get("options", []):
                argument = f" {option['argument']}" if option.get("argument") else ""
                print_help_row(f"{option['flag']}{argument}", option["description"], "green")
    else:
        console.print("Standard options", style="bold")
        for option in help_doc["standard_options"]:
            argument = f" {option['argument']}" if option.get("argument") else ""
            print_help_row(f"{option['flag']}{argument}", option["description"], "green")
    if help_doc["subcommands"]:
        console.print("")
        console.print("Subcommands", style="bold")
        for subcommand in help_doc["subcommands"]:
            print_help_row(subcommand.get("usage", subcommand["name"]), subcommand["description"], "cyan")
    if help_doc["native_option_groups"]:
        console.print("")
        console.print("Native flags", style="bold")
        console.print(
            f"  Pass these after [bold]--[/bold] or use [bold]raw[/bold]. "
            f"{help_doc['native_options_count']} native options captured.",
            style="dim",
        )
        for group in help_doc["native_option_groups"]:
            print_native_flag_group(group["name"], group["summary"], group.get("flags", []))


def print_subcommand_help(plugin, subcommand_name: str) -> None:
    help_doc = render_subcommand_help(plugin, subcommand_name)
    console.print(
        f"[bold cyan]{help_doc['tool']} {help_doc['subcommand']}[/bold cyan]: "
        f"wrapper subcommand for [green]{help_doc['binary']}[/green]"
    )
    console.print(help_doc["description"], style="dim")
    console.print("")
    console.print("Usage", style="bold")
    for line in help_doc["usage"]:
        print_wrapped_line(line, indent=2, style="bold")

    if help_doc["required_options"]:
        console.print("")
        console.print("Required options", style="bold")
        for option in help_doc["required_options"]:
            argument = f" {option['argument']}" if option.get("argument") else ""
            print_help_row(f"{option['flag']}{argument}", option["description"], "green")

    if help_doc["option_groups"]:
        console.print("")
        console.print("Options", style="bold")
        for group in help_doc["option_groups"]:
            console.print(f"  {group['name']}:", style="bold")
            for option in group.get("options", []):
                argument = f" {option['argument']}" if option.get("argument") else ""
                print_help_row(f"{option['flag']}{argument}", option["description"], "green")


def print_help_row(term: str, description: str, style: str) -> None:
    left_width = max(len(term), 24)
    terminal_width = max(console.width, 60)
    if left_width > terminal_width - 18:
        term_text = Text("    ")
        term_text.append(term, style=style)
        console.print(term_text)
        description_width = max(terminal_width - 8, 20)
        for line in textwrap.wrap(description, width=description_width, break_on_hyphens=False) or [""]:
            console.print(Text(f"        {line}", style="dim"))
        return

    description_width = max(terminal_width - left_width - 6, 12)
    description_lines = textwrap.wrap(
        description,
        width=description_width,
        break_on_hyphens=False,
    ) or [""]

    first_line = Text("    ")
    first_line.append(term.ljust(left_width), style=style)
    first_line.append("  ")
    first_line.append(description_lines[0], style="dim")
    console.print(first_line)

    continuation_prefix = " " * (left_width + 6)
    for line in description_lines[1:]:
        console.print(Text(f"{continuation_prefix}{line}", style="dim"))


def print_native_flag_group(name: str, summary: str, flags: list[str]) -> None:
    title = Text("    ")
    title.append(name, style="magenta")
    console.print(title)

    width = max(console.width - 8, 40)
    for line in textwrap.wrap(summary, width=width, break_on_hyphens=False) or [""]:
        console.print(Text(f"        {line}", style="dim"))

    flag_text = ", ".join(flags)
    flag_lines = textwrap.wrap(f"Flags: {flag_text}", width=width, break_on_hyphens=False) or [""]
    for line in flag_lines:
        console.print(Text(f"        {line}", style="dim"))


def print_wrapped_line(value: str, indent: int, style: str) -> None:
    prefix = " " * indent
    width = max(console.width - indent, 40)
    if len(value) > width and " [-- " in value:
        command, passthrough = value.split(" [-- ", 1)
        wrapped_lines = [command, f"[-- {passthrough}"]
    else:
        wrapped_lines = textwrap.wrap(value, width=width, break_on_hyphens=False) or [""]
    for index, line in enumerate(wrapped_lines):
        continuation = "  " if index else ""
        console.print(Text(f"{prefix}{continuation}{line}", style=style))


def cmd_list(output_format: str) -> None:
    payload = {
        "tools": [
            {
                "name": tool_metadata(plugin).get("name", plugin.name),
                "binary": tool_metadata(plugin).get("binary", plugin.binary),
                "summary": tool_metadata(plugin).get("summary"),
                "standard_options": [
                    option["flag"]
                    for option in (flatten_option_groups(mapped_tool(plugin)) or plugin.standard_options)
                ],
                "subcommands": [
                    subcommand.get("name")
                    for subcommand in mapped_tool(plugin).get("subcommands", [])
                ],
            }
            for plugin in REGISTRY.values()
        ]
    }
    if output_format != "text":
        print_structured(payload, output_format)
    else:
        table = Table(title="Wrapped tools")
        table.add_column("Tool", style="bold cyan")
        table.add_column("Binary", style="green")
        table.add_column("Subcommands")
        table.add_column("Summary")
        for tool in payload["tools"]:
            table.add_row(
                tool["name"],
                tool["binary"],
                ", ".join(tool["subcommands"]) or "-",
                tool["summary"] or "",
            )
        console.print(table)


def cmd_help(tool_name: str | None, output_format: str) -> None:
    if not tool_name:
        if output_format != "text":
            print_structured({"usage": usage()}, output_format)
        else:
            console.print(Syntax(usage(), "text"))
        return
    plugin = get_plugin(tool_name)
    if output_format != "text":
        print_structured(render_help(plugin), output_format)
    else:
        print_help(plugin)


def cmd_spec(tool_name: str, output_format: str) -> None:
    plugin = get_plugin(tool_name)
    rendered = dump_yaml(plugin.spec)
    if output_format != "text":
        print_structured(plugin.spec, output_format)
    else:
        console.print(Syntax(rendered, "yaml"))


def cmd_validate_specs(output_format: str) -> None:
    payload = {
        "status": "ok",
        "specs": [
            {
                "tool": tool_metadata(plugin).get("name", plugin.name),
                "path": plugin.spec_file,
            }
            for plugin in REGISTRY.values()
        ],
    }
    if output_format != "text":
        print_structured(payload, output_format)
    else:
        for spec in payload["specs"]:
            console.print(f"[green]valid[/green] {spec['tool']} {spec['path']}")


def cmd_translate(command_args: tuple[str, ...], direction: str | None, output_format: str) -> None:
    tokens = parse_command_tokens(command_args)
    if not tokens:
        raise ValueError("translate requires a command")

    inferred_direction = direction or infer_translation_direction(tokens)
    if inferred_direction == "native":
        payload = translate_wrapper_to_native(tokens)
    elif inferred_direction == "wrapper":
        payload = translate_native_to_wrapper(tokens)
    else:
        raise ValueError("--to must be 'wrapper' or 'native'")

    if output_format != "text":
        print_structured(payload, output_format)
    else:
        click.echo(payload["command"])


def parse_command_tokens(command_args: tuple[str, ...]) -> list[str]:
    if len(command_args) == 1:
        return shlex.split(command_args[0])
    return list(command_args)


def infer_translation_direction(tokens: list[str]) -> str:
    if is_wrapper_command(tokens):
        return "native"
    first = Path(tokens[0]).name
    if any(first in plugin.native_binaries() for plugin in REGISTRY.values()):
        return "wrapper"
    raise ValueError("cannot infer translation direction; use --to wrapper or --to native")


def is_wrapper_command(tokens: list[str]) -> bool:
    first = Path(tokens[0]).name
    return first in {"goru", "cliwrap.py"} or first == "./goru"


def translate_wrapper_to_native(tokens: list[str]) -> dict[str, Any]:
    if not is_wrapper_command(tokens):
        raise ValueError("expected a wrapper command starting with ./goru, goru, or cliwrap.py")
    run_index = tokens.index("run") if "run" in tokens else -1
    if run_index < 0 or run_index + 1 >= len(tokens):
        raise ValueError("wrapper command must contain run <tool>")
    tool_name = tokens[run_index + 1]
    plugin = get_plugin(tool_name)
    wrapper_args = tokens[run_index + 2 :]
    command = plugin.build_command(wrapper_args, {})
    return {
        "direction": "native",
        "tool": tool_metadata(plugin).get("name", plugin.name),
        "argv": command,
        "command": shlex.join(command),
    }


def translate_native_to_wrapper(tokens: list[str]) -> dict[str, Any]:
    plugin = plugin_for_binary(tokens[0])
    if hasattr(plugin, "translate_native_command"):
        wrapper_args = plugin.translate_native_command(tokens)
    else:
        wrapper_args = plugin.translate_native_args(tokens[1:])
    command = ["./goru", "run", tool_metadata(plugin).get("name", plugin.name), *wrapper_args]
    return {
        "direction": "wrapper",
        "tool": tool_metadata(plugin).get("name", plugin.name),
        "argv": command,
        "command": shlex.join(command),
    }


def plugin_for_binary(binary: str):
    binary_name = Path(binary).name
    for plugin in REGISTRY.values():
        if binary_name in plugin.native_binaries():
            return plugin
    known = ", ".join(sorted(binary for plugin in REGISTRY.values() for binary in plugin.native_binaries()))
    raise ValueError(f"unknown native command '{binary}'. Known binaries: {known}")


def cmd_raw_help(plugin, output_format: str) -> None:
    raw_help_args = tool_metadata(plugin).get("raw_help_command", ["--help"])
    if not isinstance(raw_help_args, list) or not all(isinstance(arg, str) for arg in raw_help_args):
        raise ValueError(f"{plugin.name} raw_help_command must be a list of strings")

    command = [plugin.binary, *raw_help_args]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if output_format != "text":
        print_structured(
            {
                "tool": plugin.name,
                "command": command,
                "native_exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            output_format,
        )
        return

    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.stderr:
        click.echo(result.stderr, err=True, nl=False)


def cmd_run(tool_name: str, args: tuple[str, ...], config_path: str | None, output_format: str) -> None:
    plugin = get_plugin(tool_name)
    args = restore_passthrough_marker(tool_name, args)
    if not args or args in (("--help",), ("-h",)):
        if output_format != "text":
            print_structured(render_help(plugin), output_format)
        else:
            print_help(plugin)
        return
    subcommand_help = requested_subcommand_help(args)
    if subcommand_help:
        if output_format != "text":
            print_structured(render_subcommand_help(plugin, subcommand_help), output_format)
        else:
            print_subcommand_help(plugin, subcommand_help)
        return
    if args == ("--raw-help",):
        cmd_raw_help(plugin, output_format)
        return

    config = load_config(config_path, plugin.name)
    try:
        command = plugin.build_command(list(args), config)
    except ValueError as exc:
        emit_error(str(exc), output_format=output_format)

    try:
        if output_format != "text":
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            print_structured(
                {
                    "tool": plugin.name,
                    "command": command,
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
                output_format,
            )
            raise click.exceptions.Exit(result.returncode)
        click.echo("+ " + " ".join(command), err=True)
        raise click.exceptions.Exit(subprocess.call(command))
    finally:
        plugin.cleanup()


def restore_passthrough_marker(tool_name: str, args: tuple[str, ...]) -> tuple[str, ...]:
    if "--" in args or "--" not in sys.argv:
        return args
    raw = sys.argv[1:]
    for index, token in enumerate(raw):
        if token == "run" and index + 1 < len(raw) and raw[index + 1] == tool_name:
            return tuple(raw[index + 2 :])
    return args


def requested_subcommand_help(args: tuple[str, ...]) -> str | None:
    if not args or args[0].startswith("-"):
        return None
    wrapper_args = args[: args.index("--")] if "--" in args else args
    if any(arg in {"--help", "-h"} for arg in wrapper_args[1:]):
        return args[0]
    return None


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--yaml", "yaml_output", is_flag=True, help="Emit wrapper output in YAML.")
@click.option("--config", "config_path", type=click.Path(exists=False, dir_okay=False), help="Read defaults from a YAML config file.")
@click.pass_context
def main(ctx: click.Context, yaml_output: bool, config_path: str | None) -> None:
    """Standardized wrapper for supported CLI tools."""
    ctx.obj = {
        "output_format": "yaml" if yaml_output else "text",
        "config": config_path,
    }


@main.command("list")
@click.pass_context
def list_command(ctx: click.Context) -> None:
    """List available wrapped tools."""
    cmd_list(ctx.obj["output_format"])


@main.command("help")
@click.argument("tool_name", required=False)
@click.pass_context
def help_command(ctx: click.Context, tool_name: str | None) -> None:
    """Show wrapper or tool-specific help."""
    try:
        cmd_help(tool_name, ctx.obj["output_format"])
    except KeyError as exc:
        emit_error(str(exc).strip("'"), output_format=ctx.obj["output_format"])


@main.command("spec")
@click.argument("tool_name")
@click.pass_context
def spec_command(ctx: click.Context, tool_name: str) -> None:
    """Print a tool spec as YAML."""
    try:
        cmd_spec(tool_name, ctx.obj["output_format"])
    except KeyError as exc:
        emit_error(str(exc).strip("'"), output_format=ctx.obj["output_format"])


@main.command("validate-specs")
@click.pass_context
def validate_specs_command(ctx: click.Context) -> None:
    """Validate every tool spec against spec.schema.json."""
    try:
        cmd_validate_specs(ctx.obj["output_format"])
    except ValueError as exc:
        emit_error(str(exc), code="spec_validation_error", output_format=ctx.obj["output_format"])


@main.command("translate", context_settings={"ignore_unknown_options": True, "allow_extra_args": True, "help_option_names": []})
@click.option("--to", "direction", type=click.Choice(["wrapper", "native"]), required=False, help="Force translation direction.")
@click.argument("command_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def translate_command(ctx: click.Context, direction: str | None, command_args: tuple[str, ...]) -> None:
    """Translate between native commands and wrapper commands."""
    try:
        cmd_translate(command_args, direction, ctx.obj["output_format"])
    except (KeyError, ValueError) as exc:
        emit_error(str(exc).strip("'"), output_format=ctx.obj["output_format"])


@main.command("run", context_settings={"ignore_unknown_options": True, "allow_extra_args": True, "help_option_names": []})
@click.argument("tool_name")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def run_command(ctx: click.Context, tool_name: str, args: tuple[str, ...]) -> None:
    """Run a wrapped tool command."""
    try:
        cmd_run(tool_name, args, ctx.obj["config"], ctx.obj["output_format"])
    except KeyError as exc:
        emit_error(str(exc).strip("'"), output_format=ctx.obj["output_format"])
    except ValueError as exc:
        emit_error(str(exc), code="config_error", output_format=ctx.obj["output_format"])


if __name__ == "__main__":
    main()
