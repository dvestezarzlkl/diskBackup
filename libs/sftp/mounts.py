import os
import pwd
import grp
import subprocess
from .errors import SftpConfigError

FSTAB_DIR = "/etc/fstab.d"   # interní per-user soubory, ne nutně čtené systémem

def get_owner_group(path):
    st = os.stat(path)
    return pwd.getpwuid(st.st_uid).pw_name, grp.getgrgid(st.st_gid).gr_name


def ensure_user_in_group(username, group):
    # id -nG user -> kontrola by šla doplnit, teď to prostě přidáme
    subprocess.run(["usermod", "-aG", group, username], check=True)


def prepare_mount_dir(username: str, group: str, dst: str):
    os.makedirs(dst, exist_ok=True)
    pw = pwd.getpwnam(username)
    gr = grp.getgrnam(group)

    # cílový adresář v jailu – user:group, 755
    os.chown(dst, pw.pw_uid, gr.gr_gid)
    os.chmod(dst, 0o755)


def bind_mount(src, dst):
    subprocess.run(["mount", "--bind", src, dst], check=True)


def write_fstab(username, mounts: dict):
    """
    mounts: { name: {src: ..., dst: ..., group: ...}, ... }
    """
    os.makedirs(FSTAB_DIR, exist_ok=True)
    fstab_file = os.path.join(FSTAB_DIR, f"sftp-{username}.fstab")

    with open(fstab_file, "w") as f:
        for name, pair in mounts.items():
            src = pair["src"]
            dst = pair["dst"]
            f.write(f"{src} {dst} none bind 0 0\n")

    return fstab_file


def remove_fstab(username):
    fstab_file = os.path.join(FSTAB_DIR, f"sftp-{username}.fstab")
    if os.path.exists(fstab_file):
        os.remove(fstab_file)


def unmount_all(mounts: dict):
    """
    mounts: { name: {src: ..., dst: ...}, ... }
    Umountuje podle dst.
    """
    # od nejhlubších cest (pro jistotu) – tady jsou stejně na stejné úrovni,
    # ale kdybys někdy vnořoval, je to bezpečnější.
    dst_list = [m["dst"] for m in mounts.values()]
    dst_list.sort(key=len, reverse=True)

    for dst in dst_list:
        # umount ignoruje, pokud už není mountnuté? Radši error-handling:
        subprocess.run(["umount", dst], check=False)
