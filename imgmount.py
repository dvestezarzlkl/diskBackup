#!/usr/bin/env python3
import argparse
import os
import subprocess
import re
import libs.toolhelp as th

"""Nástroj pro připojení (mount) a odpojení (umount) IMG souborů jako loop zařízení.
Umožňuje vybrat partition pro připojení a spravovat mountpointy.
Args:
    --img: Cesta k IMG souboru pro připojení. Pokud není zadáno, spustí se režim odpojení.
Returns:
    None
    
Author: Jan Zednik
Licence: MIT
"""

MNT_DIR:str = "/mnt"
"""Výchozí adresář pro mountpointy."""

def run(cmd: str) -> str:
    """Spustí příkaz a vrátí jeho výstup jako string.
    Args:
        cmd (str): Příkaz k vykonání.
    Returns:
        str: Výstup příkazu.
    """
    try:
        return subprocess.check_output(cmd, shell=True, text=True).strip()
    except subprocess.CalledProcessError as e:
        print(f"Chyba při volání: {cmd}")
        print(e.output)
        return ""    

def is_mounted(device: str) -> bool:
    """Zkontroluje, zda je zařízení připojeno.
    Args:
        device (str): Zařízení (např. /dev/loop0p1).
    Returns:
        bool: True pokud je připojeno, False jinak.
    """
    out = run("mount")
    return any(line.startswith(device + " ") for line in out.splitlines())

def remount_partition(loop: str) -> None:
    """Provede remount partition na jinou partition z téhož loop zařízení.
    Args:
        loop (str): Loop zařízení (např. /dev/loop0).
    Returns:
        None
    """
    parts = list_loop_partitions(loop)

    # zjistit připojené partitions
    out = run("mount")
    mounted = {}
    for line in out.splitlines():
        for p in parts:
            if line.startswith(p + " "):
                mnt = line.split(" ")[2]
                mounted[p] = mnt

    if len(mounted) != 1:
        print("Remount je možný jen pokud je připojena přesně jedna partition.")
        return

    old_part, mnt = list(mounted.items())[0]

    print(f"Připojena je: {old_part} → {mnt}")

    # vylistovat jen NEpřipojené partitions
    choices = []
    for p in parts:
        if p != old_part and not is_mounted(p):
            choices.append(p)

    if not choices:
        print("Není žádná jiná nepřipojená partition pro remount.")
        return

    print("Možnosti remountu:")
    for i, p in enumerate(choices):
        info = get_partition_info(p)
        print(f"{i+1}) {p}  [{info['fstype']}  {info['size']}  {info['label']}]")

    idx = int(input("Vyber partition: ")) - 1
    new_part = choices[idx]

    print(f"Provádím remount: {old_part} → {new_part}")

    run(f"sudo umount {mnt}")
    run(f"sudo mount {new_part} {mnt}")

    print(f"Remount dokončen. {new_part} je nyní na {mnt}.")

def get_partition_info(device: str) -> dict:
    """Získá informace o partition pomocí lsblk.
    Args:
        device (str): Zařízení (např. /dev/loop0p1).
    Returns:
        dict: Slovník s informacemi o partition.
    """
    try:
        fields = run(
            f"lsblk -no LABEL,SIZE,FSTYPE,UUID,PARTUUID {device}"
        ).splitlines()
        info = {
            "label": fields[0] if len(fields) > 0 else "",
            "size": fields[1] if len(fields) > 1 else "",
            "fstype": fields[2] if len(fields) > 2 else "",
            "uuid": fields[3] if len(fields) > 3 else "",
            "partuuid": fields[4] if len(fields) > 4 else "",
        }
        return info
    except:
        return {
            "label": "",
            "size": "",
            "fstype": "",
            "uuid": "",
            "partuuid": "",
        }


def list_loops()-> dict:
    """Vrátí slovník připojených loop zařízení a jejich image souborů
    Returns:
        dict: {loop_device: image_file}
    """
    out = run("losetup -a")
    loops = {}
    for line in out.splitlines():
        m = re.match(r"(/dev/loop\d+):.*\((.*)\)", line)
        if m:
            loops[m.group(1)] = m.group(2)
    return loops


def list_loop_partitions(loop)-> list:
    """Vrátí seznam partitions pro dané loop zařízení.
    Args:
        loop (str): Loop zařízení (např. /dev/loop0).
    Returns:
        list: Seznam partitions (např. ['/dev/loop0p1', '/dev/loop0p2']).
    """
    dev_dir = os.path.dirname(loop)
    base = os.path.basename(loop)
    prefix = base + "p"
    parts = []
    for d in os.listdir(dev_dir):
        if d.startswith(prefix):
            parts.append(os.path.join(dev_dir, d))
    return sorted(parts, key=lambda x: int(re.findall(r"p(\d+)$", x)[0]))

def list_empty_mountpoints()-> list:
    """Vrátí seznam prázdných mountpointů v MNT_DIR.
    Returns:
        list: Seznam prázdných adresářů.
    """
    dirs = []
    for d in os.listdir(MNT_DIR):
        full = os.path.join(MNT_DIR, d)
        if os.path.isdir(full) and not os.listdir(full):
            dirs.append(full)
    return dirs


def mount_mode(img)-> None:
    """Připojení IMG souboru jako loop zařízení a mount partition.
    Args:
        img (str): Cesta k IMG souboru.
    Returns:
        None
    """
    loops = list_loops()
    for loop, path in loops.items():
        if path == img:
            print(f"Image už je připojen jako {loop}")
            break
    else:
        loop = run(f"sudo losetup --find --show --partscan {img}")
        print("Připojeno loop zařízení:", loop)

    parts = list_loop_partitions(loop)
    if not parts:
        print("IMG nemá žádné partitions.")
        return

    print("Dostupné partitions:")
    for i, p in enumerate(parts):
        info = get_partition_info(p)
        print(f"{i+1}) {p}  [{info['fstype']}  {info['size']}  {info['label']}]")

    idx = int(input("Vyber číslo: ")) - 1
    part = parts[idx]

    empty_dirs = list_empty_mountpoints()
    print("Prázdné mountpointy:")
    for i, d in enumerate(empty_dirs):
        print(f"{i+1}) {d}")
    print(f"{len(empty_dirs)+1}) Vytvořit nový adresář")

    sel = int(input("Volba: "))
    if sel == len(empty_dirs) + 1:
        name = input("Zadej název subdir: ")
        mount_point = os.path.join(MNT_DIR, name)
        os.makedirs(mount_point, exist_ok=True)
    else:
        mount_point = empty_dirs[sel - 1]

    run(f"sudo mount {part} {mount_point}")
    print(f"Připojeno na {mount_point}")


def umount_mode()-> None:
    """Odpojení loop zařízení nebo partitions.
    Returns:
        None
    """
    loops = list_loops()
    if not loops:
        print("Není nic připojeno.")
        return

    print("Aktivní loop zařízení:")
    for i, (loop, img) in enumerate(loops.items()):
        print(f"{i+1}) {loop} -> {img}")

    idx = int(input("Vyber zařízení: ")) - 1
    loop = list(loops.keys())[idx]

    # najdeme mounty partitions
    parts = list_loop_partitions(loop)

    mounts = []
    out = run("mount")
    for line in out.splitlines():
        for p in parts:
            if line.startswith(p + " "):
                mnt = line.split(" ")[2]
                mounts.append((p, mnt))


    print("Mounted partitions:")
    for i, (p, m) in enumerate(mounts):
        print(f"{i+1}) {p} -> {m}")

    print(f"{len(mounts)+1}) Odpojit celé loop zařízení")
    print(f"{len(mounts)+2}) Remount – vyměnit partition")

    sel = int(input("Volba: "))

    if sel == len(mounts) + 2:
        remount_partition(loop)
        return
    if sel == len(mounts) + 1:
        # umount všech
        for p, m in mounts:
            print(f"umount {m}")
            run(f"sudo umount {m}")
        print(f"Detach {loop}")
        run(f"sudo losetup -d {loop}")
    else:
        p, m = mounts[sel - 1]
        print(f"umount {m}")
        run(f"sudo umount {m}")
        print("Zbývající partitions zůstávají připojené.")


def main()-> None:
    """Hlavní funkce pro zpracování argumentů a spuštění režimů
    Returns:
        None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--img", help="IMG soubor pro mount")
    args = parser.parse_args()

    # pokud máš --img → rovnou mount mod
    if args.img:
        mount_mode(args.img)
        return

    volba=th.menu(
        header=["=== Hlavní menu ==="],
        options=[
            ["Umount mode (odpojit loop zařízení)","-"],
            ["Mount mode (připojit .img soubor)","+"],
            ["Mount mode (připojit nepřipojený disk)","d"],
            ["Konec","q"]
        ],
        prompt="Volba: "
    )
    volba=str(volba)

    if volba == "-":
        umount_mode()
        return

    elif volba == "+":
        img = th.scan_current_dir_for_imgs()
        if img:
            mount_mode(img)
            return
        # pokud se nic nenašlo, vracíme do hlavního menu
        
    elif volba == "d":
        img = th.choose_disk()
        if img:
            mount_mode(img)
            return
        # pokud se nic nenašlo, vracíme do hlavního menu

    elif volba == "3":
        return


if __name__ == "__main__":
    main()
