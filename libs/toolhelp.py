import os
import subprocess
import json,re
from typing import List,Optional,Union,Any

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
        
        mp = mountpoints or []
        if isinstance(mp, str):
            mp = [mp]
        self.mountpoints = mp        
                    
        self.children = children if children is not None else []

class ShrinkError(Exception):
    """Custom exception for shrink operations."""
    pass

def cls()-> None:
    """Vyčistí obrazovku."""
    os.system('cls' if os.name=='nt' else 'clear')
    
def anyKey()-> None:
    """Čeká na stisk libovolné klávesy."""
    input("Stiskni Enter pro pokračování...")

def menu(header:list, options: list[str]| list[tuple[str,Any]] | List[List[Union[str,Any]]], prompt: str="Vyber možnost: ")-> int:
    """Zobrazí menu s možnostmi a vrátí index vybrané možnosti.
    Args:
        header (list): Seznam řádků záhlaví (stringů).
        options (list): Seznam možností (stringů), pak vrací index, nebo seznam tuple (str, hodnota), pak vrací hodnotu.
        prompt (str): Výzva pro uživatele.
    Returns:
        int: Index vybrané možnosti, nebo hodnota None při neplatném výběru.
            anebo hodnota pokud je options seznam tuple (str, hodnota).
    """
    
    # check pole, nesmí být kombinace stringů a tuple
    # string převedeme na tuple (str, index) a pokud list tak také na tuple (str, hodnota)
    options_converted = []
    for i, opt in enumerate(options):
        if isinstance(opt, str):
            options_converted.append( (opt, i + 1) )
        elif isinstance(opt, (tuple,list)) and len(opt) == 2:
            options_converted.append( (str(opt[0]), opt[1]) )
        else:
            raise ValueError("options musí být seznam stringů nebo seznam tuple (str, hodnota)")
    options = options_converted    
    
    while True:
        cls()        
        if not isinstance(header, list):
            header = [header]
        
        print("\n".join(header))
        print("-" * max(len(line) for line in header))
        
        for i, (option, _) in enumerate(options):
            print(f" {option[0]} = {option[1]}")
                            
        try:
            choice = int(input(prompt))
            for opt, val in options:
                if opt[0] == str(choice):
                    return val                
        except ValueError:
            pass
        print("Neplatná volba. Zkus to znovu.")
        anyKey()

def scan_current_dir_for_imgs(endsWith:str='.img')-> str:
    """Prohledá aktuální adresář pro IMG soubory a umožní uživateli vybrat jeden.
    Returns:
        str: Cesta k vybranému IMG souboru.
    """
    
    idx=None
    while idx is None:
        cls()
        cur = os.getcwd()
        header=[]
        header.append("Výběr IMG souboru z aktuálního adresáře")
        header.append("Aktuální adresář: {cur}")
        
        imgs = [f for f in os.listdir(cur) if f.lower().endswith(endsWith.lower()) and os.path.isfile(f)]

        if not imgs:
            print("\n".join(header))
            print("V aktuálním adresáři nejsou žádné IMG soubory.")
            return None

        header.append("Nalezené IMG soubory:")
        opts=[]
        for i, f in enumerate(imgs):
            opts.append(f"{i+1}) {f}")

        idx = menu(header, opts, "Vyber IMG: ")
        
    return os.path.join(cur, imgs[idx])


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

def __lsblk_process_node(node:dict, parent:Optional[lsblkDiskInfo]=None, ignoreSysDisks:bool=True, mounted:Optional[bool]=None) -> Optional[lsblkDiskInfo]:
    """Process a single lsblk node and return lsblkDiskInfo or None.
    Args:
        node (dict): LSBLK node dictionary.
        parent (Optional[lsblkDiskInfo]): Parent disk info.
        ignoreSysDisks (bool): If True, ignore system disks used for / and /boot.        
        mounted (Optional[bool]): If  
            True: only return if mounted
            False: only return if not mounted
            None: return regardless of mount status
    """
    
    if node['type'] in ['disk','part','loop']:
        nfo = lsblkDiskInfo(
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
        if mounted is True and not is_mounted:
            return None
        if mounted is False and is_mounted:
            return None
        
        return nfo
    return None
        

def __lsblk_recursive(nodes:List[dict], parent:Optional[lsblkDiskInfo]=None, ignoreSysDisks:bool=True, mounted:Optional[bool]=None) -> List[lsblkDiskInfo]:
    """Recursively process lsblk nodes and return list of lsblkDiskInfo.
    Args:
        nodes (List[dict]): List of LSBLK node dictionaries.
        parent (Optional[lsblkDiskInfo]): Parent disk info.
        ignoreSysDisks (bool): If True, ignore system disks used for / and /boot.        
        mounted (Optional[bool]): If  
            True: only return if mounted
            False: only return if not mounted
            None: return regardless of mount status
    Returns:
        List[lsblkDiskInfo]: List of processed lsblkDiskInfo objects.
    """
    result = []
    for node in nodes:
        info = __lsblk_process_node(node, parent, ignoreSysDisks, mounted)
        if info:
            # check mount status
            is_mounted = len(info.mountpoints) > 0
            if mounted is True and not is_mounted:
                continue
            if mounted is False and is_mounted:
                continue

            # ignore system disks if needed
            if ignoreSysDisks:
                sys_disks = get_mounted_devices()
                if info.name in sys_disks or (info.parent and info.parent in sys_disks):
                    continue

            # process children
            children = node.get('children', [])
            info.children = __lsblk_recursive(children, info, ignoreSysDisks, mounted)
            result.append(info)
    return result

def lsblk_list_disks(ignoreSysDisks:bool=True,mounted:Optional[bool]=None) -> dict:
    """Return list of disks with basic info using lsblk. Returns dir of lsblkDiskInfo, key is disk name.
    Args:
        ignoreSysDisks (bool): If True, ignore disks used for / and /boot.
    Returns:
        dict: Dictionary of lsblkDiskInfo objects, key is disk name.
    """
    # lsblk -no NAME,LABEL,SIZE,FSTYPE,UUID,PARTUUID,MOUNTPOINTS --json
    out = subprocess.run(
        ["lsblk", "-J","-b", "-o", "NAME,LABEL,SIZE,TYPE,FSTYPE,UUID,PARTUUID,MOUNTPOINTS"],
        capture_output=True, text=True
    )
    data = json.loads(out.stdout)
    disks = __lsblk_recursive(data.get('blockdevices', []), None, ignoreSysDisks, mounted)
    disk_dict = {disk.name: disk for disk in disks if disk.fstype != 'swap'}
    return disk_dict


def choose_disk(forMount:bool=True) -> str:
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

    print(f"Vyřazuji systémové disky: {blocked}")

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
        "Následující disky nejsou používány systémem:"
    ]
    items = [f"{n}  {s}" for (n, s) in safe_disks]
    idx=menu(headers, items, prompt="Vyber disk: ")
    disk = safe_disks[idx][0]

    # normalizace
    if disk.startswith("/dev/"):
        disk = disk.replace("/dev/", "")

    # kontrola, zda je validní
    available = [n.replace("/dev/", "") for (n, _) in safe_disks]

    if disk not in available:
        raise ValueError(f"Disk {disk} není mezi povolenými: {available}")

    return disk

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
        raise ShrinkError(f"Command failed: {cmd}\n{proc.stdout}")
    return proc.stdout
