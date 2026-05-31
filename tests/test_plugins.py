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


def test_gcc_compile_uses_spec_templates_for_compact_native_args() -> None:
    plugin = REGISTRY["gcc"]
    assert plugin.build_args(
        [
            "compile",
            "src/main.c",
            "--output",
            "main.o",
            "--standard",
            "c11",
            "--optimize",
            "2",
            "--include-dir",
            "include",
            "--define",
            "DEBUG=1",
            "--warnings",
        ],
        {},
    ) == ["-c", "-o", "main.o", "-std=c11", "-O2", "-Wall", "-Iinclude", "-DDEBUG=1", "src/main.c"]


def test_gcc_compile_requires_source() -> None:
    plugin = REGISTRY["gcc"]
    with pytest.raises(ValueError, match="gcc compile requires at least one source"):
        plugin.build_args(["compile", "--output", "main.o"], {})


def test_node_run_maps_options_before_script_args() -> None:
    plugin = REGISTRY["node"]
    assert plugin.build_args(
        [
            "run",
            "--require",
            "dotenv/config",
            "--env-file",
            ".env",
            "--watch",
            "--enable-source-maps",
            "app.js",
            "--port",
            "3000",
        ],
        {},
    ) == ["-r", "dotenv/config", "--env-file=.env", "--watch", "--enable-source-maps", "app.js", "--port", "3000"]


def test_node_eval_uses_spec_template() -> None:
    plugin = REGISTRY["node"]
    assert plugin.build_args(["eval", "--input-type", "module", "console.log(import.meta.url)"], {}) == [
        "--input-type=module",
        "-e",
        "console.log(import.meta.url)",
    ]


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


def test_nmap_service_maps_to_native_args() -> None:
    plugin = REGISTRY["nmap"]
    assert plugin.build_args(
        ["service", "scanme.nmap.org", "--ports", "22,80,443", "--skip-discovery", "--output-xml", "scan.xml"],
        {},
    ) == ["-sV", "-Pn", "-p", "22,80,443", "-oX", "scan.xml", "scanme.nmap.org"]


def test_nmap_scripts_requires_script() -> None:
    plugin = REGISTRY["nmap"]
    with pytest.raises(ValueError, match="nmap scripts requires --script"):
        plugin.build_args(["scripts", "scanme.nmap.org"], {})


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


def test_gcc_translates_native_to_wrapper_from_spec_mappings() -> None:
    plugin = REGISTRY["gcc"]
    assert plugin.translate_native_args(["-c", "-O2", "-std=c11", "-Iinclude", "-DDEBUG=1", "-Wall", "src/main.c"]) == [
        "compile",
        "src/main.c",
        "--optimize",
        "2",
        "--standard",
        "c11",
        "--include-dir",
        "include",
        "--define",
        "DEBUG=1",
        "--warnings",
    ]


def test_node_translates_native_to_wrapper_from_spec_mappings() -> None:
    plugin = REGISTRY["node"]
    assert plugin.translate_native_args(["-r", "dotenv/config", "--env-file=.env", "--watch", "app.js", "--port", "3000"]) == [
        "run",
        "--require",
        "dotenv/config",
        "--env-file",
        ".env",
        "--watch",
        "app.js",
        "--port",
        "3000",
    ]


def test_node_translates_eval_subcommand_with_value() -> None:
    plugin = REGISTRY["node"]
    assert plugin.translate_native_args(["--input-type=module", "-e", "console.log(1)"]) == [
        "eval",
        "--input-type",
        "module",
        "console.log(1)",
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


def test_nmap_translates_native_to_wrapper_from_spec_mappings() -> None:
    plugin = REGISTRY["nmap"]
    assert plugin.translate_native_args(["-sV", "-p", "22,80", "-T4", "--open", "scanme.nmap.org"]) == [
        "service",
        "scanme.nmap.org",
        "--ports",
        "22,80",
        "--timing",
        "4",
        "--open",
    ]
