import os
import re
import libs.toolhelp as th
import libs.glb as glb

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
    parts = list_loop_partitions(loop)

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


def list_loop_partitions(loop,mounted:bool=None)-> dict[str, th.lsblkDiskInfo]:
    """Vrátí seznam partitions pro dané loop zařízení.
    Args:
        loop (str): Loop zařízení (např. /dev/loop0).
        mounted (bool, optional): Filtr připojení partitions. Defaults to None.
            - None = všechny partitions
            - True = pouze připojené partitions
            - False = pouze nepřipojené partitions
    Returns:
        dict[str, th.lsblkDiskInfo]: Seznam disků kde '.children' jsou partitions.
    """
    return th.lsblk_list_disks(None,mounted,filterDev="^"+str(loop)+"$")

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
    devs = list_loop_partitions(loop,False)
    if not devs:
        raise Exception("Nenalezeno zařízení loop")
    
    dev=devs[loop] or None
    if not dev or not dev.children:
        raise Exception("Zařízení neobsahuje žádné partition.")

    parts= []
    for disk in dev.children:
            parts.append("/dev/" + disk.name + f"  [{disk.fstype}  {th.human_size(disk.size)}  {disk.label}]")

    header = [
        f"Loop zařízení: {loop}\n0c",
        "Vyber partition pro připojení:\n0c"
    ]
    parts.append(["Zpět","r"])
    
    sel = th.menu(
        header=header,
        options=parts,
        prompt="Volba: "
    )
    if sel == "r":
        return

    part=dev.children[int(sel)-1].name
    part=th.normalizeDiskPath(part,False)
    mount_point = select_mountpoint()
    
    th.run(f"sudo mount {part} {mount_point}")
    print(f"Připojeno na {mount_point}")
    th.anyKey()


def umount_mode()-> None:
    """Odpojení loop zařízení nebo partitions.
    Returns:
        None
    """
    loops = list_loops()
    if not loops:
        raise Exception("Není nic připojeno.")

    header = [
        "Vyber loop zařízení pro odpojení:\n0c"
    ]
    loop_opts = []
    for loop, img in loops.items():
        loop_opts.append(f"{loop} -> {img}")
    loop_opts.append(["Zpět","r"])
    
    sel = th.menu(
        header=header,
        options=loop_opts,
        prompt="Volba: "
    )
    if sel == "r":
        return
    
    loop = list(loops.keys())[(int(sel)-1)]
    loop=th.normalizeDiskPath(loop,True)

    while True: # operace na vybrané loop zařízení
        
        # najdeme mounty partitions
        devs = list_loop_partitions(loop,True)
        
        dev=devs.get(loop,None)

        header = [
            f"Loop zařízení: {loop}\n0c",
            "Vyber partition pro odpojení:\n0c"
        ]
        if not dev or not dev.children:
            header.append("Nebyly nalezeny připojené partition.") 
            mn_opts=[]
        else:
            header.append("Připojené partition:")
            # mn_opts=[ parts[i].name for i in parts.keys()]        
            mn_opts=[ p.name for p in dev.children]
        
        mn_opts.append([f"Odpojit celé loop zařízení","a"])
        mn_opts.append(["=\n0",None])
        mn_opts.append(["Mount partiion",'m'])
        mn_opts.append(["Zpět","r"])

        sel = th.menu(
            header=header,
            options=mn_opts,
            prompt="Volba: "
        )
        if sel == "r":
            return
        
        elif sel == "m":
            mount_partition_mode(loop)
            continue
        
        elif sel == "a":
            # umount všech
            if dev and dev.children:
                for part in dev.children:
                    mnt = th.normalizeDiskPath(part.name,False)
                    try:
                        print(f"umount {mnt}")
                        th.run(f"sudo umount {mnt}")
                    except Exception as e:
                        print(f"Chyba při umountování {mnt}: {e}")
                        th.anyKey()
            try:
                loop=th.normalizeDiskPath(loop,False)
                print(f"Detach {loop}")
                th.run(f"sudo losetup -d {loop}")
            except Exception as e:
                print(f"Chyba při odpojování {loop}: {e}")
                th.anyKey()
            return
        
        # umount vybrané partition
        part=th.normalizeDiskPath(mn_opts[int(sel)-1],False)
        
        try:
            th.run(f"sudo umount {part}")
            print(f"Odpojeno zařízení {part}")
        except Exception as e:
            print(f"Chyba při umountování {part}: {e}")
            th.anyKey()
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
            data_rows.append([dev, size, fstype, mnts])

    if not data_rows:
        print("Žádné partition.")
        return

    header = ["Zařízení", "Velikost", "Typ", "Mountpoint"]
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
            row[3].ljust(col_widths[3])
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
        
def select_mountpoint()-> str:
    """Umožní uživateli vybrat mount point ze seznamu prázdných mountpointů nebo vytvořit nový.
    Returns:
        str: Cesta k vybranému nebo nově vytvořenému mount pointu.
    """
    while True:
        empty_dirs = list_empty_mountpoints()
        header = "Prázdné mountpointy:"
        opts= []
        for i, d in enumerate(empty_dirs):
            opts.append([ d, str(i+1)])
        opts.append(["Vytvořit nový adresář", 'n'])
        opts.append(["Zpět", 'r'])
        opts.append(["Konec", 'q'])
        volba = th.menu(
            header=[header],
            options=opts,
            prompt="Volba: "
        )
        if volba == 'r':
            return None
        elif volba == 'q':
            exit(0)
        elif volba == 'n':
            name = input("Zadej název subdir: ")
            mount_point = os.path.join(glb.MNT_DIR, name)
            if os.path.exists(mount_point):
                print("Adresář už existuje, zvol jiný název.")
                th.anyKey()
                continue
            try:
                os.makedirs(mount_point, exist_ok=True)
            except Exception as e:
                print(f"Chyba při vytváření adresáře: {e}")
                th.anyKey()
                continue
            return mount_point
        else:
            try:
                idx = int(volba) - 1
            except:
                print("Neplatná volba.")
                th.anyKey()
                continue
            mount_point = empty_dirs[idx]
            return mount_point
        
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
            th.anyKey()
            return
        except Exception as e:
            print(f"Chyba při připojování: {e}")
            th.anyKey()
    
def umount_dev(mount_point: str) -> None:
    """Odpojí zařízení připojené na zadaný mount point.
    Args:
        mount_point (str): Cesta k mount pointu.
    Returns:
        None
    """
    th.run(f"sudo umount {mount_point}")
    print(f"Odpojeno zařízení z {mount_point}")
