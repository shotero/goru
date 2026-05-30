from pathlib import Path

from plugins import REGISTRY
from spec_validation import validate_tool_spec
from yaml_loader import load_yaml_file


def test_all_registered_specs_validate() -> None:
    for plugin in REGISTRY.values():
        path = Path(plugin.spec_file)
        spec = load_yaml_file(path)
        validate_tool_spec(spec, path)


def test_specs_use_canonical_shape() -> None:
    for plugin in REGISTRY.values():
        spec = plugin.spec
        assert spec["schema_version"] == 1
        assert set(spec) == {"$schema", "schema_version", "tool", "native", "wrapper"}
        assert spec["tool"]["name"] == plugin.name
        assert spec["tool"]["binary"] == plugin.binary
        assert isinstance(spec["wrapper"]["subcommands"], list)
