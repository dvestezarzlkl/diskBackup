import os
import pwd
import grp
import subprocess
from .errors import SftpUserExists, SftpConfigError

BASE_DIR = "/user"

def user_exists(username):
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def create_user(username):
    home_path = f"{BASE_DIR}/{username}"

    if user_exists(username):
        return home_path

    subprocess.run([
        "useradd",
        "-m",
        "-d", home_path,
        "-s", "/usr/sbin/nologin",
        username
    ], check=True)

    return home_path


def ensure_ssh_key(username, public_key):
    home = pwd.getpwnam(username).pw_dir
    ssh_dir = os.path.join(home, ".ssh")
    ak_file = os.path.join(ssh_dir, "authorized_keys")

    os.makedirs(ssh_dir, exist_ok=True)
    os.chown(ssh_dir, pwd.getpwnam(username).pw_uid, pwd.getpwnam(username).pw_gid)
    os.chmod(ssh_dir, 0o700)

    with open(ak_file, "w") as f:
        f.write(public_key.strip() + "\n")

    os.chown(ak_file, pwd.getpwnam(username).pw_uid, pwd.getpwnam(username).pw_gid)
    os.chmod(ak_file, 0o600)

    return ak_file
