from plugins import REGISTRY
import pytest


def test_rsync_mirror_maps_to_archive_delete() -> None:
    plugin = REGISTRY["rsync"]
    assert plugin.build_args(["mirror", "src/", "dest/", "--compress"], {}) == [
        "-a",
        "-z",
        "--del",
        "src/",
        "dest/",
    ]


def test_ssh_tunnel_maps_to_native_forwarding() -> None:
    plugin = REGISTRY["ssh"]
    assert plugin.build_args(
        ["tunnel", "example.com", "--local", "8080", "--remote", "localhost:80"],
        {},
    ) == ["-N", "-L", "8080:localhost:80", "example.com"]


def test_tar_create_maps_to_native_archive_args() -> None:
    plugin = REGISTRY["tar"]
    assert plugin.build_args(
        ["create", "--file", "archive.tar", "--compress", "gzip", "README.md"],
        {},
    ) == ["-c", "-f", "archive.tar", "-z", "README.md"]


def test_tshark_fields_maps_to_native_args() -> None:
    plugin = REGISTRY["tshark"]
    assert plugin.build_args(
        ["fields", "sample.pcap", "--field", "ip.src", "--field", "tcp.port", "--field-option", "header=y"],
        {},
    ) == ["-r", "sample.pcap", "-T", "fields", "-e", "ip.src", "-e", "tcp.port", "-E", "header=y"]


def test_qemu_boot_selects_arch_binary_and_maps_common_flags() -> None:
    plugin = REGISTRY["qemu"]
    assert plugin.build_command(
        ["boot", "vm.qcow2", "--arch", "aarch64", "--memory", "2G", "--cpus", "4", "--headless"],
        {},
    ) == [
        "qemu-system-aarch64",
        "-smp",
        "4",
        "-m",
        "2G",
        "-drive",
        "file=vm.qcow2,if=virtio",
        "-nographic",
    ]


def test_qemu_install_maps_iso_and_disk() -> None:
    plugin = REGISTRY["qemu"]
    assert plugin.build_command(
        ["install", "installer.iso", "--disk", "vm.qcow2", "--arch", "x86_64", "--memory", "4G"],
        {},
    ) == [
        "qemu-system-x86_64",
        "-m",
        "4G",
        "-drive",
        "file=vm.qcow2,if=virtio",
        "-cdrom",
        "installer.iso",
        "-boot",
        "d",
    ]


def test_rsync_translates_native_to_wrapper() -> None:
    plugin = REGISTRY["rsync"]
    assert plugin.translate_native_args(["-az", "--exclude", "*.tmp", "src/", "dest/"]) == [
        "copy",
        "src/",
        "dest/",
        "--archive",
        "--compress",
        "--exclude",
        "*.tmp",
    ]


def test_rsync_rejects_invalid_short_option_cluster() -> None:
    plugin = REGISTRY["rsync"]
    with pytest.raises(ValueError, match="unknown short option in cluster -az96: -9"):
        plugin.translate_native_args(["-az96", "src/", "dest/"])


def test_rsync_keeps_valid_unmapped_short_flags_as_passthrough() -> None:
    plugin = REGISTRY["rsync"]
    assert plugin.translate_native_args(["-aV", "src/", "dest/"]) == [
        "copy",
        "src/",
        "dest/",
        "--archive",
        "--",
        "-V",
    ]


def test_ssh_translates_native_to_wrapper() -> None:
    plugin = REGISTRY["ssh"]
    assert plugin.translate_native_args(["-l", "deploy", "-p", "2222", "example.com", "uptime"]) == [
        "exec",
        "example.com",
        "--user",
        "deploy",
        "--port",
        "2222",
        "--",
        "uptime",
    ]


def test_tar_translates_native_to_wrapper() -> None:
    plugin = REGISTRY["tar"]
    assert plugin.translate_native_args(["-czf", "archive.tar", "README.md"]) == [
        "create",
        "--compress",
        "gzip",
        "--file",
        "archive.tar",
        "README.md",
    ]


def test_tshark_translates_native_to_wrapper() -> None:
    plugin = REGISTRY["tshark"]
    assert plugin.translate_native_args(["-r", "sample.pcap", "-Y", "http", "-V"]) == [
        "read",
        "sample.pcap",
        "--display-filter",
        "http",
        "--details",
    ]


def test_qemu_translates_native_to_wrapper_with_arch() -> None:
    plugin = REGISTRY["qemu"]
    assert plugin.translate_native_command(["qemu-system-riscv64", "-m", "1G", "-drive", "file=disk.qcow2,if=virtio"]) == [
        "boot",
        "disk.qcow2",
        "--arch",
        "riscv64",
        "--memory",
        "1G",
    ]
