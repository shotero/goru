# Goru CLI Wrapper

This is a small sample wrapper that puts several existing CLI tools behind one consistent interface.

## Setup

```sh
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

The `./goru` launcher uses `venv/bin/python` when it exists.

## Tests

```sh
venv/bin/python -m pytest
```

## Layout

- `cliwrap.py` is the central wrapper.
- `plugins/base.py` contains shared plugin helpers.
- `tools/<name>/plugin.py` translates standard wrapper flags to native tool flags.
- `spec.schema.json` defines the canonical schema for every tool spec.
- `tools/<name>/spec.yaml` contains tool metadata, captured native metadata, native flag groups, and wrapper metadata.

Each tool should keep its plugin, spec, examples, and other tool-specific files inside `tools/<name>/`.

## Commands

```sh
./goru list
./goru help ssh
./goru spec tar
./goru validate-specs
./goru translate "rsync -az ./src ./backup"
./goru run rsync copy ./src ./backup --archive
./goru run ssh connect example.com --user deploy
./goru run tshark read capture.pcap --display-filter http
./goru run qemu boot vm.qcow2 --arch aarch64 --memory 2G
```

All wrapper commands accept `--yaml`:

```sh
./goru --yaml help tar
./goru --yaml validate-specs
./goru --yaml run tar list --file archive.tar
```

Native tool arguments can be passed after `--`:

```sh
./goru run ssh connect example.com -- -o StrictHostKeyChecking=no
./goru run tar list --file archive.tar -- --exclude tmp
```

Use `--` to pass extra native options to a standardized subcommand. Use `raw` to bypass wrapper remapping entirely:

```sh
./goru run ssh raw -o StrictHostKeyChecking=no example.com
./goru run rsync raw -av ./src ./dst
```

## Translation

Use `translate` to convert a pasted native command into the wrapper form, or a wrapper command into the native form:

```sh
./goru translate "rsync -az --exclude '*.tmp' ./src ./backup"
./goru translate "./goru run rsync copy ./src ./backup --archive --compress"
./goru translate "ssh -l deploy -p 2222 example.com uptime"
./goru translate "./goru run ssh exec example.com --user deploy --port 2222 -- uptime"
```

Direction is inferred. You can force it with `--to wrapper` or `--to native`:

```sh
./goru translate --to wrapper "tar -czf archive.tar README.md"
./goru translate --to native "./goru run tar create --file archive.tar --compress gzip README.md"
```

For unquoted commands, put `--` before the pasted command:

```sh
./goru translate -- rsync -az ./src ./backup
```

## SSH Subcommands

SSH is exposed as a flat command surface:

```sh
./goru run ssh connect example.com --user deploy --port 2222
./goru run ssh exec example.com -- uptime
./goru run ssh tunnel example.com --local 8080 --remote localhost:80
./goru run ssh socks bastion.example.com --listen 127.0.0.1:1080
./goru run ssh config example.com
./goru run ssh query cipher
./goru run ssh raw -V
```

## rsync Subcommands

rsync is exposed as workflow-oriented actions:

```sh
./goru run rsync copy ./src ./backup --archive
./goru run rsync mirror ./src ./backup --compress
./goru run rsync preview ./src ./backup --exclude '*.tmp'
./goru run rsync list ./src
./goru run rsync raw --version
```

## tar Subcommands

tar is exposed as archive-oriented actions:

```sh
./goru run tar create --file archive.tar ./src
./goru run tar extract --file archive.tar
./goru run tar list --file archive.tar
./goru run tar raw --help
```

## tshark Subcommands

tshark is exposed as packet capture and inspection workflows:

```sh
./goru run tshark capture --interface en0 --count 10
./goru run tshark read capture.pcap --display-filter http
./goru run tshark fields capture.pcap --field ip.src --field tcp.port
./goru run tshark interfaces
./goru run tshark reports fields
./goru run tshark raw -h
```

## QEMU Subcommands

QEMU system emulators are exposed as one `qemu` tool. Select the native `qemu-system-<arch>` binary with `--arch`:

```sh
./goru run qemu boot vm.qcow2 --arch x86_64 --memory 4G --cpus 4
./goru run qemu install debian.iso --disk vm.qcow2 --arch aarch64 --accel hvf
./goru run qemu run --arch riscv64 --machine virt --kernel Image --initrd rootfs.cpio --append 'console=ttyS0' --headless
./goru run qemu monitor --arch x86_64 --disk vm.qcow2
./goru run qemu raw --arch x86_64 -m 2G -drive file=vm.qcow2,if=virtio
```

## Spec Validation

All `tools/<name>/spec.yaml` files must match `spec.schema.json`. Specs are validated when loaded, and can be checked directly:

```sh
./goru validate-specs
./goru --yaml validate-specs
```

## SSH Config YAML

The SSH wrapper can consume YAML SSH config files and convert them to native `ssh_config` format before invoking `ssh`. Pass one explicitly:

```sh
./goru --config ./tools/ssh/example-config.yaml run ssh config github
./goru --config ./tools/ssh/example-config.yaml run ssh connect bastion
```

If `ssh-config.yaml` exists in the current directory and declares itself as an SSH config file, it is used automatically:

```yaml
type: ssh_config

global:
  server_alive_interval: 30

hosts:
  github:
    hostname: github.com
    user: git
    identity_file: ~/.ssh/id_ed25519
    identities_only: true
```

YAML keys are converted to native SSH config keys, for example `identity_file` becomes `IdentityFile` and `strict_host_key_checking` becomes `StrictHostKeyChecking`.

## Config

By default, `run <tool>` reads `<tool>-config.yaml` if it exists. A config can provide wrapper defaults and extra native args:

```yaml
# Comments and YAML anchors are allowed in config files.
defaults:
  verbose: true
native_args:
  - --no-motd
```

Use `--config` to choose a different file:

```sh
./goru --config ./my-ssh-config.yaml run ssh connect example.com
```
