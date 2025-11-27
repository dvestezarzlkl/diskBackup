import re
from pathlib import Path
from typing import Optional, Tuple
import libs.toolhelp as th
import libs.mounting as mt

# očekávám, že máš modul th s:
# th.run(cmd: str) -> None   (vyhodí exception při chybě)
# th.runRet(cmd: str) -> str
# class ShrinkError(Exception): pass

SECTOR_SIZE = 512
TMP_MOUNT = Path("/mnt/__jb_imgtool_shrink__")


class ShrinkError(Exception):
    """Custom exception for shrink operations."""
    pass

def _ensure_not_mounted(token: str) -> None:
    """
    Zkontroluje, že daný image/disk není aktuálně připojen.
    Stačí substring match v `mount` výstupu (stačí pro img cesty).
    """
    mounts = th.runRet("mount")
    if token in mounts:
        raise ShrinkError(f"{token} je aktuálně připojený – nejdřív odpoj.")


def _parse_sfdisk_dump(dump: str, disk: str, part: int) -> Tuple[str, int, int, int]:
    """
    Z dumpu sfdisk -d vytáhne:
      - upravený dump s novou velikostí (zatím vyplníme až ve volajícím)
      - původní start sektoru dané partition
      - původní size (počet sektorů)
      - max_end_sector všech partitions (pro kontrolu „poslední partition“)

    Vrací: (raw_dump, start_sector, size_sectors, max_end_sector)
    """
    lines = dump.splitlines()
    part_name_no_p = f"{disk}{part}"
    part_name_with_p = f"{disk}p{part}"

    start_sector = None
    size_sectors = None
    max_end = 0

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("#"):
            continue

        # hledáme řádky typu:
        # /dev/loop0p2 : start=..., size=..., type=...
        if line_stripped.startswith(part_name_with_p) or line_stripped.startswith(part_name_no_p):
            # rozsekáme za dvojtečkou
            try:
                _, rest = line_stripped.split(":", 1)
            except ValueError:
                continue

            parts = [p.strip() for p in rest.split(",")]

            for p in parts:
                if p.startswith("start="):
                    start_sector = int(p.split("=")[1])
                if p.startswith("size="):
                    size_sectors = int(p.split("=")[1])

        # zároveň si sbíráme všechny part řádky pro max_end
        if (line_stripped.startswith(disk) and
            (" start=" in line_stripped) and
            (" size=" in line_stripped)):
            # obecné parsování
            try:
                _, rest = line_stripped.split(":", 1)
            except ValueError:
                continue
            parts = [p.strip() for p in rest.split(",")]
            s = None
            sz = None
            for p in parts:
                if p.startswith("start="):
                    s = int(p.split("=")[1])
                if p.startswith("size="):
                    sz = int(p.split("=")[1])
            if s is not None and sz is not None:
                end = s + sz
                if end > max_end:
                    max_end = end

    if start_sector is None or size_sectors is None:
        raise ShrinkError(
            f"Nenašla jsem partition {disk}p{part} v sfdisk dumpu."
        )

    return dump, start_sector, size_sectors, max_end


def _apply_new_size_to_sfdisk_dump(raw_dump: str, disk: str, partition: str, new_sectors: int) -> str:
    """
    Úprava size= u konkrétní partition v sfdisk -d dumpu.
    """
    
    lines = raw_dump.splitlines()
    out = []
    changed = False

    # regex, který ignoruje mezery:
    # size=\s*\d+
    size_re = re.compile(r"(size=\s*)(\d+)")
    partition = th.normalizeDiskPath(partition)

    for line in lines:
        stripped = line.strip()

        if stripped.startswith(partition):
            # nahradíme pouze size=
            def repl(m):
                return f"{m.group(1)}{new_sectors}"
            new_line, count = size_re.subn(repl, line)
            if count == 0:
                raise ShrinkError(f"Partition řádek nalezen, ale size= nebyl nalezen: {line}")
            line = new_line
            changed = True

        out.append(line)

    if not changed:
        raise ShrinkError("Nepodařilo se upravit size= v řádku partition.")

    return "\n".join(out) + "\n"



def _auto_target_gib_from_used(used_bytes: int) -> int:
    """
    Vypočte cílovou velikost v GiB:
    used + 10 % + min 1 GiB.
    """
    one_gib = 1024 ** 3
    auto = int(used_bytes * 1.10)
    if auto < one_gib:
        auto = one_gib
    # zaokrouhlit nahoru na celé GiB
    target_gib = (auto + one_gib - 1) // one_gib
    return target_gib

def _shrink_partition_common(
    disk: str,
    partition: str,
    part_index: int,
    target_gib: Optional[int],
) -> Tuple[int|None, Optional[int]]:
    """
    Společná logika shrinku:
      - zjistí used space
      - spočítá cílovou velikost
      - e2fsck + resize2fs
      - upraví partition tabulku (sfdisk)

    Args:
        disk: /dev/sdX nebo /dev/loopX (celý disk, ne partition!)
        part_index: číslo partition (typicky 2)
        target_gib: cílová velikost v GiB nebo None (auto)

    Returns:
        (None,None) pokud uživatel zrušil operaci
        (target_bytes, new_img_size_bytes_or_None)
        target_bytes = cílová velikost filesystemu v bajtech
        new_img_size_bytes = pokud loop → na kolik by se měl truncate IMG
                             pokud fyzický disk → None
    """
    if th.confirm(
        f"Opravdu chcete minimalizovat ext4 filesystem na disku {disk}, partition {part_index} ({partition})?"
    ) is False:
        print("[INFO] Operace zrušena uživatelem.")
        return None, None
    
    disk = th.normalizeDiskPath(disk)
    partition = th.normalizeDiskPath(partition)
    
    print(f"[INFO] Shrinking partition {part_index} on {disk}")
    print(f"[INFO] Target size (GiB): {target_gib if target_gib is not None else 'auto'}")    
    
    # vytvoříme mountpoint
    tmp_mount = Path(TMP_MOUNT)
    tmp_mount.mkdir(exist_ok=True, mode=0o755)

    # 1) mount pro zjištění used space
    th.run(f"sudo mount {partition} {tmp_mount}")
    df_out = th.runRet(f"df -B1 {tmp_mount}")
    # poslední řádek df je náš FS
    used_bytes = int(df_out.splitlines()[-1].split()[2])
    th.run(f"sudo umount {tmp_mount}")

    if target_gib is None:
        target_gib = _auto_target_gib_from_used(used_bytes)

    if target_gib < 1:
        raise ShrinkError("Cílová velikost musí být alespoň 1 GiB.")

    target_bytes = target_gib * (1024 ** 3)

    print(f"[INFO] Used: {used_bytes/1e9:.2f} GB")
    print(f"[INFO] Target FS size: {target_bytes/1e9:.2f} GB (≈ {target_gib} GiB)")

    # 2) e2fsck
    th.run(f"sudo e2fsck -f {partition}")

    # 3) resize2fs
    th.run(f"sudo resize2fs {partition} {target_gib}G")

    # 4) přepočet sektorů pro partition
    new_sectors = target_bytes // SECTOR_SIZE

    # 5) sfdisk -d a úprava partition tabulky
    print(f"[INFO] Updating partition table for disk {disk}...")
    
    
    dump = th.runRet(f"sudo sfdisk -d {disk}")

    raw_dump, start_sector, old_size, max_end = _parse_sfdisk_dump(
        dump, disk, part_index
    )

    if new_sectors > old_size:
        raise ShrinkError(
            f"Nová velikost partition ({new_sectors} sektorů) je větší než původní ({old_size})."
        )

    new_dump = _apply_new_size_to_sfdisk_dump(raw_dump, disk, partition, new_sectors)

    # 6) zapsat novou partition tabulku
    with open("/tmp/pt.txt", "wb") as f:
        f.write(new_dump.encode("utf-8"))

    with open("/tmp/pt.txt", "rb") as f:
        th.run(["sudo", "sfdisk", disk], input_bytes=f.read())

    # někomu se hodí:
    print(f"[INFO] Partition {disk}p{part_index}: start={start_sector}, old_size={old_size}, new_size={new_sectors}")

    # přepočítáme max_end z nového layoutu
    new_dump2 = th.runRet(f"sudo sfdisk -d {disk}")
    _, _, _, new_max_end = _parse_sfdisk_dump(new_dump2, disk, part_index)

    # chceme truncate na poslední používaný sektor (poslední partition)
    new_img_size = new_max_end * SECTOR_SIZE
    print(f"[INFO] New image size (from GPT last partition end): {new_img_size/1e9:.2f} GB")

    # úklid mountpointu (pokud je prázdný)
    try:
        tmp_mount.rmdir()
    except OSError:
        # někdy tam zůstane, nevadí
        pass

    return target_bytes, new_img_size

def shrink_disk(
    partition: str,
    spaceSize: Optional[int] = None,
    part_index: Optional[int] = None,
    spaceSizeQuestion: bool = False,
) -> int:
    """
    Shrink ext4 filesystem na fyzickém disku.
    
    Args:
        device: /dev/sdX nebo /dev/sdXn
        spaceSize: cílová velikost v GiB (>=1). Pokud None, použije se automatická volba.
        part_index: číslo partition (pokud device je disk). Pokud None, autodetekce ext4 partition.
        spaceSizeQuestion: pokud True a spaceSize je None, zeptá se uživatele na cílovou velikost.
    
    """
    partition = th.normalizeDiskPath(partition,True)
    device_info = th.getDiskByPartition(partition)
    if device_info is None:
        print(f"Nepodařilo se najít disk pro partition {partition}.")
        return 0
    
    device = th.normalizeDiskPath(device_info.name)
    
    # kontrola že partititon je ext4
    part_info = None
    idx=None
    for index, part in enumerate(device_info.children):
        if th.normalizeDiskPath(part.name,True) == partition:
            part_info = part
            idx = index
            break
        
    part_index = idx + 1  # partition index je 1-based
        
    if part_info is None or part_info.fstype != "ext4":
        print(f"Nepodařilo se najít ext4 partition {partition} na disku {device}.")
        return 0
    
    # dotaz na velikost
    if spaceSizeQuestion and spaceSize is None:
        while True:
            ans = input("Zadejte cílovou velikost po shrinku (např. 2G, 500M) nebo 'a' pro automatickou volbu: ").strip().lower()
            if ans == 'a':
                spaceSize = None
                break
            m = re.match(r"^(\d+)([gGmM])$", ans)
            if m:
                size_val = int(m.group(1))
                size_unit = m.group(2).upper()
                if size_unit == 'G':
                    spaceSize = size_val
                elif size_unit == 'M':
                    spaceSize = max(1, size_val // 1024)  # převod na GiB, min 1 GiB
                break
            else:
                print("Neplatný formát. Zkuste to znovu.")
    
    mp=[p for p in part_info.mountpoints if p]
    
    # otestujeme že nemáme připojeno
    if mp:
        print(f"Partition {partition} je připojena na {', '.join(mp)}. Nejprve ji odpojte.")
        return 0

    # Spustit hlavní logiku
    target_bytes, _ = _shrink_partition_common(
        disk=device,
        partition=partition,
        part_index=part_index,
        target_gib=spaceSize,
        is_loop_backed=False,
        img_file=None,
        tmp_mount=TMP_MOUNT,
    )
    if target_bytes is None:
        print("Operace shrink byla zrušena uživatelem.")
        return 0

    print(f"[DONE] Disk {device}, partition {part_index} → ≈ {target_bytes/1e9:.2f} GB")
    return target_bytes

def extend_disk_part_max(
    dev_partition: str,
) -> int|None:
    """
    Rozšíří ext4 filesystem na fyzickém disku na zadanou velikost v GiB.
    'device' může být disk nebo partition.
    Args:
        device: /dev/sdX nebo /dev/sdXn
        new_size_gib: nová velikost v GiB (>=1). Pokud None, zvětší se na maximum.
    Returns:
        nová velikost filesystemu v bajtech nebo None při zrušení uživatelem.
    """
    dev_partition = th.normalizeDiskPath(dev_partition,True)
    
    diskInfo=th.getDiskByPartition(dev_partition)
    if diskInfo is None:
        print(f"Nepodařilo se najít disk pro partition {dev_partition}.")
        return None
    
    disk= th.normalizeDiskPath(diskInfo.name)
        
    idx=None
    for index, part in enumerate(diskInfo.children):
        if th.normalizeDiskPath(part.name,True) == dev_partition and part.fstype == "ext4":
            part_info = part
            idx = index
            break
    if idx is None:
        print(f"Nepodařilo se najít ext4 partition {dev_partition} na disku {disk}.")
        return None
    
    part_index = idx + 1  # partition index je 1-based

    if idx != len(diskInfo.children)-1:
        print(f"Partition {dev_partition} není poslední na disku {disk}. Nelze automaticky zvětšit na maximum.")
        return None
   
    print(f"[INFO] Extending partition {part_index} ({dev_partition}) on disk {disk} to size: maximum")
    
    if th.confirm(
        f"Opravdu chcete rozšířit ext4 filesystem na disku {disk}, partition {part_index} ({dev_partition})?"
    ) is False:
        print("[INFO] Operace zrušena uživatelem.")
        return None
        
    dev_partition = th.normalizeDiskPath(dev_partition,False)
    # grow partition na maximum
    th.run(f"sudo growpart {disk} {part_index}")
    # maximize filesystem
    th.run(f"sudo resize2fs {dev_partition}")
    
    
    # zjistit novou velikost
    tune = th.runRet(f"tune2fs -l {dev_partition}")
    block_count = None
    block_size = None

    for line in tune.splitlines():
        if line.startswith("Block count:"):
            block_count = int(line.split()[-1])
        elif line.startswith("Block size:"):
            block_size = int(line.split()[-1])

    if block_count is None or block_size is None:
        print("[ERROR] Nepodařilo se přečíst velikost EXT4 z tune2fs.")
        return None
    
    mt.print_partitions(filter=dev_partition)
    return block_count * block_size
