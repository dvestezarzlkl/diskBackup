import os
import re
import libs.toolhelp as th
import libs.glb as glb
import subprocess
from pathlib import Path
import json
from .JBLibs.input import select_item, select,anyKey
from .JBLibs.c_menu import c_menu_block_items,c_menu_title_label
from typing import Union

def is_mounted(device: str) -> bool:
    """Zkontroluje, zda je zařízení připojeno.
    Args:
        device (str): Zařízení (např. /dev/loop0p1).
    Returns:
        bool: True pokud je připojeno, False jinak.
    """
    out = th.run("mount")
    return any(line.startswith(device + " ") for line in out.splitlines())

def remount_partition(loop: str) -> None:
    """Provede remount partition na jinou partition z téhož loop zařízení.
    Args:
        loop (str): Loop zařízení (např. /dev/loop0).
    Returns:
        None
    """
    parts = th.list_loop_partitions(loop)

    # zjistit připojené partitions
    out = th.run("mount")
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

    th.run(f"sudo umount {mnt}")
    th.run(f"sudo mount {new_part} {mnt}")

    print(f"Remount dokončen. {new_part} je nyní na {mnt}.")

def get_partition_info(device: str) -> dict:
    """Získá informace o partition pomocí lsblk.
    Args:
        device (str): Zařízení (např. /dev/loop0p1).
    Returns:
        dict: Slovník s informacemi o partition.
    """
    try:
        fields = th.run(
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
    out = th.runRet("losetup -a")
    loops = {}
    if out is None or out.strip() == "":
        return loops
    for line in out.splitlines():
        m = re.match(r"(/dev/loop\d+):.*\((.*)\)", line)
        if m:
            loops[m.group(1)] = m.group(2)
    return loops

def list_empty_mountpoints()-> list:
    """Vrátí seznam prázdných mountpointů v MNT_DIR.
    Returns:
        list: Seznam prázdných adresářů.
    """
    dirs = []
    for d in os.listdir(glb.MNT_DIR):
        full = os.path.join(glb.MNT_DIR, d)
        if os.path.isdir(full) and not os.listdir(full):
            dirs.append(full)
    return dirs


def _isAttachedImg(img:str)-> None|str:
    """Zkontroluje, zda je loop zařízení připojeno.
    Args:
        img (str): Loop zařízení (např. /dev/loop0).
    Returns:
        str: None pokud není připojeno, jinak název loop zařízení.
    """
    loops = list_loops()
    for loop, path in loops.items():
        if path == img:
            return loop
    return None

def mount_mode(img)-> None:
    """Připojení IMG souboru jako loop zařízení a mount partition.
    Args:
        img (str): Cesta k IMG souboru.
    Returns:
        None
    """   
    loop = _isAttachedImg(img)
    if not loop:
        try:
            th.run(f"sudo losetup --find --show --partscan {img}")
            loop = _isAttachedImg(img)
            if not loop:
                raise Exception("Nepodařilo se připojit IMG soubor jako loop zařízení.")
        except Exception as e:
            raise Exception(f"Chyba při připojování IMG souboru: {e}")

    mount_partition_mode(loop)

def mount_partition_mode(loop:str)-> None:
    """Připojení partition z loop zařízení.
    Args:
        loop (str): Loop zařízení (např. /dev/loop0).
    Returns:
        None
    """
    loop = th.normalizeDiskPath(loop,True)
    part = th.choose_partition(loop,True)
    if not part:
        return        
    part=th.normalizeDiskPath(part,False)
    mount_point = select_mountpoint()
    
    th.run(f"sudo mount {part} {mount_point}")
    print(f"Připojeno na {mount_point}")
    anyKey()



def umount_mode()-> None:
    """Odpojení loop zařízení nebo partitions.
    Returns:
        None
    """
    loops = list_loops()
    if not loops:
        raise Exception("Není nic připojeno.")

    msg="Vyber loop zařízení pro odpojení"
    loop_opts = []
    for loop, img in loops.items():
        # loop_opts.append(f"{loop} -> {img}")
        loop_opts.append( select_item(
            f"{loop} -> {img}",
            "",
            f"{loop}"
        ))
    sel=select(
        msg,
        loop_opts,
        80
    )
    if sel.item is None:
        return
    loop=sel.item.data
    loop=th.normalizeDiskPath(loop,True)    
    
    devs = th.list_loop_partitions(loop,True)
    dev=devs.get(loop,None)
    
    header = c_menu_block_items()
    header.append(f"*** Odpojení loop zařízení: {loop} ***")
    header.append("Vyberte partition pro odpojení nebo odpojte celé loop zařízení.")
    
    opts=[]
    if not dev or not dev.children:
        header.append("Nebyly nalezeny připojené partition.") 
    else:
        header.append("Připojené partition:")
        for part in dev.children:
            opts.append( select_item(
                f"{part.name}",
                "",
                f"{part.name}"
            ))
            
    opts.append( select_item(
        f"Odpojit celé loop zařízení",
        "a",
        "a"
    ))
    opts.append( None )
    opts.append( select_item(
        f"Mount partition",
        "m",
        "m"
    ))
    x=select(
        "Volba:",
        opts,
        80,
        header,
    )
    if x.item is None:
        return
    if x.item.data=="a":
        # umount všech
        if dev and dev.children:
            for part in dev.children:
                mnt = th.normalizeDiskPath(part.name,False)
                try:
                    print(f"umount {mnt}")
                    th.run(f"sudo umount {mnt}")
                except Exception as e:
                    print(f"Chyba při umountování {mnt}: {e}")
                    anyKey()
        try:
            loop=th.normalizeDiskPath(loop,False)
            print(f"Detach {loop}")
            th.run(f"sudo losetup -d {loop}")
        except Exception as e:
            print(f"Chyba při odpojování {loop}: {e}")
            anyKey()
        return
    elif x.item.data=="m":
        mount_partition_mode(loop)
        return
    else:
        # umount vybrané partition
        part=th.normalizeDiskPath(x.item.data,False)
        try:
            th.run(f"sudo umount {part}")
            print(f"Odpojeno zařízení {part}")
        except Exception as e:
            print(f"Chyba při umountování {part}: {e}")
            anyKey()
        return
    
        
def print_partitions(filter:str=None, retStrOnly:bool=False) -> str:
    """Vytiskne seznam všech partitions.
    Args:
        filter (str, optional): Filtr pro disk nebo zařízení, může být zadáno loop0, pak se zobrazí všechny partitions pro toto zařízení.  
            nebo /dev/loop0p1 nebo loop0p1 pro konkrétní partition. Defaults to None.
        retStrOnly (bool, optional): Pokud je False tak jen vrací string, jinak i tiskne.
    Returns:
        str: Výstupní řetězec - vždy
    """
    
    lst = th.lsblk_list_disks(mounted=None)

    data_rows = []
    for disk in lst.values():
        for part in disk.children:
            if filter:
                if not (filter in disk.name or filter in part.name):
                    continue
            dev = f"/dev/{part.name}"
            size = th.human_size(part.size)
            fstype = part.fstype or "-"
            mnts = ", ".join(part.mountpoints) if part.mountpoints else "nepřipojeno"
            label = part.label or "-"
            puid = part.partuuid or "-"            
            data_rows.append([dev, size, fstype, mnts, label, puid])

    if not data_rows:
        print("Žádné partition.")
        return

    header = ["Zařízení", "Velikost", "Typ", "Mountpoint", "Label", "PartUUID"]
    all_rows = [header] + data_rows

    col_widths = [
        max(len(str(row[i])) for row in all_rows)
        for i in range(len(header))
    ]

    def format_row(row):
        return (
            row[0].ljust(col_widths[0]) + "  " +
            row[1].rjust(col_widths[1]) + "  " +
            row[2].ljust(col_widths[2]) + "  " +
            row[3].ljust(col_widths[3]) + "  " +
            row[4].ljust(col_widths[4]) + "  " +
            row[5].ljust(col_widths[5])
        )

    total_width = sum(col_widths) + 2 * (len(col_widths) - 1)

    output_lines = []

    # Title
    ln = "*" * total_width
    title = "Seznam partitions:"
    
    title = f" {title} "
    pad_total = total_width - len(title)
    left_pad = pad_total // 2
    right_pad = pad_total - left_pad
    title_line = "*" * left_pad + title + "*" * right_pad

    output_lines += [
        ln,
        title_line,
        ln,
        ""
    ]

    output_lines.append(format_row(header))
    output_lines.append("-" * total_width)

    for row in data_rows:
        output_lines.append(format_row(row))

    output_lines += [
        ln,
        ""
    ]

    x="\n".join(output_lines)
    if not retStrOnly:
        print(x)
    return x
        
def select_mountpoint()-> Union[str|None]:
    """Umožní uživateli vybrat mount point ze seznamu prázdných mountpointů nebo vytvořit nový.
    Returns:
        str: Cesta k vybranému nebo nově vytvořenému mount pointu.
    """
    empty_dirs = list_empty_mountpoints()
    
    header = c_menu_block_items()
    header.append("*** Výběr mountpointu ***")
    header.append("")
    
    items = []
    for d in empty_dirs:
        items.append(select_item(d, "", d))
    items.append(select_item("Vytvořit nový adresář", "n", "n"))

    while True:    
        x= select(
            "Vyberte mountpoint:",
            items,
            80,
            header,
        )
        if x.item is None:
            return None
        elif x.item == "n":
            name = input("Zadej název subdir: ")
            mount_point = os.path.join(glb.MNT_DIR, name)
            if os.path.exists(mount_point):
                print("Adresář už existuje, zvol jiný název.")
                anyKey()
                continue
            try:
                os.makedirs(mount_point, exist_ok=True)
            except Exception as e:
                print(f"Chyba při vytváření adresáře: {e}")
                anyKey()
                continue
            return mount_point    
        else:
            return x.item.data
    
        
def mount_dev(device: str, mount_point:str|None=None) -> None:
    """Připojí zadané zařízení na zadaný mount point.
    Args:
        device (str): Zařízení (např. /dev/loop0p1).
        mount_point (str): Cesta k mount pointu.
    Returns:
        None
    """
    if not mount_point:
        mount_point = select_mountpoint()
    if mount_point:
        try:
            th.run(f"sudo mount {device} {mount_point}")
            print(f"Připojeno {device} na {mount_point}")
            anyKey()
            return
        except Exception as e:
            print(f"Chyba při připojování: {e}")
            anyKey()
    
def umount_dev(mount_point: str) -> None:
    """Odpojí zařízení připojené na zadaný mount point.
    Args:
        mount_point (str): Cesta k mount pointu.
    Returns:
        None
    """
    th.run(f"sudo umount {mount_point}")
    print(f"Odpojeno zařízení z {mount_point}")

def mountImage(imgFile: str, mountBase: str = "/mnt/imgtool") -> dict:
    """
    Připojí IMG soubor – buď celý disk, nebo jen jednu partition.
    Automaticky detekuje typ:

      - Pokud IMG obsahuje GPT/MBR → připojí přes losetup --partscan
        a jako root partition použije /dev/loopXp2 (pokud existuje).

      - Pokud IMG je pouze jedna partition (ext4, vfat) → mount -o loop.

    Vrací dict:
    {
        "mode": "disk" | "partition",
        "loop": "/dev/loopX" | None,
        "mount": "/mnt/imgtool/<name>",
        "parts": [ "/dev/loopXp1", "/dev/loopXp2", ... ]
    }

    Vytvoří addressář mountpointu a uloží si stav do:
        <mountBase>/<name>/.mountinfo.json
    """
    img = Path(imgFile).resolve()
    if not img.exists():
        raise RuntimeError(f"Soubor IMG neexistuje: {img}")

    name = img.stem
    base = Path(mountBase).resolve()
    base.mkdir(parents=True, exist_ok=True)

    mountpoint = base / name
    mountpoint.mkdir(exist_ok=True)

    print(f"[MOUNT] Připojuji {img} → {mountpoint}")

    # Zkusit zjistit, zda IMG obsahuje GPT nebo MBR
    out = subprocess.run(
        ["file", "-b", str(img)],
        capture_output=True,
        text=True
    ).stdout.lower()

    is_disk = ("partition table" in out) or ("dos/mb" in out) or ("gpt" in out)

    state = {
        "mode": None,
        "loop": None,
        "mount": str(mountpoint),
        "parts": []
    }

    if is_disk:
        # ---------------------------------------------
        #  DISK IMAGE – POUŽÍT losetup --partscan
        # ---------------------------------------------
        print("[INFO] Detekováno jako disk image (MBR/GPT)")

        loop = th.runRet(["sudo", "losetup", "--find", "--show", "--partscan", str(img)]).strip()
        state["loop"] = loop
        state["mode"] = "disk"

        # Najít partitiony /dev/loopXpX
        lsblk_json = th.runRet(["lsblk", "-J", "-o", "NAME,PATH,TYPE", loop])
        data = json.loads(lsblk_json)

        parts = []
        for node in data.get("blockdevices", []):
            for ch in node.get("children", []):
                if ch.get("type") == "part":
                    parts.append(ch["path"])

        state["parts"] = parts

        if not parts:
            raise RuntimeError("IMG je disk, ale neobsahuje žádné partition.")

        # Mount první ext4 nebo vfat partition
        rootPart = None
        for p in parts:
            fstype = th.runRet(["lsblk", "-no", "FSTYPE", p]).strip().lower()
            if fstype in ("ext4", "vfat", "fat32", "xfs", "btrfs"):
                rootPart = p
                break

        if not rootPart:
            raise RuntimeError("Disk IMG obsahuje partition, ale žádná není mountovatelný FS.")

        th.run(["sudo", "mount", rootPart, str(mountpoint)])
        print(f"[OK] Disk IMG připojen na {mountpoint} (partition {rootPart})")

    else:
        # ---------------------------------------------
        #  PARTITION IMAGE – MOUNT PŘÍMO -o loop
        # ---------------------------------------------
        print("[INFO] Detekováno jako partition image")

        state["mode"] = "partition"
        th.run(["sudo", "mount", "-o", "loop", str(img), str(mountpoint)])
        print(f"[OK] Partition IMG připojen na {mountpoint}")

    # uložit stav pro unmount
    infofile = mountpoint / ".mountinfo.json"
    infofile.write_text(json.dumps(state, indent=2), encoding="utf-8")

    return state

def unmountImage(path: str, mountBase: str = "/mnt/imgtool") -> None:
    """
    Odpojí předtím připojený IMG (přes mountImage).
    Parametr může být:
        - IMG soubor
        - nebo mountpoint adresář

    Najde .mountinfo.json a podle něj provede unmount + losetup -d.
    """
    p = Path(path).resolve()

    # pokud je zadáno IMG, mountpoint se jmenuje /mnt/imgtool/<stem>
    if p.is_file():
        mountpoint = Path(mountBase) / p.stem
    else:
        mountpoint = p

    infofile = mountpoint / ".mountinfo.json"
    if not infofile.exists():
        raise RuntimeError(f"{mountpoint} není imgtool mountpoint (chybí .mountinfo.json)")

    state = json.loads(infofile.read_text(encoding="utf-8"))

    print(f"[UMOUNT] Odpojuji {mountpoint}")

    # unmount mountpoint
    try:
        th.run(["sudo", "umount", str(mountpoint)])
    except Exception as e:
        print("[WARN] Umount selhal:", e)

    # detach loop
    if state.get("loop"):
        try:
            th.run(["sudo", "losetup", "-d", state["loop"]])
        except Exception as e:
            print("[WARN] losetup -d selhal:", e)

    # smazat stát
    try:
        infofile.unlink()
    except:
        pass

    print("[DONE] IMG odpojen.")
