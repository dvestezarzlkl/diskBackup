#!/usr/bin/env python3

import argparse
from libs.sftp import parser, user, jail, mounts, sshd, metadata

def install(cfgfile):
    cfg = parser.load_config(cfgfile)
    username = cfg["user"]

    # 1) create user
    home = user.create_user(username)

    # 2) add ssh key
    user.ensure_ssh_key(username, cfg["key"])

    # 3) create jail
    jail_root, mounts_root = jail.create_jail(username)

    # 4) process mountpoints
    mp_info = {}

    for name, src in cfg["mounts"].items():
        owner, group = mounts.get_owner_group(src)
        mounts.ensure_user_in_group(username, group)

        dst = f"{mounts_root}/{name}"
        mounts.bind_mount(src, dst)

        mp_info[name] = {"src": src, "dst": dst}

    # 5) write fstab entries
    mounts.write_fstab(username, mp_info)

    # 6) sshd config
    sshd.write_sshd_config(username, jail_root)

    # 7) metadata
    metadata.save_metadata(username, {
        "user": username,
        "jail": jail_root,
        "mounts": mp_info
    })

    print(f"User {username} installed successfully.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_inst = sub.add_parser("install")
    ap_inst.add_argument("--file", required=True)

    ap_un = sub.add_parser("uninstall")
    ap_un.add_argument("--user", required=True)

    args = ap.parse_args()

    if args.cmd == "install":
        install(args.file)

if __name__ == "__main__":
    main()
