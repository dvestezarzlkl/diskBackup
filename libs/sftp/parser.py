import os
import configparser
from .errors import SftpConfigError, MountPointMissing, InvalidPublicKey

def load_config(path):
    if not os.path.exists(path):
        raise SftpConfigError(f"Config file not found: {path}")

    cfg = configparser.ConfigParser()
    cfg.read(path)

    if "general" not in cfg or "mountpoints" not in cfg:
        raise SftpConfigError("Config must contain [general] and [mountpoints] sections")

    user = cfg["general"].get("user", "").strip()
    key = cfg["general"].get("key", "").strip()
    if not user:
        raise SftpConfigError("Field 'user' missing in [general]")
    if not key or "ssh-" not in key:
        raise InvalidPublicKey("Invalid or missing SSH public key in [general]")

    mounts = {}
    for name, src in cfg["mountpoints"].items():
        src = src.strip()
        if not os.path.exists(src):
            raise MountPointMissing(f"Mountpoint does not exist: {src}")
        mounts[name] = src

    return {
        "user": user,
        "key": key,
        "mounts": mounts,
    }
