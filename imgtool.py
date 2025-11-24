#!/usr/bin/env python3
"""
imgtool.py – nástroj pro práci s diskovými obrazy

Režimy:
  backup        – raw záloha celého disku (dd), volitelně gzip
  restore       – obnova raw nebo gzip obrazu na disk
  extract       – rozbalení .img.gz na .img

  smart-backup  – „chytrá“ záloha: layout (GPT/MBR) + každá partition zvlášť (partclone)
  smart-restore – obnova layoutu + partitions, volitelně --resize poslední ext4 na celý disk

  compress      – gzip komprese existujícího .img (např. po editaci)
  decompress    – dekomprese .img.gz → .img

Vlastnosti:
  - SHA256 vždy generovaný pro každý výstupní soubor (*.sha256)
  - při restore/ smart-restore se SHA kontroluje (lze vypnout --no-sha)
  - gzip se použije jen, pokud je zadán --fast nebo --max
  - autoprefix (YYYY-MM-DD-HHMM_disk_...) je default, vypne se --noautoprefix
"""

from __future__ import annotations

from typing import Optional, Tuple
import argparse
import datetime
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any
import libs.toolhelp as th
import libs.shring as shr

# ============================================================
# Low-level helpers
# ============================================================

def check_output(cmd: List[str]) -> bytes:
    """Vrátí stdout daného příkazu (bytes) nebo vyhodí výjimku."""
    print(f"[CMD] {' '.join(cmd)}")
    return subprocess.check_output(cmd)


def sha256_file(path: Path) -> str:
    """Vypočítá SHA256 pro daný soubor."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def write_sha256_sidecar(path: Path) -> None:
    """Vytvoří <soubor>.sha256 s hash + názvem souboru."""
    digest = sha256_file(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    print(f"[SHA256] {sidecar} ({digest})")


def verify_sha256_sidecar(path: Path) -> bool:
    """
    Zkontroluje, zda soubor odpovídá uloženému SHA256.
    Očekává <soubor>.sha256.
    """
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.exists():
        print(f"[SHA256] Sidecar {sidecar} neexistuje – přeskočeno.")
        return False

    content = sidecar.read_text(encoding="utf-8").strip()
    if not content:
        print(f"[SHA256] Prázdný sidecar {sidecar}.")
        return False

    expected = content.split()[0]
    actual = sha256_file(path)
    if actual == expected:
        print(f"[SHA256] OK: {path.name}")
        return True

    print(f"[SHA256] MISMATCH: {path.name}")
    print(f"   expected: {expected}")
    print(f"   actual  : {actual}")
    return False


def human_size(num_bytes: int) -> str:
    """Převod velikosti v bajtech na čitelný string (MiB/GiB)."""
    step = 1024.0
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(num_bytes)
    idx = 0
    while size >= step and idx < len(units) - 1:
        size /= step
        idx += 1
    return f"{size:.1f} {units[idx]}"



def confirm(msg: str) -> bool:
    """Vrátí True pokud uživatel odpověděl 'y' nebo 'Y'."""
    return input(msg + " [y/N]: ").lower() == "y"


def is_gzip(path: Path) -> bool:
    """Detekce gzip podle přípony."""
    return path.suffix == ".gz" or path.name.endswith(".img.gz")


# ============================================================
# Simple backup / restore / extract (dd)
# ============================================================

def generate_base_name(disk: str, base: str | None, autoprefix: bool) -> str:
    """
    Vygeneruje základ jména souboru.
    - pokud base je zadané, použije se
    - jinak 'disk'
    - autoprefix -> YYYY-MM-DD-HHMM_disk_base
    """
    if not base:
        base = disk
    if autoprefix:
        prefix = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
        return f"{prefix}_{base}"
    return base


def backup_disk_raw(disk: str, base: str | None, fast: bool, maxC: bool,
                    autoprefix: bool) -> None:
    """
    Záloha celého /dev/<disk> přes dd.
    Bez komprese, pokud není --fast / --max.
    Vždy se vytvoří SHA256 sidecar.
    """
    dev = f"/dev/{disk}"
    base_name = generate_base_name(disk, base, autoprefix)

    # rozhodnutí o kompresi
    if fast:
        out = Path(base_name + ".img.gz")
        print(f"Záloha disku {dev} → {out} (gzip -1)")
        if not confirm("Spustit backup s rychlou kompresí?"):
            print("Zrušeno.")
            return
        dd = ["dd", f"if={dev}", "bs=4M", "status=progress"]
        gz = ["gzip", "-1"]
        with out.open("wb") as f:
            p1 = subprocess.Popen(dd, stdout=subprocess.PIPE)
            p2 = subprocess.Popen(gz, stdin=p1.stdout, stdout=f)
            p1.stdout.close()
            p2.communicate()
    elif maxC:
        out = Path(base_name + ".img.gz")
        print(f"Záloha disku {dev} → {out} (gzip -9)")
        if not confirm("Spustit backup s maximální kompresí?"):
            print("Zrušeno.")
            return
        dd = ["dd", f"if={dev}", "bs=4M", "status=progress"]
        gz = ["gzip", "-9"]
        with out.open("wb") as f:
            p1 = subprocess.Popen(dd, stdout=subprocess.PIPE)
            p2 = subprocess.Popen(gz, stdin=p1.stdout, stdout=f)
            p1.stdout.close()
            p2.communicate()
    else:
        out = Path(base_name + ".img")
        print(f"Záloha disku {dev} → {out} (RAW, bez gzip)")
        if not confirm("Spustit backup bez komprese?"):
            print("Zrušeno.")
            return
        th.run(["dd", f"if={dev}", f"of={str(out)}", "bs=4M", "status=progress"])

    write_sha256_sidecar(out)
    print(f"Hotovo: {out}")


def restore_disk_raw(filename: Path, disk: str, no_sha: bool) -> None:
    """
    Obnova RAW nebo .gz obrazu na /dev/<disk>.
    Před zápisem ověří SHA256, pokud existuje sidecar a není --no-sha.
    """
    dev = f"/dev/{disk}"
    if not filename.exists():
        raise FileNotFoundError(filename)

    print(f"\nObnova {filename} → {dev}")
    if not no_sha:
        ok = verify_sha256_sidecar(filename)
        if not ok:
            if not confirm("Hash nesedí nebo sidecar chybí. Pokračovat i tak?"):
                print("Zrušeno.")
                return

    if not confirm("!!! Tohle přepíše celý disk. Pokračovat?"):
        print("Zrušeno.")
        return

    if is_gzip(filename):
        cmd = ["bash", "-c", f"gunzip -c '{filename}' | dd of={dev} bs=4M status=progress"]
        th.run(cmd)
    else:
        th.run(["dd", f"if={str(filename)}", f"of={dev}", "bs=4M", "status=progress"])

    print("Obnova dokončena.")


def extract_gz_to_img(filename: Path) -> None:
    """
    Rozbalí .img.gz na .img (stejné jméno bez .gz).
    SHA se vygeneruje pro rozbalený soubor.
    """
    if not filename.exists():
        raise FileNotFoundError(filename)
    if not is_gzip(filename):
        print("Soubor není .gz – není co extrahovat.")
        return

    print(f"Extract {filename} → gunzip")
    th.run(["gunzip", str(filename)])
    out = Path(str(filename).removesuffix(".gz"))
    if out.exists():
        write_sha256_sidecar(out)
        print(f"Extract hotov: {out}")
    else:
        print("Extract se nepovedl – výstupní soubor neexistuje.")


# ============================================================
# Smart backup / restore (layout + partitions)
# ============================================================

def detect_fs(devPath: str) -> str | None:
    """Zjistí typ FS buď z blkid, nebo vrátí None."""
    try:
        fs = check_output(["blkid", "-o", "value", "-s", "TYPE", devPath]).decode().strip()
        return fs if fs else None
    except subprocess.CalledProcessError:
        return None


def partclone_program_for_fs(fs: str) -> str | None:
    """Vrátí vhodný partclone.* binárku pro daný FS, nebo None."""
    fs = fs.lower()
    if fs in ("ext2", "ext3", "ext4"):
        return "partclone.extfs"
    if fs in ("vfat", "fat", "fat32"):
        return "partclone.vfat"
    if fs == "ntfs":
        return "partclone.ntfs"
    # další FS lze doplnit podle potřeby
    return None


def backup_layout(disk: str, folder: Path) -> Path:
    """
    Záloha GPT nebo MBR layoutu do souboru.
    Upřednostňuje GPT (sgdisk), jinak sfdisk.
    """
    dev = f"/dev/{disk}"
    gpt_file = folder / "layout.gpt"
    try:
        th.run(["sgdisk", f"--backup={gpt_file}", dev])
        return gpt_file
    except subprocess.CalledProcessError:
        sfd_file = folder / "layout.sfdisk"
        data = check_output(["sfdisk", "-d", dev])
        sfd_file.write_bytes(data)
        return sfd_file


def restore_layout(disk: str, folder: Path, layout_name: str) -> None:
    """
    Obnova layoutu z uloženého souboru (layout.gpt nebo layout.sfdisk).
    """
    dev = f"/dev/{disk}"
    path = folder / layout_name
    if not path.exists():
        raise FileNotFoundError(path)

    if layout_name.endswith(".gpt"):
        th.run(["sgdisk", f"--load-backup={path}", dev])
    elif layout_name.endswith(".sfdisk"):
        data = path.read_bytes()
        th.run(["sfdisk", dev], input_bytes=data)
    else:
        raise ValueError(f"Neznámý typ layout souboru: {layout_name}")

    # Necháme kernel znovu načíst partition tabulku
    th.run(["partprobe", dev])


def backup_partition_image(
    devName: str,
    folder: Path,
    prefix: str | None,
    fast: bool,
    maxC: bool
) -> Dict[str, Any]:
    """
    Záloha jedné partition pomocí partclone.* (pokud je podporovaný FS) nebo dd fallback.
    Vrací meta informace pro manifest.
    """
    devPath = f"/dev/{devName}"
    fs = detect_fs(devPath)
    size_bytes = int(check_output(["blockdev", "--getsize64", devPath]).decode().strip())
    human = human_size(size_bytes)

    base = f"{devName}.img"
    if prefix:
        base = f"{prefix}_{base}"
    out = folder / base

    print(f"\n[SMART] Backup partition {devPath} ({fs}, {human})")

    pc_prog = partclone_program_for_fs(fs) if fs else None

    # Rozhodnutí – partclone nebo dd
    if pc_prog:
        print(f"Používám {pc_prog} (partclone).")
        th.run([pc_prog, "-c", "-s", devPath, "-o", str(out)])
    else:
        print("FS není podporován partclone – používám dd fallback.")
        th.run(["dd", f"if={devPath}", f"of={str(out)}", "bs=4M", "status=progress"])

    # Komprese (jen pokud fast/max)
    if fast or maxC:
        level = "-1" if fast else "-9"
        gz = Path(str(out) + ".gz")
        print(f"Komprese {out} → {gz} (gzip {level})")
        dd = ["dd", f"if={str(out)}", "bs=4M"]
        gz_cmd = ["gzip", level]
        with gz.open("wb") as f:
            p1 = subprocess.Popen(dd, stdout=subprocess.PIPE)
            p2 = subprocess.Popen(gz_cmd, stdin=p1.stdout, stdout=f)
            p1.stdout.close()
            p2.communicate()
        out.unlink()  # původní .img smažeme, zůstane .img.gz
        out = gz

    write_sha256_sidecar(out)

    return {
        "name": devName,
        "devpath": devPath,
        "fstype": fs,
        "size_bytes": size_bytes,
        "size_human": human,
        "image": out.name,
        "sha256_file": out.name + ".sha256",
    }


def smart_backup(
    disk: str,
    outdir: Path,
    fast: bool,
    maxC: bool,
    autoprefix: bool
) -> None:
    """
    SMART BACKUP:
      - uloží diskový layout
      - zálohuje každou partition do zvláštního image
      - vytvoří manifest.json
    """
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    prefix = f"{ts}_{disk}" if autoprefix else None

    print(f"=== SMART BACKUP /dev/{disk} → {outdir} ===")

    layout_path = backup_layout(disk, outdir)

    # lsblk JSON s velikostmi
    info = json.loads(check_output(["lsblk", "-b", "-J", f"/dev/{disk}"]))
    devInfo = info["blockdevices"][0]
    parts = devInfo.get("children", [])

    manifest: Dict[str, Any] = {
        "disk": disk,
        "created": ts,
        "size_bytes": int(devInfo.get("size", 0)),
        "size_human": human_size(int(devInfo.get("size", 0))),
        "layout_file": layout_path.name,
        "partitions": [],
    }

    for p in parts:
        if p.get("type") != "part":
            continue
        devName = p["name"]
        entry = backup_partition_image(devName, outdir, prefix, fast, maxC)
        manifest["partitions"].append(entry)

    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nSMART BACKUP dokončen. Manifest: {outdir / 'manifest.json'}")


def restore_partition_image(
    image_path: Path,
    devpath: str,
    no_sha: bool
) -> None:
    """
    Obnova jedné partition pomocí partclone.restore (--restore_raw).
    Umí .img i .img.gz, validuje SHA pokud není no_sha=True.
    """
    print(f"[SMART] Restore {image_path} → {devpath}")

    if not image_path.exists():
        raise FileNotFoundError(image_path)

    if not no_sha:
        ok = verify_sha256_sidecar(image_path)
        if not ok and not confirm("Hash nesedí nebo chybí – pokračovat i tak?"):
            print("Zrušeno.")
            return

    if is_gzip(image_path):
        # gunzip -c image | partclone.restore --restore_raw -C -s - -o dev
        p1 = subprocess.Popen(["gunzip", "-c", str(image_path)], stdout=subprocess.PIPE)
        p2 = subprocess.Popen(
            ["partclone.restore", "--overwrite", "--restore_raw", "-C", "-s", "-", "-o", devpath],
            stdin=p1.stdout
        )
        p1.stdout.close()
        p2.communicate()
    else:
        th.run(["partclone.restore", "--overwrite", "--restore_raw", "-C", "-s", str(image_path), "-o", devpath])


def smart_restore(
    disk: str,
    inDir: Path,
    resize: bool,
    no_sha: bool
) -> None:
    """
    SMART RESTORE:
      - načte manifest.json
      - obnoví layout
      - obnoví každou partition
      - volitelně roztáhne poslední ext4 partition na celý disk (--resize)
    """
    if not inDir.is_dir():
        raise NotADirectoryError(inDir)

    manifest_path = inDir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    layout_file = manifest["layout_file"]

    print(f"=== SMART RESTORE → /dev/{disk} z {inDir} ===")

    restore_layout(disk, inDir, layout_file)

    for part_info in manifest["partitions"]:
        devPath = part_info["devpath"]
        image = inDir / part_info["image"]
        restore_partition_image(image, devPath, no_sha=no_sha)

    # Volitelné zvětšení poslední ext4 partition
    if resize and manifest["partitions"]:
        last = manifest["partitions"][-1]
        fs = (last.get("fstype") or "").lower()
        devName = last["name"]
        if fs == "ext4":
            print(f"[RESIZE] Pokus o zvětšení poslední partition {devName} (ext4).")
            # vyparsujeme číslo partition z názvu (sdf2, nvme0n1p3 → 2, 3)
            m = re.search(r"(\d+)$", devName)
            if not m:
                print("[RESIZE] Nepodařilo se zjistit číslo partition, resize přeskočen.")
            else:
                partnum = m.group(1)
                devdisk = f"/dev/{disk}"
                th.run(["growpart", devdisk, partnum])
                th.run(["resize2fs", f"/dev/{devName}"])
                print("[RESIZE] Hotovo.")
        else:
            print("[RESIZE] Poslední partition není ext4, resize přeskočen.")

    print("SMART RESTORE dokončen.")


# ============================================================
# Compress / Decompress
# ============================================================

def compress_image(path: Path, fast: bool, maxC: bool) -> None:
    """
    gzip komprese existujícího .img (nebo libovolného souboru).
    Default level = -6 pokud nezadáš ani fast, ani max.
    Vytvoří nový .gz a SHA256 pro .gz.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    if is_gzip(path):
        print("Soubor už je gzip – není co komprimovat.")
        return

    level = "-6"
    if fast:
        level = "-1"
    elif maxC:
        level = "-9"

    out = Path(str(path) + ".gz")
    print(f"Komprese {path} → {out} (gzip {level})")

    dd = ["dd", f"if={str(path)}", "bs=4M"]
    gz = ["gzip", level]
    with out.open("wb") as f:
        p1 = subprocess.Popen(dd, stdout=subprocess.PIPE)
        p2 = subprocess.Popen(gz, stdin=p1.stdout, stdout=f)
        p1.stdout.close()
        p2.communicate()

    write_sha256_sidecar(out)
    print("Komprese hotová.")


def decompress_image(path: Path) -> None:
    """
    Dekomprese .img.gz → .img (gunzip).
    Přegeneruje SHA256 pro rozbalený soubor.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    if not is_gzip(path):
        print("Soubor není .gz – není co dekomprimovat.")
        return

    print(f"Dekomprese {path} → gunzip")
    th.run(["gunzip", str(path)])
    out = Path(str(path).removesuffix(".gz"))
    if out.exists():
        write_sha256_sidecar(out)
        print(f"Dekomprese hotová: {out}")
    else:
        print("Výstupní soubor po gunzip neexistuje.")


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Disk backup/restore utility (raw + smart)")
    p.add_argument("mode", choices=[
        "backup", "restore", "extract",
        "smart-backup", "smart-restore",
        "compress", "decompress",
        "shrinkImage", "shrinkDisk"
    ])

    p.add_argument("--disk", help="název disku (bez /dev, např. sdb)")
    p.add_argument("--file", help="soubor (.img / .img.gz) nebo základ jména")
    p.add_argument("--dir", help="adresář pro smart-backup/smart-restore")

    p.add_argument("--fast", action="store_true", help="rychlý gzip (-1)")
    p.add_argument("--max", action="store_true", help="maximální gzip (-9)")

    p.add_argument("--noautoprefix", action="store_true",
                   help="nevkládat auto prefix YYYY-MM-DD-HHMM_")

    p.add_argument("--resize", action="store_true",
                   help="smart-restore: zvětšit poslední ext4 partition na celý disk")

    p.add_argument("--no-sha", action="store_true",
                   help="při restore nesrovnávat SHA256 (nedoporučeno)")

    p.add_argument("--shrink-size", type=int, default=None,
                   help="shrink: cílová velikost v GiB (min 1 GiB), pokud není zadáno, auto výpočet")

    return p


def main() -> None:
    args = build_parser().parse_args()

    autoprefix = not args.noautoprefix

    if args.mode == "backup":
        disk = args.disk or th.choose_disk()
        backup_disk_raw(
            disk=disk,
            base=args.file,
            fast=args.fast,
            maxC=args.max,
            autoprefix=autoprefix,
        )

    elif args.mode == "restore":
        if not args.file:
            raise ValueError("restore vyžaduje --file")
        disk = args.disk or th.choose_disk()
        restore_disk_raw(Path(args.file), disk, no_sha=args.no_sha)

    elif args.mode == "extract":
        if not args.file:
            raise ValueError("extract vyžaduje --file (.img.gz)")
        extract_gz_to_img(Path(args.file))

    elif args.mode == "smart-backup":
        if not args.dir:
            raise ValueError("smart-backup vyžaduje --dir (adresář pro zálohu)")
        smart_backup(
            disk=args.disk or th.choose_disk(),
            outdir=Path(args.dir),
            fast=args.fast,
            maxC=args.max,
            autoprefix=autoprefix,
        )

    elif args.mode == "smart-restore":
        if not args.dir:
            raise ValueError("smart-restore vyžaduje --dir (adresář se zálohou)")
        smart_restore(
            disk=args.disk or th.choose_disk(),
            inDir=Path(args.dir),
            resize=args.resize,
            no_sha=args.no_sha,
        )

    elif args.mode == "compress":
        file = args.file or th.scan_current_dir_for_imgs(".img")
        if not file:
            raise ValueError("compress vyžaduje --file (.img)")
        compress_image(Path(file), fast=args.fast, maxC=args.max)

    elif args.mode == "decompress":
        file = args.file or th.scan_current_dir_for_imgs(".img.gz")
        if not file:
            raise ValueError("decompress vyžaduje --file (.img.gz)")
        decompress_image(Path(file))
        
    elif args.mode == "shrinkImage":
        file = args.file or th.scan_current_dir_for_imgs(".img")        
        if not file:
            raise ValueError("shrink vyžaduje --file (.img)")
        from libs.shring import shrink_image
        shrink_image(
            file,
            spaceSize=args.shrink_size
        )
    elif args.mode == "shrinkDisk":
        disk = args.disk
        if not disk:
            disk = th.choose_disk()
            disk = f"/dev/{disk}"
            partitions = shr.detect_partitions(disk)
            if partitions:
                # dej výběr přes menu
                header=[
                    "Následující partition byly detekovány na disku:",
                    "Vyber partition pro shrink (mountované partition budou odpojeny):"
                ]
                menuList=[]
                items=[]
                for p in partitions:
                    items.append(p["name"])
                    menuList.append(f"{p['name']} | {p['size']} | {p['fstype']}")
        
                # select index
                idx=th.menu(header,menuList,'Vyber partition pro shrink (mountované partition budou odpojeny):')
                disk=items[idx]
                
        print(f"Vybraný disk pro shrink: {disk}")
        
        from libs.shring import shrink_disk
        shrink_disk(
            disk,
            spaceSize=args.shrink_size
        )

    else:
        raise ValueError(f"Neznámý režim: {args.mode}")


if __name__ == "__main__":
    main()
