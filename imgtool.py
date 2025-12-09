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

import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any
import libs.toolhelp as th
import libs.glb as glb
import os
import libs.toolhelp as th
from libs.JBLibs.input import anyKey,cls,confirm
from libs.JBLibs.term import reset


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
    cls()
    
    dev = f"/dev/{disk}"
    base_name = generate_base_name(disk, base, autoprefix)
   
    header = [
        "*** Disk Backup Tool (RAW dd) ***\n0c",
        f"Aktuální adresář: {os.getcwd()}\n0c",
        f"Záloha disku {dev} → {base_name}.img\n0c",
    ]
    
    if not fast and not maxC:
        opts=[
            ["Pokračovat bez komprese (RAW .img)","y"],
            ["Pokračovat s rychlou kompresí (gzip -1)","f"],
            ["Pokračovat s maximální kompresí (gzip -9)","m"],
            ["Zrušit","q"]
        ]
        volba=th.menu(header,opts,"Vyber možnost:")
        if volba=="q":
            print("Zrušeno.")
            return
        elif volba=="f":
            fast=True
        elif volba=="m":
            maxC=True
    else:
        if fast:
            header.append("Rychlá komprese: gzip -1\n0c")
        if maxC:
            header.append("Maximální komprese: gzip -9\n0c")
        
        opts=[
            ["Pokračovat","y"],
            ["Zrušit","q"]
        ]
        volba=th.menu(header,opts,"Potvrď zálohu disku:")
        if volba=="q":
            print("Zrušeno.")
            return

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
        th.run(["dd", f"if={dev}", f"of={str(out)}", "bs=4M", "status=progress"])

    th.write_sha256_sidecar(out)
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
        ok = th.verify_sha256_sidecar(filename)
        if not ok:
            if not confirm("Hash nesedí nebo sidecar chybí. Pokračovat i tak?"):
                print("Zrušeno.")
                return

    if not confirm("!!! Tohle přepíše celý disk. Pokračovat?"):
        print("Zrušeno.")
        return

    if th.is_gzip(filename):
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
    if not th.is_gzip(filename):
        print("Soubor není .gz – není co extrahovat.")
        return

    print(f"Extract {filename} → gunzip")
    th.run(["gunzip", str(filename)])
    out = Path(str(filename).removesuffix(".gz"))
    if out.exists():
        th.write_sha256_sidecar(out)
        print(f"Extract hotov: {out}")
    else:
        print("Extract se nepovedl – výstupní soubor neexistuje.")


# ============================================================
# Smart backup / restore (layout + partitions)
# ============================================================

def detect_fs(devPath: str) -> str | None:
    """Zjistí typ FS buď z blkid, nebo vrátí None."""
    try:
        fs = th.check_output(["blkid", "-o", "value", "-s", "TYPE", devPath]).decode().strip()
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
        data = th.check_output(["sfdisk", "-d", dev])
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
    size_bytes = int(th.check_output(["blockdev", "--getsize64", devPath]).decode().strip())
    human = th.human_size(size_bytes)

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

    th.write_sha256_sidecar(out)

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
    info = json.loads(th.check_output(["lsblk", "-b", "-J", f"/dev/{disk}"]))
    devInfo = info["blockdevices"][0]
    parts = devInfo.get("children", [])

    manifest: Dict[str, Any] = {
        "disk": disk,
        "created": ts,
        "size_bytes": int(devInfo.get("size", 0)),
        "size_human": th.human_size(int(devInfo.get("size", 0))),
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
        ok = th.verify_sha256_sidecar(image_path)
        if not ok and not confirm("Hash nesedí nebo chybí – pokračovat i tak?"):
            print("Zrušeno.")
            return

    if th.is_gzip(image_path):
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
    if th.is_gzip(path):
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

    th.write_sha256_sidecar(out)
    print("Komprese hotová.")


def decompress_image(path: Path) -> None:
    """
    Dekomprese .img.gz → .img (gunzip).
    Přegeneruje SHA256 pro rozbalený soubor.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    if not th.is_gzip(path):
        print("Soubor není .gz – není co dekomprimovat.")
        return

    print(f"Dekomprese {path} → gunzip")
    th.run(["gunzip", str(path)])
    out = Path(str(path).removesuffix(".gz"))
    if out.exists():
        th.write_sha256_sidecar(out)
        print(f"Dekomprese hotová: {out}")
    else:
        print("Výstupní soubor po gunzip neexistuje.")


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Disk backup/restore utility (raw + smart)")
    p.add_argument(
        "mode",
        nargs="?",
        choices=[
            "backup", "restore", "extract",
            "smart-backup", "smart-restore",
            "compress", "decompress","swap",
            "bkpart", "rspart",
        ],
        default=None,
        help="Režim práce s disky/obrazy"
    )

    p.add_argument("--disk", help="název disku (bez /dev, např. sdb)")
    p.add_argument("--file", help="soubor (.img / .img.gz) nebo základ jména")
    p.add_argument("--dir", help="adresář pro smart-backup/smart-restore",default=None)

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
    
    p.add_argument("--target-size", type=int, default=None,
                   help="swap: cílová velikost v MB nebo GB (př.zadání: 512M, 2G)")

    return p

def __showMenu() -> None:
    from libs.JBLibs.input import select_item,select
    from libs.JBLibs.c_menu import c_menu_block_items,c_menu_title_label
    
    header=c_menu_block_items()
    header.append( ("Disk Backup Tool","c") )
    header.append( "-")
    header.append( ("Verze", f"{glb.VERSION}"))
    header.append( ("Aktuální cesta", f"{os.getcwd()}"))
    
    sel_opts=[
        c_menu_title_label("Režimy práce s disky/obrazy:"),
        None,
        select_item("Backup whole disk (raw dd) one img",   "bw",   "backup"),
        select_item("Restore whole disk (raw dd) one img",  "rw",   "restore"),
        None,
        select_item("Backup parts disk (raw dd) layout + one part one img", "bpd", "bkpart"),
        select_item("Restore parts disk (raw dd) layout + one part one img", "rpd", "rspart"),
        None,
        select_item("Smart Backup (layout + partitions)", "sb", "smart-backup"),
        select_item("Smart Restore (layout + partitions)", "sr", "smart-restore"),
        None,
        select_item("Extract .img.gz → .img", "e", "extract"),
        select_item("Compress .img → .img.gz", "c", "compress"),
        select_item("Decompress .img.gz → .img", "d", "decompress"),
        None,
        select_item("Změna velikosti swap file", "w", "swap"),
        None,
        select_item("Disk tool", "t","t"),
    ]
    x= select(None,sel_opts,80,header)
    return x.item.data
    

def main() -> None:
    args = build_parser().parse_args()
    autoprefix = not args.noautoprefix
    
    mode=args.mode
    repeat = mode is None
    
    while repeat:
        if not mode:
            cls()
            mode=__showMenu()
            if not mode:
                return

        if mode == "backup":
            disk = args.disk or th.choose_disk()
            backup_disk_raw(
                disk=disk,
                base=args.file,
                fast=args.fast,
                maxC=args.max,
                autoprefix=autoprefix,
            )
            mode=None

        elif mode == "restore":
            if not args.file:
                raise ValueError("restore vyžaduje --file")
            disk = args.disk or th.choose_disk()
            restore_disk_raw(Path(args.file), disk, no_sha=args.no_sha)
            mode=None

        elif mode == "extract":
            if not args.file:
                raise ValueError("extract vyžaduje --file (.img.gz)")
            extract_gz_to_img(Path(args.file))
            mode=None

        elif mode == "smart-backup":
            dir=args.dir
            if dir==None:
                dir=os.getcwd()
                
            if not os.path.isdir(dir):
                raise ValueError("smart-backup vyžaduje exitující cestu nebo zadaný parametr --dir")
            
            dir=th.getNewDir(dir,"smart-backup")
            
            if not os.path.isdir(dir):
                raise ValueError("smart-backup vyžaduje --dir (adresář pro zálohu)")
            
            # opravu zálohovat do zadaného adresáře
            cls()
            print(f"Smart backup bude uložen do adresáře: {dir}")
            if not confirm(f"Zálohovat do adresáře: {dir}?"):
                print("Zrušeno.")
                return
            
            smart_backup(
                disk=args.disk or th.choose_disk(),
                outdir=Path(dir),
                fast=args.fast,
                maxC=args.max,
                autoprefix=autoprefix,
            )
            mode=None

        elif mode == "smart-restore":
            if not args.dir:
                raise ValueError("smart-restore vyžaduje --dir (adresář se zálohou)")
            smart_restore(
                disk=args.disk or th.choose_disk(),
                inDir=Path(args.dir),
                resize=args.resize,
                no_sha=args.no_sha,
            )
            mode=None

        elif mode == "compress":
            file = args.file or th.scan_current_dir_for_imgs(".img")
            if not file:
                raise ValueError("compress vyžaduje --file (.img)")
            compress_image(Path(file), fast=args.fast, maxC=args.max)
            mode=None

        elif mode == "decompress":
            file = args.file or th.scan_current_dir_for_imgs(".img.gz")
            if not file:
                raise ValueError("decompress vyžaduje --file (.img.gz)")
            decompress_image(Path(file))
            mode=None
            
        elif mode== "t":
            app="jbtool"
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
            return
            
        elif mode=="swap":
            file = args.file or None
            cls()
            targetSize = args.target_size
            from libs import swap
            swap.resizeSwap(file, targetSize)
            mode=None
            anyKey()

        else:
            raise ValueError(f"Neznámý režim: {args.mode}")

if __name__ == "__main__":
    reset()
    main()
