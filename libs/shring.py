import re
from pathlib import Path
from typing import Optional, Tuple
import libs.toolhelp as th
import json

# očekávám, že máš modul th s:
# th.run(cmd: str) -> None   (vyhodí exception při chybě)
# th.runRet(cmd: str) -> str
# class th.ShrinkError(Exception): pass

SECTOR_SIZE = 512
TMP_MOUNT = Path("/mnt/__jb_imgtool_shrink__")


def _ensure_not_mounted(token: str) -> None:
    """
    Zkontroluje, že daný image/disk není aktuálně připojen.
    Stačí substring match v `mount` výstupu (stačí pro img cesty).
    """
    mounts = th.runRet("mount")
    if token in mounts:
        raise th.ShrinkError(f"{token} je aktuálně připojený – nejdřív odpoj.")


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
        raise th.ShrinkError(
            f"Nenašla jsem partition {disk}p{part} v sfdisk dumpu."
        )

    return dump, start_sector, size_sectors, max_end


def _apply_new_size_to_sfdisk_dump(raw_dump: str, disk: str, part_index: int, new_sectors: int) -> str:
    """
    Úprava size= u konkrétní partition v sfdisk -d dumpu.
    """
    part_name = _make_part_dev(disk, part_index).split("/")[-1]   # sdc2, mmcblk0p1, loop0p2...

    lines = raw_dump.splitlines()
    out = []
    changed = False

    # regex, který ignoruje mezery:
    # size=\s*\d+
    size_re = re.compile(r"(size=\s*)(\d+)")

    for line in lines:
        stripped = line.strip()

        if stripped.startswith(f"/dev/{part_name}"):
            # nahradíme pouze size=
            def repl(m):
                return f"{m.group(1)}{new_sectors}"
            new_line, count = size_re.subn(repl, line)
            if count == 0:
                raise th.ShrinkError(f"Partition řádek nalezen, ale size= nebyl nalezen: {line}")
            line = new_line
            changed = True

        out.append(line)

    if not changed:
        raise th.ShrinkError("Nepodařilo se upravit size= v řádku partition.")

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


def _make_part_dev(disk: str, part_index: int) -> str:
    """
    Vrátí správný název partition podle typu zařízení:
      /dev/sdc  + 2      → /dev/sdc2
      /dev/mmcblk0 + 2   → /dev/mmcblk0p2
      /dev/loop0 + 2     → /dev/loop0p2
      /dev/nvme0n1 + 2   → /dev/nvme0n1p2
    """
    # zařízení končící číslem (mmcblk0, loop0, nvme0n1, atd.) → potřebují 'p'
    if re.search(r'\d$', disk):
        return f"{disk}p{part_index}"
    else:
        return f"{disk}{part_index}"

def _shrink_partition_common(
    disk: str,
    part_index: int,
    target_gib: Optional[int],
    is_loop_backed: bool,
    img_file: Optional[Path] = None,
    tmp_mount: Path = TMP_MOUNT,
) -> Tuple[int, Optional[int]]:
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
        is_loop_backed: True = je to loop (IMG), False = fyzický disk
        img_file: Path k IMG (povinné, pokud is_loop_backed=True)
        tmp_mount: dočasný mountpoint

    Returns:
        (target_bytes, new_img_size_bytes_or_None)
        target_bytes = cílová velikost filesystemu v bajtech
        new_img_size_bytes = pokud loop → na kolik by se měl truncate IMG
                             pokud fyzický disk → None
    """
    print(f"[INFO] Shrinking partition {part_index} on {disk}")
    print(f"[INFO] Temporary mount point: {tmp_mount}")
    print(f"[INFO] Is loop-backed: {is_loop_backed}")
    print(f"[INFO] Target size (GiB): {target_gib if target_gib is not None else 'auto'}")    
    
    part_dev = _make_part_dev(disk, part_index)

    # vytvoříme mountpoint
    tmp_mount.mkdir(exist_ok=True, mode=0o755)

    # 1) mount pro zjištění used space
    th.run(f"sudo mount {part_dev} {tmp_mount}")
    df_out = th.runRet(f"df -B1 {tmp_mount}")
    # poslední řádek df je náš FS
    used_bytes = int(df_out.splitlines()[-1].split()[2])
    th.run(f"sudo umount {tmp_mount}")

    if target_gib is None:
        target_gib = _auto_target_gib_from_used(used_bytes)

    if target_gib < 1:
        raise th.ShrinkError("Cílová velikost musí být alespoň 1 GiB.")

    target_bytes = target_gib * (1024 ** 3)

    print(f"[INFO] Used: {used_bytes/1e9:.2f} GB")
    print(f"[INFO] Target FS size: {target_bytes/1e9:.2f} GB (≈ {target_gib} GiB)")

    # 2) e2fsck
    th.run(f"sudo e2fsck -f {part_dev}")

    # 3) resize2fs
    th.run(f"sudo resize2fs {part_dev} {target_gib}G")

    # 4) přepočet sektorů pro partition
    new_sectors = target_bytes // SECTOR_SIZE

    # 5) sfdisk -d a úprava partition tabulky
    print(f"[INFO] Updating partition table for disk {disk}...")
    
    
    dump = th.runRet(f"sudo sfdisk -d {disk}")

    raw_dump, start_sector, old_size, max_end = _parse_sfdisk_dump(
        dump, disk, part_index
    )

    if new_sectors > old_size:
        raise th.ShrinkError(
            f"Nová velikost partition ({new_sectors} sektorů) je větší než původní ({old_size})."
        )

    new_dump = _apply_new_size_to_sfdisk_dump(raw_dump, disk, part_index, new_sectors)

    # 6) zapsat novou partition tabulku
    with open("/tmp/pt.txt", "wb") as f:
        f.write(new_dump.encode("utf-8"))

    with open("/tmp/pt.txt", "rb") as f:
        th.run(["sudo", "sfdisk", disk], input_bytes=f.read())

    # někomu se hodí:
    print(f"[INFO] Partition {disk}p{part_index}: start={start_sector}, old_size={old_size}, new_size={new_sectors}")

    # 7) výpočet nové velikosti image, pokud je to loop a partition je poslední
    new_img_size = None
    if is_loop_backed:
        if img_file is None:
            raise th.ShrinkError("img_file musí být zadán, pokud je is_loop_backed=True.")

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

def detect_partitions(device: str):
    """
    Zjistí partition layout pro zařízení /dev/sdX nebo /dev/mmcblkX.
    Vrací list:
      [ { "name": "/dev/sdc1", "fstype": "...", "size": "...", "index": 1 }, ... ]
    """
    device = Path(device).as_posix()
    
    # JSON formát lsblk
    out = th.runRet(f"lsblk -J {device}")
    js = json.loads(out)

    if "blockdevices" not in js or len(js["blockdevices"]) == 0:
        raise th.ShrinkError(f"Zařízení {device} není platné nebo lsblk nenašlo žádná data")

    entry = js["blockdevices"][0]

    # Pokud není "children", tak to není disk → je to přímo partition
    if "children" not in entry or entry["children"] is None:
        # vracíme přímo tuto jednu partition
        return [{
            "name": device,
            "fstype": entry.get("fstype"),
            "size": entry.get("size"),
            "index": None,   # nevíme
        }]

    result = []
    for ch in entry["children"]:
        # child jméno je např: "sdc2" → uděláme /dev/sdc2
        name = "/dev/" + ch["name"]
        fstype = ch.get("fstype")
        size = ch.get("size")

        # zjistíme číslo partition
        m = re.match(r".*?(\d+)$", name)
        idx = int(m.group(1)) if m else None

        result.append({
            "name": name,
            "fstype": fstype,
            "size": size,
            "index": idx
        })

    return result

def shrink_image(file: str, spaceSize: Optional[int] = None, part_index: int = 2) -> Tuple[int, str]:
    """
    Zmenší ext4 IMG soubor (s GPT/MBR) na minimální nebo uživatelem zadanou velikost.

    Args:
        file: cesta k IMG souboru
        spaceSize: cílová velikost v GiB (>=1). Pokud None, spočítá se automaticky (used + 10 %).
        part_index: číslo partition s root FS (default 2)

    Returns:
        (new_fs_size_bytes, path_to_result_img)
    """
    img = Path(file).resolve()
    if not img.exists():
        raise th.ShrinkError(f"IMG soubor neexistuje: {img}")

    _ensure_not_mounted(img.as_posix())

    # 1) vytvořit loopdevice
    loop = th.runRet(
        f"sudo losetup --find --show --partscan {img}"
    ).strip()

    print(f"[INFO] Používám loop zařízení: {loop}")

    try:
        target_bytes, new_img_size = _shrink_partition_common(
            disk=loop,
            part_index=part_index,
            target_gib=spaceSize,
            is_loop_backed=True,
            img_file=img,
            tmp_mount=TMP_MOUNT,
        )
    finally:
        # odpojení loopu (i když něco spadne)
        try:
            th.run(f"sudo losetup -d {loop}")
        except Exception:
            pass

    if new_img_size is None:
        raise th.ShrinkError("Interní chyba: new_img_size je None u loop-backed image.")

    # 2) truncate IMG na novou velikost
    th.run(f"truncate -s {new_img_size} {img}")
    print(f"[DONE] New image size: {new_img_size/1e9:.2f} GB")

    return target_bytes, str(img)

def parse_device_and_partition(device: str):
    """
    Pokud dostaneš /dev/sdc → vrátí ("disk", "/dev/sdc", None)
    Pokud dostaneš /dev/sdc2 → vrátí ("partition", "/dev/sdc", 2)
    """
    dev = device.strip()

    m = re.match(r"(/dev/[a-zA-Z0-9]+?)(\d+)$", dev)
    if m:
        # /dev/sdc2
        base = m.group(1)
        idx  = int(m.group(2))
        return ("partition", base, idx)
    else:
        # /dev/sdc
        return ("disk", dev, None)


def shrink_disk(device: str, spaceSize: Optional[int] = None, part_index: Optional[int] = None) -> int:
    """
    Shrink ext4 filesystem na fyzickém disku. 'device' může být disk nebo partition.
    """
    # 1) Rozpoznat vstup: disk nebo partition
    kind, base_disk, detected_idx = parse_device_and_partition(device)

    if kind == "partition":
        # Uživatel zadal /dev/sdc2
        disk = base_disk              # → /dev/sdc
        if part_index is None:
            part_index = detected_idx # → 2
    else:
        # Uživatel zadal /dev/sdc
        disk = base_disk              # → /dev/sdc
        if part_index is None:
            # autodetekovat ext4 partition
            parts = detect_partitions(disk)
            ext = next((p for p in parts if p["fstype"] == "ext4"), None)
            if not ext:
                raise th.ShrinkError(f"Na disku {disk} není ext4 partition.")
            part_index = ext["index"]

    # 2) Zkontrolovat mount — použít helper
    part_dev = _make_part_dev(disk, part_index)
    _ensure_not_mounted(part_dev)

    # 3) Spustit hlavní logiku
    target_bytes, _ = _shrink_partition_common(
        disk=disk,
        part_index=part_index,
        target_gib=spaceSize,
        is_loop_backed=False,
        img_file=None,
        tmp_mount=TMP_MOUNT,
    )

    print(f"[DONE] Disk {disk}, partition {part_index} → ≈ {target_bytes/1e9:.2f} GB")
    return target_bytes

