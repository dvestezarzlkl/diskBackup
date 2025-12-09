#!/usr/bin/env python3
import argparse
import os
import libs.toolhelp as th
import libs.mounting as mt
import libs.glb as glb
import libs.shring as shr
from typing import Union
from libs.JBLibs.input import anyKey,cls

"""Nástroj pro připojení (mount) a odpojení (umount) IMG souborů jako loop zařízení.
Umožňuje vybrat partition pro připojení a spravovat mountpointy.
Args:
    --img: Cesta k IMG souboru pro připojení. Pokud není zadáno, spustí se režim odpojení.
Returns:
    None
    
Author: Jan Zednik
Licence: MIT
"""


def __showMenu() -> Union[str, None]:
    """Zobrazí hlavní menu a umožní uživateli vybrat režim.
    Returns:
        Vybraný režim jako string, nebo None pokud uživatel zvolí ukončení.
    """
    from libs.JBLibs.input import select_item,select
    from libs.JBLibs.c_menu import c_menu_block_items,c_menu_title_label
    
    header=c_menu_block_items()
    header.append("*** Disk Mount Tool ***")
    header.append("=== Hlavní menu ===")
    header.append("")
    header.append(f"Verze: {glb.VERSION}")
    header.append("")

    options=[
        select_item("Mount mode (připojit .img soubor)","+"),
        select_item("Umount mode (odpojit loop zařízení)","-"),
        None,
        select_item("Přehled partition a mountpointů","l"),
        select_item("Zkontrolovat ext4 poit (jen nepřipojené!)","c"),
        None,
        select_item("Mount mode (připojit nepřipojený disk)","m"),
        select_item("Umount mode (odpojit připojený disk)","u"),
        None,
        select_item("Minimalizovat disk","ds"),
        select_item("Maximalizovat disk","de"),
        None,
        select_item("Image Tool",'t'),
    ]
    option:select_item=None
    for option in options:
        if option and  option.data is None:
            option.data=option.choice
            
    choice=select(
        "Diskové nástroje - vyberte režim",
        options,
        80,
        header,
    )
    if choice.item is None:
        return None
    
    return choice.item.data

def main()-> None:
    """Hlavní funkce pro zpracování argumentů a spuštění režimů
    Returns:
        None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--img", help="IMG soubor pro mount")
    parser.add_argument("--dir", help="Adresář pro img pro připojení", default=os.getcwd())
    parser.add_argument("--file", help="Soubor .img pro shrink")
    parser.add_argument("--disk", help="Disk /dev/sdX pro shrink")
    parser.add_argument("--shrink-size", help="Velikost prostoru po shrinku (např. 2G, 500M)", default=None)
    
    args = parser.parse_args()
    
    # pokud máš --img → rovnou mount mod
    if args.img:
        mt.mount_mode(args.img)
        return

    while True:
        volba=__showMenu()
        if volba is None:
            return

        if volba == "-":
            try:
                mt.umount_mode()
            except Exception as e:
                print(f"Chyba při umountování: {e}")
                anyKey()
                continue

        elif volba == "+":
            try:
                img = th.scan_current_dir_for_imgs(fromDir=args.dir)
            except Exception as e:
                print(f"Chyba při výběru IMG souboru: {e}")
                anyKey()
                continue
            if img:
                try:
                    mt.mount_mode(img)
                except Exception as e:
                    print(f"Chyba při mountování: {e}")
                    anyKey()
                    continue
            else:
                print("Žádný IMG soubor nebyl vybrán.")
                anyKey()
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
                    anyKey()
                    continue
            except Exception as e:
                print(f"Chyba při výběru disku: {e}")
                anyKey()
                continue
            if img:
                mt.mount_dev(img)
                cls()
                print(f"Disk {img} byl připojen.")
                anyKey()
        elif volba == "u":
            try:
                mnt=th.choose_partition(None,False)
                if mnt is None:
                    continue
                if mnt:
                    mt.umount_dev(mnt)
                    cls()
                    print(f"Zařízení připojené na {mnt} bylo odpojeno.")
                    anyKey()
            except Exception as e:
                print(f"Chyba při výběru mount pointu: {e}")
                anyKey()
                continue
        elif volba == "l":
            cls()
            mt.print_partitions()
            anyKey()
        elif volba == "q":
            return
        elif volba == "t":
            app="imgtool"
            cls()
            myPath=os.path.abspath(__file__)
            if os.path.isfile(myPath):
                myPath=os.path.dirname(myPath)            
            if os.path.exists(os.path.join(myPath,app)):
                imgtoolPath=os.path.join(myPath,app)
            elif os.path.exists(os.path.join(myPath,app+".py")):
                imgtoolPath=os.path.join(myPath,app+".py")
            else:
                imgtoolPath=app
            os.execv(imgtoolPath, [imgtoolPath] + os.sys.argv[1:])
        elif volba == "c":
            try:
                mnt=th.choose_partition(None,True)
                if mnt is None:
                    print("Žádný mount point nebyl vybrán.")
                    anyKey()
                    continue
                
                th.checkExt4(mnt)
                print(f"Kontrola ext4 partition {mnt} byla dokončena.")
                anyKey()
            except Exception as e:
                print(f"Chyba při výběru mount pointu: {e}")
                anyKey()
                continue
                        
        elif volba == "ds":            
            partition = args.disk or None
            if not partition:
                partition = th.choose_partition(None,True)
                if partition is None:
                    continue
                partition = th.normalizeDiskPath(partition)
                    
            print(f"Vybraný partition pro shrink: {partition}")
            shr.shrink_disk(
                partition,
                spaceSize=args.shrink_size,
                spaceSizeQuestion=True
            )
            anyKey()
            
            
        elif volba == "de":
            partition = args.disk or None
            if not partition:
                partition = th.choose_partition(None,True)
                if partition is None:
                    continue
                partition = th.normalizeDiskPath(partition)
                    
            print(f"Vybraný partition pro shrink: {partition}")
            shr.extend_disk_part_max(partition)
            anyKey()
            
        else:
            print("Neplatná volba.")
            anyKey()

if __name__ == "__main__":
    main()
