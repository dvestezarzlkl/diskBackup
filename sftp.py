#!/usr/bin/env python3
import argparse
import logging
from libs.JBLibs.sftp import parser, user, jail, mounts, sshd, metadata

log = logging.getLogger("sftpctl")

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def install(cfgfile: str):
    cfg = parser.load_config(cfgfile)
    username = cfg["user"]
    log.info(f"Installing SFTP user %s from %s", username, cfgfile)

    # 1) create / ensure user
    home = user.create_user(username)
    log.debug("User %s home: %s", username, home)

    # 2) SSH key
    user.ensure_ssh_key(username, cfg["key"])
    log.debug("SSH key installed for %s", username)

    # 3) jail
    jail_root, mounts_root = jail.create_jail(username)
    log.debug("Jail root: %s, mounts root: %s", jail_root, mounts_root)

    # 4) mountpoints
    mp_info = {}

    for name, src in cfg["mounts"].items():
        owner, group = mounts.get_owner_group(src)
        log.info("Mountpoint %s -> %s (owner=%s, group=%s)", name, src, owner, group)

        mounts.ensure_user_in_group(username, group)

        dst = f"{mounts_root}/{name}"
        try:
            mounts.prepare_mount_dir(username, group, dst)
            mounts.bind_mount(src, dst)
        except Exception as e:
            log.error("Failed to prepare/bind mount %s -> %s: %s", src, dst, e)

        mp_info[name] = {"src": src, "dst": dst, "group": group}

    # jail.validate_jail(jail_root, username, mp_info)

    # 5) fstab (interní per-user soubor)
    mounts.write_fstab(username, mp_info)

    # 6) sshd config
    sshd.write_sshd_config(username, jail_root)

    # 7) metadata
    metadata.save_metadata(username, {
        "user": username,
        "jail": jail_root,
        "mounts": mp_info,
    })

    log.info("Installation of %s completed.", username)


def uninstall(username: str, remove_user: bool = False):
    log.info("Uninstalling SFTP user %s", username)

    meta = metadata.load_metadata(username)
    if not meta:
        log.error("No metadata found for user %s, aborting uninstall.", username)
        return

    # 1) umount všech mountů
    if not mounts.unmount_all(meta["mounts"]):
        log.error("Failed to unmount all mounts for user %s, aborting uninstall.", username)        
        return

    # 2) smazat per-user fstab
    try:
        mounts.remove_fstab(username)
    except Exception as e:
        log.exception(e)
        log.error("Failed to remove fstab for user %s: %s", username, e)
        return

    # 3) smazat jail (__sftp__)
    try:
        jail.remove_jail(meta["jail"])
    except Exception as e:
        log.exception(e)
        log.error("Failed to remove jail for user %s: %s", username, e)
        return

    # 4) smazat sshd config
    try:
        sshd.remove_sshd_config(username)
    except Exception as e:
        log.exception(e)
        log.error("Failed to remove sshd config for user %s: %s", username, e)
        return

    try:
        sshd.restart_sshd()
    except Exception as e:
        log.exception(e)
        log.error("Failed to restart sshd after uninstalling user %s: %s", username, e)
        return

    # volitelně user
    if remove_user:
        try:
            user.delete_user(username, remove_home=True)
            log.info("User %s removed.", username)
        except Exception as e:
            log.exception(e)
            log.error("Failed to remove user %s: %s", username, e)
            return

    # 5) smazat metadata
    try:
        metadata.delete_metadata(username)
    except Exception as e:
        log.exception(e)
        log.error("Failed to remove metadata for user %s: %s", username, e)
        return

    log.info("Uninstall of %s completed.", username)


from libs.JBLibs.sftp.user import sftpUserMng

def main():
    ap = argparse.ArgumentParser(description="SFTP jail manager")
    ap.add_argument("-v", "--verbose", action="store_true")

    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_inst = sub.add_parser("install", help="Install SFTP user from config file")
    ap_inst.add_argument("--file", required=True)

    ap_un = sub.add_parser("uninstall", help="Uninstall SFTP user")
    ap_un.add_argument("--user", required=True)
    ap_un.add_argument("--remove-user", action="store_true")

    args = ap.parse_args()
    setup_logging(args.verbose)

    if args.cmd == "install":
        sftpUserMng.createUserFromJson(args.file)
    elif args.cmd == "uninstall":
        for u in sftpUserMng.listActiveUsers():
            log.debug(f"Checking user {u.username} for uninstall")
            try:
                u.delete_user()
            except Exception as e:
                log.error(f"Failed to uninstall user {u.username}: {e}")
                log.exception(e)
    try:
        sshd.restart_sshd()
    except Exception as e:
        log.exception(e)
        log.error(f"Failed to restart sshd after operations: {e}")

if __name__ == "__main__":
    main()
