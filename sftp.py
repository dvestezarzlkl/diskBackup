#!/usr/bin/env python3
import libs.JBLibs.helper as hlp
hlp.initLogging(toConsole=True)
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
    ap_un.add_argument("--user", required=True)
    ap_un.add_argument("--remove-user", action="store_true")

    args = ap.parse_args()

    if args.cmd == "install":
        log.info(f"Installing SFTP users from file: {args.file}")
        parser.createUserFromJson(args.file)
    elif args.cmd == "uninstall":
        log.info(f"Uninstalling SFTP user: {args.user}")
        for u in parser.listActiveUsers():
            log.debug(f"Checking user {u.username} for uninstall")
            try:
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
