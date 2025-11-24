#!/usr/bin/env python3
import argparse
import os
import subprocess
import re
import libs.toolhelp as th
import libs.mounting as mt
import libs.glb as glb

"""Nástroj pro připojení (mount) a odpojení (umount) IMG souborů jako loop zařízení.
Umožňuje vybrat partition pro připojení a spravovat mountpointy.
Args:
    --img: Cesta k IMG souboru pro připojení. Pokud není zadáno, spustí se režim odpojení.
Returns:
    None
    
Author: Jan Zednik
Licence: MIT
"""

def main()-> None:
    """Hlavní funkce pro zpracování argumentů a spuštění režimů
    Returns:
        None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--img", help="IMG soubor pro mount")
    parser.add_argument("--dir", help="Adresář pro img pro připojení", default=os.getcwd())    
    
    args = parser.parse_args()
    
    # pokud máš --img → rovnou mount mod
    if args.img:
        mt.mount_mode(args.img)
        return

    while True:
        volba=th.menu(
            header=[
                "*** Disk Mount Tool ***\n0c",
                "=== Hlavní menu ===\n0c",
                f"Verze: {glb.VERSION}\n0c",
                "Current dir for imgs",
                f"{args.dir}\n0c"
            ],
            options=[
                ["Mount mode (připojit .img soubor)","+"],
                ["Umount mode (odpojit loop zařízení)","-"],
                ["-\n0",None],
                ["Přehled partition a mountpointů","l"],
                ["Mount mode (připojit nepřipojený disk)","m"],
                ["Umount mode (odpojit připojený disk)","u"],
                ["=\n0",None],
                ["Image Tool",'t'],
                ["Konec","q"]
            ],
            prompt="Volba: "
        )

        if volba == "-":
            try:
                mt.umount_mode()
            except Exception as e:
                print(f"Chyba při umountování: {e}")
                th.anyKey()
                continue

        elif volba == "+":
            try:
                img = th.scan_current_dir_for_imgs(fromDir=args.dir)
            except Exception as e:
                print(f"Chyba při výběru IMG souboru: {e}")
                th.anyKey()
                continue
            if img:
                try:
                    mt.mount_mode(img)
                except Exception as e:
                    print(f"Chyba při mountování: {e}")
                    th.anyKey()
                    continue
            else:
                print("Žádný IMG soubor nebyl vybrán.")
                th.anyKey()
                continue
            
        elif volba == "m":
            try:        
                img = th.choose_disk()
                if img is None:
                    continue
                try:
                    part=th.choose_partition(img)
                    if part is None:
                        continue
                    if part:
                        img=part
                except Exception as e:
                    print(f"Chyba při výběru partition: {e}")
                    th.anyKey()
                    continue
            except Exception as e:
                print(f"Chyba při výběru disku: {e}")
                th.anyKey()
                continue
            if img:
                mt.mount_dev(img)
                th.cls()
                print(f"Disk {img} byl připojen.")
                th.anyKey()
        elif volba == "u":
            try:
                mnt=th.choose_partition(None,False)
                if mnt is None:
                    continue
                if mnt:
                    mt.umount_dev(mnt)
                    th.cls()
                    print(f"Zařízení připojené na {mnt} bylo odpojeno.")
                    th.anyKey()
            except Exception as e:
                print(f"Chyba při výběru mount pointu: {e}")
                th.anyKey()
                continue
        elif volba == "l":
            th.cls()
            mt.print_partitions()
            th.anyKey()
        elif volba == "q":
            return
        elif volba == "t":
            th.cls()
            os.execv("imgtool",["python3" , "imgtool"] + os.sys.argv[1:])
        else:
            print("Neplatná volba.")
            th.anyKey()

if __name__ == "__main__":
    main()
