#!/usr/bin/env python3
import libs.JBLibs.helper as hlp
hlp.initLogging(toConsole=True,log_level=hlp.logging.INFO)
log = hlp.getLogger("sftpManager")

import argparse
from libs.JBLibs.sftp import parser
from libs.JBLibs.sftp import ssh

def main():
    log.info("\n"+"*"*20 + " SFTP Jail Manager Started " + "*"*20)
    
    ap = argparse.ArgumentParser(description="SFTP jail manager")
    ap.add_argument("-v", "--verbose", action="store_true")

    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_inst = sub.add_parser("install", help="Install SFTP user from config file")
    ap_inst.add_argument("--file", required=True)

    ap_un = sub.add_parser("uninstall", help="Uninstall SFTP user")
    ap_un.add_argument("--user", required=False, help="Username to uninstall (if not provided, uninstalls all users)")
    ap_un.add_argument("--all", action="store_true", help="Uninstall all SFTP users")

    args = ap.parse_args()

    if args.cmd == "install":
        log.info(f"Installing SFTP users from file: {args.file}")
        parser.createUserFromJson(args.file)
    elif args.cmd == "uninstall":
        if not args.all and not args.user:
            log.error("Either --all or --user must be specified for uninstall.")
            return
        if args.all:
            log.info("Uninstalling all SFTP users.")        
            for u in parser.listActiveUsers():
                log.debug(f"Checking user {u.username} for uninstall")
                try:
                    u.delete_user()
                except Exception as e:
                    log.error(f"Failed to uninstall user {u.username}: {e}")
                    log.exception(e)
        else:
            log.info(f"Uninstalling SFTP user: {args.user}")
            u = parser.sftpUserMng(args.user)
            try:
                if not u.ok:
                    raise RuntimeError(f"User {args.user} is not a valid SFTP user.")
                u.delete_user()
            except Exception as e:
                log.error(f"Failed to uninstall user {u.username}: {e}")
                log.exception(e)
    try:
        ssh.restart_sshd()
    except Exception as e:
        log.exception(e)
        log.error(f"Failed to restart sshd after operations: {e}")
        
    log.info("\n"+"*"*20 + " SFTP Jail Manager Finished " + "*"*20 + "\n")

if __name__ == "__main__":
    main()
