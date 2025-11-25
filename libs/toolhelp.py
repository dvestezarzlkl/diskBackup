import os,datetime
import subprocess
import json,re
from typing import List,Optional,Union,Any
import hashlib
from pathlib import Path
import libs.shring as shr
import libs.toolhelp as th

class lsblkError(Exception):
    """Custom exception for lsblk errors."""
    pass

class lsblkDiskInfo:
    """popis disku z lsblk"""
    def __init__(
        self,
        name:str,
        label:str,
        size:int,
        fstype:str,
        type:str,
        uuid:str,
        partuuid:str,        
        mountpoints:Union[List[str],str],
        parent:Optional[str]=None,
        children:Optional[List['lsblkDiskInfo']]=None
    ):
        self.name = name
        self.label = label
        self.size = size
        self.fstype = fstype
        self.uuid = uuid
        self.partuuid = partuuid
        self.mountpoints = mountpoints
        self.parent = parent
        self.type = type
        
        mp = mountpoints or []
        if isinstance(mp, str):
            mp = [mp]
        self.mountpoints = mp        
                    
        self.children = children if children is not None else []
        
    def __repr__(self):
        sz=human_size(self.size)
        mountPoints=len(self.mountpoints)
        childs=len(self.children)
        childsLst=[child.name for child in self.children]
        return f"lsblkDiskInfo(tp:{self.type}, nm={self.name}, sz={sz}, fstp={self.fstype}, uuid={self.uuid}, partuuid={self.partuuid}, mountpoints={mountPoints}, children={childs} {childsLst})"

class partitionInfo():
    """Popis partition."""
    def __init__(
        self,
        partition:str,
    ):
        if not isinstance(partition, str):
            raise ValueError("partition musí být string")
        partition=partition.strip()
        if not partition or len(partition)<2:
            raise ValueError("partition nesmí být prázdný string a musí mít alespoň 2 znaky")
        
        self.partitionName:str = normalizeDiskPath(partition, True)
        """Název partition neobsahuje prefix /dev/"""
        
        self.partitionPath:str = normalizeDiskPath(partition)
        """Plná cesta k partition (např. /dev/sda1)"""
        
        self.diskInfo:lsblkDiskInfo|None = getDiskByPartition(self.partitionPath)
        """Info o disku, na kterém je partition."""
        
        self.diskName:str|None = normalizeDiskPath(self.diskInfo.name,True)
        """Název disku (např. sda)"""
        
        self.diskPath:str|None = normalizeDiskPath(self.diskInfo.name)
        """Plná cesta k disku (např. /dev/sda)"""
        
        self.partitionInfo:lsblkDiskInfo|None = None
        """Info o partition."""
        
        self.partitionIndex:int|None = None
        """Index partition na disku (1,2,3...)"""
        
        self.isLastPartition:bool = False
        """Je to poslední partition na disku?"""
        
        self.isPartitionExt4:bool = False
        """Je to ext4 partition?"""
        
        if self.diskInfo and self.diskInfo.children:
            for idx, part in enumerate(self.diskInfo.children):
                if part.name == self.partitionName or th.normalizeDiskPath(part.name, False) == self.partitionName:
                    self.partitionInfo = part
                    self.partitionIndex = idx + 1
                    self.isLastPartition = (idx == len(self.diskInfo.children) - 1)
                    self.isPartitionExt4 = (part.fstype == 'ext4')
                    break

def human_size(num_bytes: int) -> str:
    """Převod velikosti v bajtech na čitelný string (MiB/GiB).
    Args:
        num_bytes (int): Velikost v bajtech.
    Returns:
        str: Čitelný formát velikosti.
    """
    step = 1024.0
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(num_bytes)
    idx = 0
    while size >= step and idx < len(units) - 1:
        size /= step
        idx += 1
    return f"{size:.1f} {units[idx]}"

def sha256_file(path: Path) -> str:
    """Vypočítá SHA256 pro daný soubor."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            if not block:
                break
            h.update(block)
    return h.hexdigest()

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

def cls()-> None:
    """Vyčistí obrazovku."""
    os.system('cls' if os.name=='nt' else 'clear')
    
def anyKey()-> None:
    """Čeká na stisk libovolné klávesy."""
    input("Stiskni Enter pro pokračování...")

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
    
    cur = os.path.abspath(fromDir)
    header=[]
    header.append("Výběr IMG souboru z aktuálního adresáře\n0c")
    header.append(f"Aktuální adresář: {cur}")
    
    imgs = [f for f in os.listdir(cur) if f.lower().endswith(endsWith.lower()) and os.path.isfile(os.path.join(cur, f))]
    if not imgs:
        raise FileNotFoundError(f"V aktuálním adresáři {cur} nejsou žádné IMG soubory.")

    header.append(f"Nalezené IMG soubory, počet: {len(imgs)}\n0c")
    
    imgs.append(["=\n0",None])
    imgs.append(["Zrušit výběr","q"])
    
    idx = menu(header, imgs, "Vyber IMG: ")
    if idx == "q":
        return None
        
    selected_img = imgs[idx - 1]
    return os.path.join(cur, selected_img)


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

def __lsblk_process_node(
    node:dict,
    parent:Optional[lsblkDiskInfo]=None,
    ignoreSysDisks:bool=True,
    mounted:Optional[bool]=None,
    filterDev:Optional[re.Pattern]=None
) -> Optional[lsblkDiskInfo]:
    """Process a single lsblk node and return lsblkDiskInfo or None.
    Args:
        node (dict): LSBLK node dictionary.
        parent (Optional[lsblkDiskInfo]): Parent disk info.
        ignoreSysDisks (bool): If True, ignore system disks used for / and /boot.        
        mounted (Optional[bool]): If  
            True: only return if mounted
            False: only return if not mounted
            None: return regardless of mount status
        filterDev (Optional[re.Pattern]): If provided, only return 'devices' (no partitions filter) matching the regex.
            - 'loop\d+' for loop devices
            - 'sd[a-z]+' for standard disks
            - 'loop0' for specific device
    Returns:
        Optional[lsblkDiskInfo]: Processed lsblkDiskInfo object or None.
        
    """
    
    if node['type'] in ['disk','part','loop']:
        nfo = lsblkDiskInfo(
            type=node.get('type',''),
            name=node.get('name', ''),
            label=node.get('label', ''),
            size=int(node.get('size', 0)),
            fstype=node.get('fstype', ''),
            uuid=node.get('uuid', ''),
            partuuid=node.get('partuuid', ''),
            mountpoints=node.get('mountpoints', []),
            parent=parent.name if parent else None,
            children=[]
        )
        if ignoreSysDisks and ('/' in nfo.mountpoints or '/boot' in nfo.mountpoints):
            return None
        
        nfo.mountpoints = [mp for mp in nfo.mountpoints if mp]  # remove empty mountpoints
            
        is_mounted = len(nfo.mountpoints) > 0
        # pokud je to distk tak vracíme vždy, mounted je jen pro partition
        # if node['type'] != 'disk':
        if not node['type'] in ['disk','loop']:
            if mounted is True and not is_mounted:
                return None
            if mounted is False and is_mounted:
                return None
        else:
            # pokud je to disk a je nastaven filterDev tak aplikujeme filtr
            if isinstance(filterDev, re.Pattern):
                nm=normalizeDiskPath(nfo.name,True)
                if not filterDev.fullmatch(nm):
                    return None
        return nfo
    return None
        

def __lsblk_recursive(
    nodes:List[dict],
    parent:Optional[lsblkDiskInfo]=None,
    ignoreSysDisks:bool=True,
    mounted:Optional[bool]=None,
    filterDev:Optional[re.Pattern]=None
) -> List[lsblkDiskInfo]:
    """Recursively process lsblk nodes and return list of lsblkDiskInfo.
    Args:
        nodes (List[dict]): List of LSBLK node dictionaries.
        parent (Optional[lsblkDiskInfo]): Parent disk info.
        ignoreSysDisks (bool): If True, ignore system disks used for / and /boot.        
        mounted (Optional[bool]): If  
            True: only return if mounted
            False: only return if not mounted
            None: return regardless of mount status
        filterDev (Optional[re.Pattern]): If provided, only return 'devices' (no partitions filter) matching the regex.
            - 'loop\d+' for loop devices
            - 'sd[a-z]+' for standard disks
            - 'loop0' for specific device
    Returns:
        List[lsblkDiskInfo]: List of processed lsblkDiskInfo objects.
    """
    result = []
    for node in nodes:
        info = __lsblk_process_node(node, parent, ignoreSysDisks, mounted, filterDev)
        if info:
            children = node.get('children', [])
            info.children = __lsblk_recursive(children, info, ignoreSysDisks, mounted, filterDev)
            
            # check mount status
            is_mounted = len(info.mountpoints) > 0
            for x in info.children:
                if len(x.mountpoints) > 0:
                    is_mounted = True
                    break
            
            if not mounted is None:
                if mounted is True and not is_mounted:
                    continue
                if mounted is False and is_mounted:
                    continue
                
            # ignore system disks if needed
            is_sys='/' in info.mountpoints or '/boot' in info.mountpoints
            for x in info.children:
                if '/' in x.mountpoints or '/boot' in x.mountpoints:
                    is_sys = True
                    break
            if ignoreSysDisks and is_sys:
                continue

            # process children
            result.append(info)
    return result

def lsblk_list_disks(
        ignoreSysDisks:bool=True,
        mounted:Optional[bool]=None,
        filterDev:Optional[re.Pattern|str]=None
    ) -> dict[str,lsblkDiskInfo]:
    """Return list of disks with basic info using lsblk. Returns dir of lsblkDiskInfo, key is disk name.
    Args:
        ignoreSysDisks (bool): If True, ignore disks used for / and /boot.
        mounted (Optional[bool]): If  
            True: only return mounted disks
            False: only return unmounted disks
            None: return all disks
        filterDev (Optional[re.Pattern|str]): If provided, only return 'devices' (no partitions filter) matching the regex.
            - 'loop\d+' for loop devices
            - 'sd[a-z]+' for standard disks
            - 'loop0' for specific device
    Returns:
        dict[str,lsblkDiskInfo]: Dictionary of lsblkDiskInfo objects, key is disk name.
    """
    # lsblk -no NAME,LABEL,SIZE,FSTYPE,UUID,PARTUUID,MOUNTPOINTS --json
    out = subprocess.run(
        ["lsblk", "-J","-b", "-o", "NAME,LABEL,SIZE,TYPE,FSTYPE,UUID,PARTUUID,MOUNTPOINTS"],
        capture_output=True, text=True
    )
    data = json.loads(out.stdout)
    if filterDev and isinstance(filterDev, str):
        filterDev = re.compile(filterDev)
    disks = __lsblk_recursive(data.get('blockdevices', []), None, ignoreSysDisks, mounted, filterDev)
    disk_dict = {disk.name: disk for disk in disks if disk.fstype != 'swap'}
    return disk_dict

def getDiskByPartition(partition:str) -> Optional[lsblkDiskInfo]:
    """Vrátí disk, na kterém se nachází daná partition.
    Args:
        partition (str): Partition (např. /dev/sda1) nebo název (sda1).
    Returns:
        Optional[lsblkDiskInfo]: Disk info nebo None pokud nenalezen.
    """
    partition = th.normalizeDiskPath(partition, False)
    ls_parts = lsblk_list_disks(ignoreSysDisks=False)
    for disk in ls_parts.values():
        if disk.children:
            for child in disk.children:
                if child.name == partition or th.normalizeDiskPath(child.name, False) == partition:
                    return disk
    return None

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
    items = [f"{n}  {s}" for (n, s) in safe_disks]
    
    items.append(["=\n0",None])
    items.append(["Zrušit výběr","q"])
    
    idx=menu(headers, items, prompt="Vyber disk: ")
    disk = safe_disks[idx-1][0]
    if disk == "q":
        return None

    # normalizace
    disk=th.normalizeDiskPath(disk,True)

    # kontrola, zda je validní
    available = [n.replace("/dev/", "") for (n, _) in safe_disks]

    if disk not in available:
        raise ValueError(f"Disk {disk} není mezi povolenými: {available}")

    return disk

def choose_partition(disk:str|None, forMount:bool=True, fullPath:bool=True) -> str|None:
    """Interaktivní výběr partition z daného disku.
    Args:
        disk (str|None): Disk (např. /dev/sda). Pokud None, budou k vybrání všechny partition z dostupných disků.
        forMount (bool): Pokud True, zobrazí jen nepřipojené partition, jinak jen připojené.
        fullPath (bool): Pokud True, vrátí plnou cestu (/dev/sda1), jinak jen název (sda1).
    Returns:
        str: Vybraná partition (např. /dev/sda1).
    """
    if not disk is None:
        disk=th.normalizeDiskPath(disk,True)
    
    ls_parts=lsblk_list_disks(True,not forMount)
    
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

    headers = [
        f"Výběr partition z disku {disk}" if not disk is None else "Výběr partition ze všech dostupných disků",
        "Následující partition jsou k dispozici:"
    ]
    
    items = [
        f"{part.name}  {human_size(part.size)}  [{part.fstype}]" + (f"  [připojeno: {', '.join(part.mountpoints)}]"
        if part.mountpoints
        else "  [nepřipojeno]")
        for part in parts
    ]

    items.append(["=\n0",None])
    items.append(["Zrušit výběr","q"])

    idx = menu(headers, items, prompt="Vyber partition: ")
    if idx == "q":
        return None
    
    selected_part = parts[idx - 1].name

    selected_part = th.normalizeDiskPath(selected_part, not fullPath)
    return selected_part
    

def run(cmd: List[str]|str, *, input_bytes: bytes | None = None) -> None:
    """Spustí příkaz, logne ho a při chybě vyhodí výjimku."""
    if isinstance(cmd, str):
        cmd = cmd.split()
    print(f"[RUN] {' '.join(cmd)}")
    subprocess.run(cmd, check=True, input=input_bytes)


def runRet(cmd: str) -> str:
    """Run shell command and return output, raise on error."""
    proc = subprocess.run(
        cmd, shell=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if proc.returncode != 0:
        raise shr.ShrinkError(f"Command failed: {cmd}\n{proc.stdout}")
    return proc.stdout

def check_output(cmd: List[str]) -> bytes:
    """Vrátí stdout daného příkazu (bytes) nebo vyhodí výjimku."""
    print(f"[CMD] {' '.join(cmd)}")
    return subprocess.check_output(cmd)

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


def confirm(msg: str) -> bool:
    """Vrátí True pokud uživatel odpověděl 'y' nebo 'Y'."""
    return input(msg + " [y/N]: ").lower() == "y"


def is_gzip(path: Path) -> bool:
    """Detekce gzip podle přípony."""
    return path.suffix == ".gz" or path.name.endswith(".img.gz")

def normalizeDiskPath(disk: str, noDevPath:bool=False) -> str:
    """Normalizuje diskovou cestu na /dev/sdX formát.
    Args:
        disk (str): Cesta k disku (např. sda, /dev/sda).
        noDevPath (bool): Pokud:
            - True, vrátí cestu 'sda' bez /dev/ prefixu.
            - False, vrátí cestu '/dev/sda' s /dev/ prefixem.
    Returns:
        str: Normalizovaná cesta k disku.        
    """
    if not disk.startswith("/dev/"):
        disk = "/dev/" + disk
        
    if noDevPath:
        disk = disk.replace("/dev/","")
        
    return disk    

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
        
def checkExt4(partition:str) -> None:
    """Zkontroluje ext4 partition.
    Akceptuje název partition bez /dev/ (sdb2, mmcblk0p1, atd.).
    Args:
        partition (str): název partition s nebo bez /dev/
    Raises:
        ValueError: pokud partition neexistuje nebo není ext4 nebo dojde k chybě při kontrole.
    """
    
    part = partitionInfo(partition)
    if part is None or part.partitionInfo is None:
        raise ValueError(f"Nepodařilo se zjistit informace o partition: {partition}")
    
    if not part.isPartitionExt4:
        raise ValueError(f"Partition {partition} není ext4.")
    
    try:
        run(["sudo", "e2fsck", "-f", part.partitionPath])
    except Exception as e:
        raise ValueError(f"Chyba při kontrole ext4 partition {partition}: {e}")