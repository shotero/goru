from click.testing import CliRunner

from cliwrap import main


def run_cli(*args: str):
    return CliRunner().invoke(main, list(args))


def test_validate_specs_command() -> None:
    result = run_cli("validate-specs")
    assert result.exit_code == 0
    assert "valid ssh tools/ssh/spec.yaml" in result.output
    assert "valid rsync tools/rsync/spec.yaml" in result.output
    assert "valid tar tools/tar/spec.yaml" in result.output
    assert "valid tshark tools/tshark/spec.yaml" in result.output
    assert "valid qemu tools/qemu/spec.yaml" in result.output


def test_help_includes_native_flag_groups() -> None:
    result = run_cli("run", "ssh", "--help")
    assert result.exit_code == 0
    assert "Native flags" in result.output
    assert "Pass these after -- or use raw." in result.output
    assert "Addressing" in result.output
    assert "Flags: -4, -6, -B, -b, -J, -l, -p" in result.output


def test_translate_native_rsync_to_wrapper() -> None:
    result = run_cli("translate", "rsync -az --exclude '*.tmp' src/ dest/")
    assert result.exit_code == 0
    assert result.output.strip() == "./goru run rsync copy src/ dest/ --archive --compress --exclude '*.tmp'"


def test_translate_wrapper_ssh_to_native() -> None:
    result = run_cli(
        "translate",
        "./goru run ssh exec example.com --user deploy --port 2222 -- uptime",
    )
    assert result.exit_code == 0
    assert result.output.strip() == "ssh -l deploy -p 2222 example.com uptime"


def test_translate_tar_cluster_to_wrapper() -> None:
    result = run_cli("translate", "tar -czf archive.tar README.md")
    assert result.exit_code == 0
    assert result.output.strip() == "./goru run tar create --compress gzip --file archive.tar README.md"


def test_yaml_translate_output() -> None:
    result = run_cli("--yaml", "translate", "ssh -Q cipher")
    assert result.exit_code == 0
    assert "direction: wrapper" in result.output
    assert "tool: ssh" in result.output
    assert "command: ./goru run ssh query cipher" in result.output


def test_translate_native_tshark_fields_to_wrapper() -> None:
    result = run_cli("translate", "tshark -r sample.pcap -T fields -e ip.src -e tcp.port")
    assert result.exit_code == 0
    assert result.output.strip() == "./goru run tshark fields sample.pcap --field ip.src --field tcp.port"


def test_translate_native_qemu_to_wrapper() -> None:
    result = run_cli("translate", "qemu-system-aarch64 -m 2G -smp 4 -drive file=vm.qcow2,if=virtio -nographic")
    assert result.exit_code == 0
    assert result.output.strip() == "./goru run qemu boot vm.qcow2 --arch aarch64 --memory 2G --cpus 4 --headless"
