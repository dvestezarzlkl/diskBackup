"""
Záloha disku přes layout a partitions, tzn zálohuje se disk podle partition a ne celý disk
tzn pokud bude sikg 64G a partition jen 1G a 12G tak se zálohují jen tyto partition a layout disku o souhrnu 13G
restore pak vytvoří layout disku a na něj nahraje jednotlivé partition
výhoda je v tom že záloha zabere méně místa a je rychlejší
nevýhoda je v tom že restore musí být na stejný nebo větší disk než byl zálohovaný
"""
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from ..libs import toolhelp as th
from ..libs.JBLibs.input import confirm

def verify_sha256_sidecar(path: Path) -> bool:
    """
    Ověří SHA256 souboru pomocí sidecar souboru <soubor>.sha256.
    Vrací True pokud OK, jinak vyvolá výjimku.
    """
    sidecar = Path(str(path) + ".sha256")
    if not sidecar.exists():
        raise RuntimeError(f"SHA256 sidecar neexistuje: {sidecar}")
    print(f"[SHA256] Kontrola {path.name}")
    # sha256sum -c file.sha256
    th.run(["sha256sum", "-c", str(sidecar)])
    return True

def diskImgLikeBackup(disk: str, destDir: str, name: Optional[str] = None) -> str:
    """
    Vytvoří „disk image like“ zálohu:
      - uloží GPT layout (sfdisk -d)
      - uloží RAW obrazy všech partition (dd, bez komprese)
      - vygeneruje SHA256 sidecar pro každou partition
      - vytvoří manifest.json

    Struktura:
        <destDir>/<YYYY-MM-DD-HHMM_name_or_disk>/
          layout.gpt
          manifest.json
          p1_<label_or_part>.part
          p1_...part.sha256
          ...

    Args:
        disk: název disku bez /dev (např. "sdf").
        destDir: cílový adresář, ve kterém se vytvoří subdir pro backup.
        name: volitelné jméno backupu; pokud None, zeptá se uživatele.

    Returns:
        Cesta k vytvořenému backup adresáři (str).
    """
    dev = f"/dev/{disk}"
    base_dest = Path(destDir).resolve()
    base_dest.mkdir(parents=True, exist_ok=True)

    # Ověřit, že disk existuje
    try:
        th.run(["lsblk", "-dn", dev])
    except Exception as e:
        raise RuntimeError(f"Disk {dev} neexistuje nebo není dostupný") from e

    # Ověřit, že je GPT (bod 4 – jen GPT)
    parted_out = th.runRet(["parted", "-s", dev, "print"])
    if "Partition Table: gpt" not in parted_out:
        raise RuntimeError(f"Disk {dev} není GPT (Partition Table: gpt).")

    # Jméno backupu
    if name is None:
        default_name = disk
        entered = input(f"Zadej název backupu (bez timestampu, prázdné = {default_name}): ").strip()
        if not entered:
            entered = default_name
        name = entered

    ts = datetime.now().strftime("%Y-%m-%d-%H%M")
    backup_dir = base_dest / f"{ts}_{name}"
    backup_dir.mkdir(parents=False, exist_ok=False)

    print(f"=== Disk backup (diskImgLikeBackup) {dev} → {backup_dir} ===")

    # 1) Uložit GPT layout
    layout_path = backup_dir / "layout.gpt"
    layout_text = th.runRet(["sfdisk", "-d", dev])
    layout_path.write_text(layout_text, encoding="utf-8")
    print(f"[INFO] Uložen layout: {layout_path}")

    # 2) Najít partition přes lsblk (JSON)
    lsblk_json = th.runRet(["lsblk", "-J", "-b", "-o", "NAME,TYPE,FSTYPE,LABEL,SIZE", dev])
    data = json.loads(lsblk_json)

    parts = []
    for node in data.get("blockdevices", []):
        if node.get("type") == "disk":
            for ch in node.get("children", []):
                if ch.get("type") == "part":
                    parts.append(ch)

    if not parts:
        raise RuntimeError(f"Disk {dev} neobsahuje žádné partition, není co zálohovat.")

    manifest = {
        "type": "imgtool-disk-backup",
        "version": 1,
        "source_disk": disk,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "partitions": []
    }

    # 3) Pro každou partition dd → .part + SHA256
    for part in parts:
        pname = part["name"]          # např. sdf1
        pdev = f"/dev/{pname}"
        size_bytes = int(part.get("size", 0))
        fstype = part.get("fstype") or ""
        label = part.get("label") or ""

        # číslo partition z názvu
        m = re.match(r"^([a-zA-Z]+)(\d+)$", pname)
        if not m:
            raise RuntimeError(f"Neznámý formát názvu partition: {pname}")
        pnum = int(m.group(2))

        # název souboru: p<num>_<label_or_name>.part
        base_part_name = label if label else pname
        img_name = f"p{pnum}_{base_part_name}.part"
        img_path = backup_dir / img_name

        print(f"[PART] {pdev} ({fstype or 'unknown'}, {size_bytes} B) → {img_name}")
        if not confirm(f"Zálohovat partition {pdev} do {img_name}?"):
            print(f"[SKIP] {pdev}")
            continue

        th.run([
            "dd",
            f"if={pdev}",
            f"of={str(img_path)}",
            "bs=4M",
            "status=progress"
        ])

        # SHA256 sidecar
        th.write_sha256_sidecar(img_path)

        manifest["partitions"].append({
            "num": pnum,
            "name": base_part_name,
            "devname": pname,
            "fstype": fstype,
            "size_bytes": size_bytes,
            "filename": img_name
        })

    # 4) Uložit manifest
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[INFO] Uložen manifest: {manifest_path}")

    # 5) Dotaz na kontrolu SHA256 všech IMG po záloze (bod 5)
    if confirm("Provést kontrolu SHA256 všech IMG souborů v backupu?"):
        for p in manifest["partitions"]:
            img_path = backup_dir / p["filename"]
            verify_sha256_sidecar(img_path)
        print("[INFO] SHA256 kontrola všech partition úspěšná.")
    else:
        print("[INFO] SHA256 kontrola přeskočena na žádost uživatele.")

    print(f"[DONE] Disk backup hotov: {backup_dir}")
    return str(backup_dir)

def diskImgLikeRestore(src: str, destDisk: str, verifySha: bool = True) -> None:
    """
    Obnoví disk z adresářové zálohy vytvořené diskImgLikeBackup().

    Postup:
      - ověří strukturu (manifest.json, layout.gpt)
      - volitelně zkontroluje SHA256 všech .img
      - zapíše GPT layout na cílový disk (sfdisk)
      - obnoví jednotlivé partition přes dd
      - volitelně nabídne:
          - e2fsck -f na ext4 partition
          - resize2fs na ext4 partition (rozšíření na velikost partition)

    Args:
        src: cesta k adresáři s backupem.
        destDisk: cílový disk (bez /dev, např. "sdf").
        verifySha: zda nabídnout před restore kontrolu SHA256.
    """
    backup_dir = Path(src).resolve()
    if not backup_dir.is_dir():
        raise RuntimeError(f"Backup adresář neexistuje: {backup_dir}")

    dev = f"/dev/{destDisk}"

    manifest_path = backup_dir / "manifest.json"
    layout_path = backup_dir / "layout.gpt"

    if not manifest_path.exists():
        raise RuntimeError(f"Chybí manifest.json v {backup_dir}")
    if not layout_path.exists():
        raise RuntimeError(f"Chybí layout.gpt v {backup_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if manifest.get("type") != "imgtool-disk-backup":
        raise RuntimeError("manifest.json neodpovídá typu imgtool-disk-backup.")

    parts = manifest.get("partitions", [])
    if not parts:
        raise RuntimeError("V manifestu nejsou žádné partition k obnově.")

    print(f"=== Disk restore (diskImgLikeRestore) {backup_dir} → {dev} ===")
    print(f"Zdrojový disk v manifestu: {manifest.get('source_disk')}")

    if not confirm(f"POZOR: Tímto dojde k přepsání {dev}. Pokračovat?"):
        print("Obnova zrušena uživatelem.")
        return

    # Volitelná SHA256 kontrola všech IMG před zápisem
    if verifySha and confirm("Provést SHA256 kontrolu všech IMG souborů před obnovou?"):
        for p in parts:
            img_path = backup_dir / p["filename"]
            verify_sha256_sidecar(img_path)
        print("[INFO] SHA256 kontrola všech IMG proběhla v pořádku.")
    else:
        print("[INFO] Předběžná SHA256 kontrola přeskočena.")

    # 1) Obnova GPT layoutu
    print(f"[LAYOUT] Obnova GPT layoutu na {dev}")
    layout_text = layout_path.read_text(encoding="utf-8")
    try:
        subprocess.run(
            ["sfdisk", dev],
            input=layout_text.encode("utf-8"),
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"sfdisk selhal při obnově layoutu na {dev}") from e

    # Přinutit kernel znovu načíst partition tabulku
    th.run(["partprobe", dev])

    # 2) Obnova jednotlivých partition
    for p in parts:
        pnum = p["num"]
        fname = p["filename"]
        fstype = p.get("fstype") or ""
        img_path = backup_dir / fname

        # pro /dev/sdX formát stačí /dev/sdX + číslo
        pdev = f"{dev}{pnum}"

        print(f"[RESTORE] {img_path.name} → {pdev}")
        if not confirm(f"Obnovit IMG {img_path.name} na {pdev}?"):
            print(f"[SKIP] {pdev}")
            continue

        th.run([
            "dd",
            f"if={str(img_path)}",
            f"of={pdev}",
            "bs=4M",
            "status=progress"
        ])

        # Po zápisu můžeme volitelně ověřit SHA proti sidecar ještě jednou
        # (ale většinou stačí předběžná kontrola)

    # 3) Nabídnout kontrolu ext4 filesystemů
    ext4_parts = [p for p in parts if (p.get("fstype") or "") == "ext4"]
    if ext4_parts and confirm("Spustit e2fsck -f na ext4 partition po obnově?"):
        for p in ext4_parts:
            pnum = p["num"]
            pdev = f"{dev}{pnum}"
            print(f"[FSCK] e2fsck -f {pdev}")
            # Bez -y, aby ses mohl rozhodnout, co opravit
            th.run(["e2fsck", "-f", pdev])
    else:
        if ext4_parts:
            print("[INFO] Kontrola e2fsck na ext4 partition přeskočena.")

    # 4) Nabídnout rozšíření ext4 filesystemů na velikost partition
    if ext4_parts and confirm("Rozšířit ext4 filesystem(y) na plnou velikost partition (resize2fs)?"):
        for p in ext4_parts:
            pnum = p["num"]
            pdev = f"{dev}{pnum}"
            print(f"[RESIZE] resize2fs {pdev}")
            th.run(["resize2fs", pdev])
    else:
        if ext4_parts:
            print("[INFO] Rozšíření ext4 partition přeskočeno.")

    print("[DONE] Disk obnova dokončena.")

