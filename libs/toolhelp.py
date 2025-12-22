import os,datetime
import subprocess
import json,re
from typing import List,Optional,Union,Any
import hashlib
from pathlib import Path
import libs.toolhelp as th
from .JBLibs.input import select_item, select, anyKey,cls
from .JBLibs.helper import run
from .JBLibs.c_menu import c_menu_block_items
from libs.JBLibs.format import bytesTx
from libs.JBLibs.fs_utils import lsblkDiskInfo,lsblk_list_disks,partitionInfo



   
def __menuPrinList(options: List[Union[str,tuple[str,Any]]], maxOptLen:int=1,menuLen:int=60)-> None:
    """Pomocná funkce pro tisk menu z listu."""
    for i, opt in enumerate(options):
        if isinstance(opt, str):
            option_str = opt
            choice = str(i + 1)
        elif isinstance(opt, (tuple,list)) and len(opt) == 2:
            option_str = str(opt[0])
            choice = str(opt[1])
        else:
            raise ValueError("options musí být seznam stringů nebo seznam tuple (str, hodnota)")
        
        # pokud je volba None → jedná se o splitter nebo popis
        if choice == 'None' or choice is None:
            # pokud je option ve formátu znak+\n+počet → vytvoříme řádek
            match = re.match(r"^(.+)\n(\d+)([crl]?)$", option_str)
            if match:
                char = str(match.group(1))
                count = int(match.group(2))
                if count==0:
                    count=menuLen
                align = match.group(3)                                        
                if align == 'c':
                    print(char.center(count))
                elif align == 'r':
                    print(char.rjust(count))
                elif align == 'l':
                    print(char)
                else:
                    print(char * count)
            else:
                print(option_str)
            continue
        else:
            spc=" " * (maxOptLen - len(str(choice)))
            print(f" {spc}{choice}    {option_str}")            


def menu(header:list, options: list[str]| list[tuple[str,Any]] | List[List[Union[str,Any]]], prompt: str="Vyber možnost: ")-> int:
    """Zobrazí menu s možnostmi a vrátí index vybrané možnosti.
    Args:
        header (list): Seznam řádků záhlaví (stringů).
        options (list): Seznam - položka může být
            - string (zobrazí se jako možnost s indexem)
            - tuple (str, hodnota) (zobrazí se str, a výběrová hodnota je hodnota která se vrátí)
            - tuple (str, None) Tak se jedná o splitter nebo popis (není volitelná), splitter se dá zapsat takto
                ["--- Nějaký popis ---", None], nebo má podporu názobení znaku kde musí mát formát znaku a počtu
                např. ["-\n10",None] → "----------" má podporu multiznaku např. ["*-\n5",None] → "*-*-*-*-*-"  
                POZOR pokud zadáme délku nula tak se použije výchozí délka menu (výchozí je 60)  
                POKUD je za délkou znak tak se provádí operace s textem před délkou:
                    - 'c' tak se řádek centrovaně zarovná
                    - 'r' tak se řádek zarovná vpravo
                    - 'l' tak se řádek zarovná vlevo
                    - bez zadání se násobí znak
                
        prompt (str): Výzva pro uživatele.
    Returns:
        str | int : Vybraná možnost, poku je možné vrátit číslo tak vrátí int, jinak str.
    """
    
    # check pole, nesmí být kombinace stringů a tuple
    # string převedeme na tuple (str, index) a pokud list tak také na tuple (str, hodnota)
    options_converted = []
    maxOptLen = 0
    for i, opt in enumerate(options):
        if isinstance(opt, str):
            options_converted.append( (opt, str(i + 1) ) )
        elif isinstance(opt, (tuple,list)) and len(opt) == 2:
            options_converted.append( (str(opt[0]), str(opt[1]) ) )
        else:
            raise ValueError("options musí být seznam stringů nebo seznam tuple (str, hodnota)")
        if len(str(opt[0])) > maxOptLen:
            maxOptLen = len(str(opt[1]))
    options = options_converted    
    
    if not isinstance(header, list):
        raise ValueError("header musí být seznam řádků (stringů)")
    
    menuLen=60
    header = [ (str(line),None) for line in header]
    if header:
        header.insert(0, ("=\n" + str(menuLen), None) )
        header.append( ("=\n" + str(menuLen), None) )
    while True:
        cls()
        if header:
            __menuPrinList(header,menuLen=menuLen)        
        
        for i, (option, choice) in enumerate(options):
            # pokud je volba None → jedná se o splitter nebo popis
            if choice == 'None' or choice is None:
                # pokud je option ve formátu znak+\n+počet → vytvoříme řádek
                match = re.match(r"^(.+)\n(\d+)([crl]?)$", option)
                if match:
                    char = str(match.group(1))
                    count = int(match.group(2))
                    if count==0:
                        count=menuLen
                    align = match.group(3)                                        
                    if align == 'c':
                        print(char.center(count))
                    elif align == 'r':
                        print(char.rjust(count))
                    elif align == 'l':
                        print(char)
                    else:
                        print(char * count)
                else:
                    print(option)
                continue
            else:
                spc=" " * (maxOptLen - len(str(choice)))
                print(f" {spc}{choice}    {option}")
                            
        try:
            choice = str(input(prompt))
            for opt, val in options:
                if val == str(choice):
                    try:
                        idx = int(val)
                        return idx
                    except ValueError:
                        return str(val)
                    
        except ValueError:
            pass
        print("Neplatná volba. Zkus to znovu.")
        anyKey()

def scan_current_dir_for_imgs(endsWith:str='.img', fromDir:str=os.getcwd())-> str|None:
    """Prohledá aktuální adresář pro IMG soubory a umožní uživateli vybrat jeden.
    Returns:
        str: Cesta k vybranému IMG souboru.
        None: Pokud uživatel zruší výběr.
    """
    from .JBLibs.input import select_item, select
    from .JBLibs.c_menu import c_menu_block_items
    
    cur = os.path.abspath(fromDir)
    header=[]
    header.append("Výběr IMG souboru z aktuálního adresáře")
    header.append(f"Aktuální adresář: {cur}")
    
    
    
    imgs = [select_item(f,data=f) for f in os.listdir(cur) if f.lower().endswith(endsWith.lower()) and os.path.isfile(os.path.join(cur, f))]
    if not imgs:
        raise FileNotFoundError(f"V aktuálním adresáři {cur} nejsou žádné IMG soubory.")

    x= select(
        f"Nalezené IMG soubory, počet: {len(imgs)}",
        imgs,
        subTitle=c_menu_block_items(header)
    )
    
    
    # itms=[]
    # imgs.append(["=\n0",None])
    # imgs.append(["Zrušit výběr","q"])
    
    # idx = menu(header, imgs, "Vyber IMG: ")
    # if idx == "q":
        # return None
    if x.item is None:
        return None
        
    return os.path.join(cur, x.item.data)


def get_mounted_devices() -> List[str]:
    """Return list of devices used for / and /boot."""
    mounts = subprocess.check_output(["mount"]).decode()
    bad = []

    for line in mounts.splitlines():
        if " on / " in line or " on / " in line:
            bad.append(line.split()[0])
        if " on /boot" in line:
            bad.append(line.split()[0])

    # přepnout např. /dev/sda1 → /dev/sda
    cleaned = set()
    for dev in bad:
        # pokud je to partition, zahoď číslo
        if dev.startswith("/dev/"):
            base = "".join([c for c in dev if not c.isdigit()])
            cleaned.add(base)
    return list(cleaned)


def choose_disk(forMount:bool=True) -> str|None:
    """Bezpečný interaktivní výběr disku — nezobrazí disky s root/boot."""
        
    print("\n=== Detekce bezpečných disků ===")    

    # 1) zjisti disky, partition info nepotřebujeme
    lsblk_raw = subprocess.check_output(
        ["lsblk", "-dnpo", "NAME,SIZE,TYPE"]
    ).decode(errors="ignore")

    # 2) vyber jen TYPE=disk
    disks = []
    for line in lsblk_raw.splitlines():
        name, size, typ = line.split()
        if typ == "disk":
            disks.append((name, size))

    # 3) zjisti disky, které jsou mountnuté jako root/boot
    blocked = get_mounted_devices()

    # 4) filtr
    safe_disks = [(n, s) for (n, s) in disks if n not in blocked]
    
    # vyřadíme disky podle volby forMount
    if forMount:
        # pro mount potřebujeme disky, které NEMAJÍ žádné mountnuté partition
        safe_disks = [
            (n, s) for (n, s) in safe_disks
            if not any(
                part.mountpoints
                for part in lsblk_list_disks(ignoreSysDisks=False).values()
                if part.parent == n
            )
        ]
    else:
        # pro unmount potřebujeme disky, které MAJÍ nějakou mountnutou partition
        safe_disks = [
            (n, s) for (n, s) in safe_disks
            if any(
                part.mountpoints
                for part in lsblk_list_disks(ignoreSysDisks=False).values()
                if part.parent == n
            )
        ]

    headers = [
        "Detekce bezpečných disků",
        f"Vyřazuji systémové disky: {blocked}",
        "Následující disky nejsou používány systémem",
    ]
    if forMount:
        headers.append("a nemají připojené partition")
    else:
        headers.append("a mají připojené partition")
    
    headers=c_menu_block_items(headers)    
    items = [select_item(f"{n}  {s}","", n) for (n, s) in safe_disks]    
    disk = select(
        "Výběr disku",
        items,
        80,
        headers
    )
    if disk.item is None:
        return None
    
    disk=disk.item.data
    
    # normalizace
    disk=th.normalizeDiskPath(disk,True)

    # kontrola, zda je validní
    available = [n.replace("/dev/", "") for (n, _) in safe_disks]

    if disk not in available:
        raise ValueError(f"Disk {disk} není mezi povolenými: {available}")

    return disk

def choose_partition(disk:str|None, forMount:bool=True, fullPath:bool=True, filterDev:Optional[re.Pattern|str]=None) -> str|None:
    """Interaktivní výběr partition z daného disku.
    Args:
        disk (str|None): Disk (např. /dev/sda). Pokud None, budou k vybrání všechny partition z dostupných disků.
        forMount (bool): Pokud True, zobrazí jen nepřipojené partition, jinak jen připojené.
        fullPath (bool): Pokud True, vrátí plnou cestu (/dev/sda1), jinak jen název (sda1).
        filterDev (Optional[re.Pattern|str]): If provided, only return 'devices' (no partitions filter) matching the regex.
            - 'loop\d+' for loop devices
    Returns:
        str: Vybraná partition (např. /dev/sda1).
    """
    if not disk is None:
        disk=th.normalizeDiskPath(disk,True)
    
    ls_parts=lsblk_list_disks(True,not forMount, filterDev)
    
    parts=[]
    for disk_v in ls_parts.values():
        if disk_v.children:
            for child_v in disk_v.children:                
                if child_v.parent == disk:
                    parts.append(child_v)
                elif disk is None:
                    parts.append(child_v)
                 
    if not parts:
        if disk is None:
            raise ValueError("Nejsou žádné vhodné partition pro výběr.")
        else:        
            raise ValueError(f"Na disku {disk} nejsou žádné vhodné partition pro výběr.")

    header=c_menu_block_items([
        f"Výběr partition z disku {disk}" if not disk is None else "Výběr partition ze všech dostupných disků",
        "Následující partition jsou k dispozici:"
    ])
    items = [
        select_item(
            f"{part.name}  {bytesTx(part.size)}  [{part.fstype}]" + (f"  [připojeno: {', '.join(part.mountpoints)}]"
            if part.mountpoints
            else "  [nepřipojeno]"),
            "",
            part.name
        )
        for part in parts
    ]
    x= select(
        "Výběr partition",
        items,
        80,
        header
    )
    if x.item is None:
        return None
    
    # selected_part = parts[idx - 1].name
    selected_part = x.item.data

    selected_part = th.normalizeDiskPath(selected_part, not fullPath)
    return selected_part

def check_output(cmd: List[str]) -> bytes:
    """Vrátí stdout daného příkazu (bytes) nebo vyhodí výjimku."""
    print(f"[CMD] {' '.join(cmd)}")
    return subprocess.check_output(cmd)

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

def is_gzip(path: Path) -> bool:
    """Detekce gzip podle přípony."""
    return path.suffix == ".gz" or path.name.endswith(".img.gz")

def getNewDir(baseDir:str, prefix:str)-> str:
    """Vytvoří nový adresář s inkrementálním číslem v zadaném baseDir s daným prefixem.
    Např. prefix="smart-backup" → smart-backup-001, smart-backup-002, ...
    Args:
        baseDir (str): Základní adresář, kde se bude nový adresář vytvářet.
        prefix (str): Prefix názvu nového adresáře.
    Returns:
        str: Cesta k novému adresáři.
    """
    idx = 1
    # Y-m-d-His
    datetimeStamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    prefix = f"{prefix}-{datetimeStamp}"
    while True:
        dirName = f"{prefix}-{idx:03d}"
        fullPath = os.path.join(baseDir, dirName)
        if not os.path.exists(fullPath):
            try:
                os.makedirs(fullPath)
            except Exception as e:
                raise OSError(f"Nelze vytvořit adresář {fullPath}: {e}")
            return fullPath
        idx += 1
          
def list_loop_partitions(loop,mounted:bool=None)-> dict[str, lsblkDiskInfo]:
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
    return lsblk_list_disks(None,mounted,filterDev="^"+str(loop)+"$")

