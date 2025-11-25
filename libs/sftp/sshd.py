import os
import subprocess

SSHD_DIR = "/etc/ssh/sshd_config.d"

TPL = """
# Auto-generated SFTP jail config for user: {user}

Match User {user}
    ChrootDirectory {jail}
    ForceCommand internal-sftp
    PasswordAuthentication no
    AuthorizedKeysFile /user/{user}/.ssh/authorized_keys
    X11Forwarding no
    AllowTcpForwarding no
    PermitTunnel no
"""

def write_sshd_config(user, jail):
    os.makedirs(SSHD_DIR, exist_ok=True)
    path = os.path.join(SSHD_DIR, f"sftp-{user}.conf")

    content = TPL.format(user=user, jail=jail)
    with open(path, "w") as f:
        f.write(content)

    subprocess.run(["systemctl", "restart", "ssh"], check=True)
    return path


def remove_sshd_config(user):
    path = os.path.join(SSHD_DIR, f"sftp-{user}.conf")
    if os.path.exists(path):
        os.remove(path)
        subprocess.run(["systemctl", "restart", "ssh"], check=True)
