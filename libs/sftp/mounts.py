import os
import stat
import pwd
import grp
import subprocess
from .errors import SftpConfigError

FSTAB_DIR = "/etc/fstab.d"

def get_owner_group(path):
    st = os.stat(path)
    return pwd.getpwuid(st.st_uid).pw_name, grp.getgrgid(st.st_gid).gr_name


def ensure_user_in_group(username, group):
    subprocess.run(["usermod", "-aG", group, username], check=True)


def bind_mount(src, dst):
    os.makedirs(dst, exist_ok=True)
    subprocess.run(["mount", "--bind", src, dst], check=True)


def write_fstab(username, mounts):
    os.makedirs(FSTAB_DIR, exist_ok=True)
    fstab_file = os.path.join(FSTAB_DIR, f"sftp-{username}.fstab")

    with open(fstab_file, "w") as f:
        for name, pair in mounts.items():
            src = pair["src"]
            dst = pair["dst"]
            f.write(f"{src} {dst} none bind 0 0\n")

    return fstab_file
