import os
import pwd
import shutil

def create_jail(username):
    home = pwd.getpwnam(username).pw_dir
    jail_root = os.path.join(home, "__sftp__")
    mounts_dir = os.path.join(jail_root, "mounts")

    os.makedirs(mounts_dir, exist_ok=True)

    # jail root musí být root:root 755
    os.chown(jail_root, 0, 0)
    os.chmod(jail_root, 0o755)

    # mounts patří userovi
    pw = pwd.getpwnam(username)
    os.chown(mounts_dir, pw.pw_uid, pw.pw_gid)
    os.chmod(mounts_dir, 0o755)

    return jail_root, mounts_dir


def remove_jail(jail_root: str):
    """
    Smaže __sftp__ jail (po umountu mountů).
    """
    if os.path.isdir(jail_root):
        # bezpečně – měl by být prázdný (mounty odpojené)
        shutil.rmtree(jail_root)
