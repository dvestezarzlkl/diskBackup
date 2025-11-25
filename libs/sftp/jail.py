import os
import pwd
import grp

def create_jail(username):
    home = pwd.getpwnam(username).pw_dir
    jail_root = os.path.join(home, "__sftp__")
    mounts_dir = os.path.join(jail_root, "mounts")

    os.makedirs(mounts_dir, exist_ok=True)

    # jail root must be root:root 755
    os.chown(jail_root, 0, 0)
    os.chmod(jail_root, 0o755)

    # mounts subdir belongs to user
    uid = pwd.getpwnam(username).pw_uid
    gid = pwd.getpwnam(username).pw_gid

    os.chown(mounts_dir, uid, gid)
    os.chmod(mounts_dir, 0o755)

    return jail_root, mounts_dir
