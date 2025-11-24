#!/usr/bin/env python3
import subprocess
import json
import re

"""Nástroj pro zobrazení informací o discích dostupných v systému ale bez nutnosti jejich připojení
Tzn zamýšleno pro diky kterou jou vidět ale nejsou mountnuté.

Args:
    None
Returns:
    None

Author: Jan Zednik
Licence: MIT
"""

def run(cmd):
    """Run external command and return stdout (decoded)."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout.strip()

def list_disks():
    out = run(["lsblk", "-J", "-o", "NAME,SIZE,MODEL,TYPE"])
    data = json.loads(out)

    disks = []
    for blk in data["blockdevices"]:
        if blk["type"] == "disk":
            disks.append(blk)
    return disks

def list_partitions(disk):
    out = run(["lsblk", "-J", f"/dev/{disk}", "-o", "NAME,SIZE,FSTYPE,TYPE"])
    data = json.loads(out)

    parts = []
    for blk in data["blockdevices"]:
        if "children" in blk:
            for ch in blk["children"]:
                if ch["type"] == "part":
                    parts.append(ch)
    return parts

def get_ext4_info(dev):
    """Return dict with size, used, free for ext4 without mounting."""
    out = run(["dumpe2fs", "-h", dev])
    info = {}

    def get(pattern):
        m = re.search(pattern, out)
        if m:
            return int(m.group(1))
        return None

    block_count = get(r"Block count:\s+(\d+)")
    free_blocks = get(r"Free blocks:\s+(\d+)")
    block_size = get(r"Block size:\s+(\d+)")

    if block_count and free_blocks and block_size:
        total = block_count * block_size
        free = free_blocks * block_size
        used = total - free
        info["total"] = total
        info["used"] = used
        info["free"] = free

    return info

def get_xfs_info(dev):
    """Return size only; XFS cannot accurately report used without mount."""
    try:
        sb = run(["xfs_db", "-r", dev, "-c", "sb 0", "-c", "p dblocks"])
        m = re.search(r"dblocks = (\d+)", sb)
        if not m:
            return {}

        dblocks = int(m.group(1))

        info = run(["xfs_info", dev])
        m2 = re.search(r"sectsz=(\d+)", info)
        blocksize = int(m2.group(1)) if m2 else 4096

        total = dblocks * blocksize

        return {
            "total": total,
            "used": None,
            "free": None
        }
    except Exception:
        return {}

def fmt(bytes_val):
    if bytes_val is None:
        return "unknown"
    return subprocess.run(["numfmt", "--to=iec"], input=str(bytes_val), text=True, capture_output=True).stdout.strip()

def main():
    # === 1) Vypiš dostupné disky ===
    print("=== Available disks ===")
    disks = list_disks()
    if not disks:
        print("No disks found.")
        return

    for i, d in enumerate(disks):
        print(f"{i}) {d['name']:>6}   {d['size']:>8}   {d.get('model','')}")

    # === 2) Výběr disku ===
    choice = input("Select disk index: ").strip()
    if not choice.isdigit() or int(choice) not in range(len(disks)):
        print("Invalid selection.")
        return

    disk = disks[int(choice)]["name"]
    print(f"\nSelected disk: /dev/{disk}")

    # === 3) Oddíly ===
    parts = list_partitions(disk)
    if not parts:
        print("Disk has no partitions.")
        return

    print("\n--- Partitions ---")
    for p in parts:
        print(f"  /dev/{p['name']}  {p['size']}  {p.get('fstype','?')}")

    # === 4) Detailní informace ===
    print("\n=== Partition details ===")

    for p in parts:
        dev = "/dev/" + p["name"]
        fstype = p.get("fstype")

        print(f"\n>>> {dev} ({fstype})")

        if fstype == "ext4":
            info = get_ext4_info(dev)
            print(f"  Size: {fmt(info.get('total'))}")
            print(f"  Used: {fmt(info.get('used'))}")
            print(f"  Free: {fmt(info.get('free'))}")

        elif fstype == "xfs":
            info = get_xfs_info(dev)
            print(f"  Size: {fmt(info.get('total'))}")
            print(f"  Used: cannot detect without mount")
            print(f"  Free: cannot detect without mount")

        else:
            print("  Unsupported FS (need mount for details).")

if __name__ == "__main__":
    main()
