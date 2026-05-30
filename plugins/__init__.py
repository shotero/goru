"""Tool plugin registry for goru."""

from tools.rsync.plugin import PLUGIN as RSYNC
from tools.qemu.plugin import PLUGIN as QEMU
from tools.ssh.plugin import PLUGIN as SSH
from tools.tar.plugin import PLUGIN as TAR
from tools.tshark.plugin import PLUGIN as TSHARK


REGISTRY = {
    SSH.name: SSH,
    QEMU.name: QEMU,
    RSYNC.name: RSYNC,
    TAR.name: TAR,
    TSHARK.name: TSHARK,
}
