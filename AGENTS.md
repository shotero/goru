# Standard for CLI Applications

CLI applications evolve organically and often vary wildly from one application to another for similar options. We aim to create a simple wrapper to standardize common and similar options for CLI applications. These include:

1. Standardize help and usage switch `--help`
2. Standardize error number and error format
3. Configurable via `<toolname>-config.yaml` file
4. Accept `--yaml` switch for output
5. Use flat standardized subcommands
6. Rename difficult and nonstandard flags to a common name
7. Absence of a required argument should show help or a clear standardized error
8. Color output by default

## Current Structure

- `cliwrap.py`: generic root CLI. Owns root command routing, output formatting, config loading, command execution, and generic translation routing.
- `goru`: launcher script. Uses `venv/bin/python` when available.
- `plugins/base.py`: shared plugin interface and helper functions.
- `plugins/__init__.py`: plugin registry.
- `tools/<tool>/plugin.py`: tool-specific logic, including wrapper-to-native arg mapping and native-to-wrapper translation.
- `tools/<tool>/spec.yaml`: YAML tool spec for metadata, native usage/options, wrapper options, and wrapper subcommands.
- `spec.schema.json`: canonical JSON Schema for every `spec.yaml`.
- `spec_validation.py`: validates specs against `spec.schema.json`.
- `tests/`: pytest suite for specs, plugins, and CLI behavior.
- `requirements.txt`: Python dependencies.

## Architecture Rules

- Keep tool-specific behavior out of `cliwrap.py`.
- Put tool-specific behavior in `tools/<tool>/plugin.py`.
- Put command, option, usage, and mapping metadata in `tools/<tool>/spec.yaml`.
- Prefer changing `spec.schema.json` and specs over adding ad hoc assumptions in plugins when the behavior is shared.
- `cliwrap.py` should call plugin interfaces such as `build_args(...)` and `translate_native_args(...)` rather than branching by tool.
- Root CLI behavior should remain generic across tools.
- Specs are YAML, but must validate against the JSON Schema.

## Spec Shape

Every `tools/<tool>/spec.yaml` should use this root shape:

```yaml
$schema: ../../spec.schema.json
schema_version: 1

tool:
  name: ssh
  binary: ssh
  summary: Standardized SSH client wrapper.
  raw_help_command: []

native:
  usage: []
  options: []
  option_groups: []

wrapper:
  usage: []
  option_groups: []
  subcommands: []
```

`tool` contains identity and native binary metadata.

`native` contains captured native help/usage/options and organized native option groups for help display.

`wrapper` contains standardized usage, option groups, and flat subcommands.

## Root Commands

Supported root commands:

```sh
./goru list
./goru help <tool>
./goru spec <tool>
./goru validate-specs
./goru translate [--to wrapper|native] <command...>
./goru run <tool> ...
```

`./goru run <tool> --help` shows standardized wrapper help.

`./goru run <tool> --raw-help` shows the native tool help.

`./goru translate` converts between native commands and wrapper commands. Wrapper-to-native uses `plugin.build_args(...)`. Native-to-wrapper uses `plugin.translate_native_args(...)`.

## Testing

Run tests with:

```sh
venv/bin/python -m pytest
```

When editing Python files, also run a syntax check:

```sh
venv/bin/python -m py_compile cliwrap.py spec_validation.py plugins/base.py tools/ssh/plugin.py tools/rsync/plugin.py tools/tar/plugin.py tools/tshark/plugin.py
```

When editing specs, run:

```sh
./goru validate-specs
```

Add or update tests when changing plugin mapping, translation behavior, schema validation, or root CLI behavior.

## Runtime Dependencies

- Click is used for the root CLI.
- Rich is used for colored human-readable output.
- PyYAML is used for YAML parsing when available.
- `jsonschema` is used for validating `spec.yaml`.

## NOTE

Managing backwards compatibility of the commands is not important. We are still trying to arrive at a good interface, do not spend time on maintaining compatibility. Keeping the API maintainable and user friendly is the most important thing.

## References

- https://clig.dev
