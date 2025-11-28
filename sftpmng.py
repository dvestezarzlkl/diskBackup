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
    
    _ = sub.add_parser("list", help="List all SFTP users")

    args = ap.parse_args()

    rst=False
    if args.cmd == "install":
        log.info(f"Installing SFTP users from file: {args.file}")
        parser.createUserFromJson(args.file)
        rst=True
    elif args.cmd == "uninstall":
        if not args.all and not args.user:
            log.error("Either --all or --user must be specified for uninstall.")
            return
        rst=True
        if args.all:
            log.info("Uninstalling all SFTP users.")
            parser.uninstallAllUsers()
        else:
            log.info(f"Uninstalling SFTP user: {args.user}")
            parser.uninstallUser(args.user)
    elif args.cmd == "list":
        log.info("Listing all SFTP users:")
        users = parser.listActiveUsers()
        if not users:
            print("\nNo SFTP users found.\n")
        else:
            print("\nSFTP Users:")
            for u in users:
                print(f"- {u.username} (Home: {u.homeDir}")
            print("")
    try:
        if rst:
            ssh.restart_sshd()
    except Exception as e:
        log.exception(e)
        log.error(f"Failed to restart sshd after operations: {e}")
        
    log.info("\n"+"*"*20 + " SFTP Jail Manager Finished " + "*"*20 + "\n")

if __name__ == "__main__":
    main()
