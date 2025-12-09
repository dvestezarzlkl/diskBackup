import libs.toolhelp as th
from pathlib import Path
from .JBLibs.input import anyKey, get_input,select,select_item,confirm
import re

def swapIsActive(filename: str) -> bool:
    """
    Zjistí, zda je daný swap soubor aktivní.
    
    Args:
        filename: cesta k swap souboru (např. "/swapfile")
    Returns:
        True pokud je swap aktivní, False jinak
    """
    filename = Path(filename).resolve()
    if not filename.exists():
        return False
    activeSwaps = th.runRet("swapon --show --raw --noheadings").splitlines()
    flnmTx=str(filename)+""

    for line in activeSwaps:
        if line.startswith(flnmTx):
            return True

    return False

def inputNewSwapFile() -> str|None:
    """
    Nabídne uživateli výběr swap souboru z aktuálního adresáře.
    
    Returns:
        Cesta k vybranému swap souboru jako string, nebo None pokud nebyl vybrán žádný.
    """
    print("Vyberte swap soubor z aktuálního adresáře:")
    filename = None
    while True:
        filename = get_input("Zadej nový název swap souboru, nemusí obsahovat '.img': ")
        if not filename:
            return None
        if filename.lower() == "q":
            return None
        if not filename.endswith(".img"):
            filename += ".img"
        return "/" + filename

def modifyFstabSwapEntry(filename: str, add: bool = True) -> None:
    """
    Přidá nebo odstraní záznam o swap souboru v /etc/fstab.
    
    Args:
        filename: cesta k swap souboru (např. "/swapfile")
        add: pokud True, přidá záznam, pokud False, odstraní záznam
    """
    fstab_path = Path("/etc/fstab")
    fstab_lines = fstab_path.read_text(encoding="utf-8").splitlines()
    entry = f"{filename} none swap sw 0 0"

    if add:
        if any(filename in line for line in fstab_lines):
            print(f"[FSTAB] Swap soubor {filename} již existuje v /etc/fstab.")
            return
        print(f"[FSTAB] Přidávám swap soubor {filename} do /etc/fstab.")
        with open(fstab_path, "a", encoding="utf-8") as f:
            f.write("\n" + entry + "\n")
    else:
        new_lines = [line for line in fstab_lines if filename not in line]
        if len(new_lines) == len(fstab_lines):
            print(f"[FSTAB] Swap soubor {filename} nebyl nalezen v /etc/fstab.")
            return
        print(f"[FSTAB] Odstraňuji swap soubor {filename} z /etc/fstab.")
        fstab_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

def resizeSwap(filename: str|None, targetSize: str) -> None:
    """
    Změní velikost swap souboru.
    
    - Zkontroluje využití RAM a swapu (bezpečnost).
    - Výpočet zda je soubor aktivní swap.
    - Pokud neexistuje → nabídne vytvoření.
    - Pokud existuje a je aktivní → swapoff.
    - Vytvoří nový o dané velikosti.
    - Nastaví mkswap, znovu zapne swapon.
    - Přidá/aktualizuje /etc/fstab.
    
    Args:
        filename: cesta k swap souboru (např. "/swapfile")  
            pokud je None, nabídne výběr ze souborů v aktuálním adresáři
        targetSize: velikost jako string, např. "1G", "512M"
    """

    if filename is None:
        x=select("Nebyl zadán swap soubor",[
            select_item("Vyhledat v dialogu","f"),
            select_item("Zadat nový název","n")
        ])
        if not x.item:
            print("Zrušeno uživatelem.")
            return
        if x.item.choice=="n":        
            filename = inputNewSwapFile()
            if filename is None:
                print("Zrušeno uživatelem.")
                return
        else:
            # vybereme soubor přes dialog        
            filename = th.scan_current_dir_for_imgs(fromDir="/")
            if filename is None:
                print("[ERROR] Nebyl vybrán žádný swap soubor.")
                return

    filename:Path = Path(filename).resolve()
    if not filename.is_absolute():
        print(f"[ERROR] Cesta k swap souboru musí být absolutní: {filename}")
        return

    if filename.is_file() and not swapIsActive(filename):
        print(f"[INFO] Swap file {filename} není aktivní.")
        return

    # ----------------------------
    # 1) Zjistit RAM + SWAP load
    # ----------------------------
    meminfo = th.runRet("grep -E 'MemTotal|MemAvailable|SwapTotal|SwapFree' /proc/meminfo")
    mem = dict()
    for line in meminfo.splitlines():
        k, v = line.split(":")
        mem[k.strip()] = int(v.strip().split()[0]) * 1024  # přepočet na B

    mem_total = mem.get("MemTotal", 0)
    mem_avail = mem.get("MemAvailable", 0)
    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    swap_used = swap_total - swap_free

    print("== RAM/SWAP info ==")
    print(f"RAM:   {mem_total/1e9:.2f} GB total  | {mem_avail/1e9:.2f} GB free")
    print(f"SWAP:  {swap_total/1e9:.2f} GB total | {swap_used/1e9:.2f} GB used")

    # Bezpečnostní kontrola:
    # Pokud by vypnutí swapu snížilo dostupnou paměť pod 1.5× memory pressure, varuj
    if swap_used > mem_avail:
        print("\n[WARNING] Systém má méně volné RAM než využitého swapu!")
        print("Vypnutí swapu může způsobit OOM (out-of-memory).")
        if not confirm("Přesto pokračovat?"):
            print("Zrušeno.")
            return

    # ----------------------------------------
    # 2) Zjistit, zda swap existuje a je aktivní
    # ----------------------------------------
    swapActive = swapIsActive(str(filename))
    exists = filename.exists()

    # ----------------------------------------
    # 3) Pokud neexistuje → nabídnout vytvoření
    # ----------------------------------------
    if not exists:
        print(f"[INFO] Swap file {filename} neexistuje.")
        if not confirm(f"Vytvořit nový swap {targetSize}?"):
            print("Zrušeno uživatelem.")
            return
    else:
        print(f"[INFO] Swap file existuje: {filename}")
        
    if targetSize is None:
        # dotaz na zadání nové velikosti nebo při ne smazání souboru
        opts=[]
        if exists:
            opts.append(select_item("Zadat novou velikost","s"))
            opts.append(select_item("Smazat stávající swap soubor","d"))
        else:
            opts.append(select_item("Zadat velikost","s"))
        
        x=select("Cílová velikost swap souboru nebyla zadána.",opts)
        if not x.item:
            print("Zrušeno uživatelem.")
            return
        if x.item.choice=="s":
            mb, targetSize = th.inputSize("Cílová velikost swap (např. 1G, 512M): ")
            if targetSize is None:
                print("[ERROR] Nezadána cílová velikost swap souboru.")
                return
        else:
            if not confirm(f"Opravdu smazat stávající swap soubor {filename}?!"):
                print("Zrušeno uživatelem.")
                return
            print(f"[RM] Mažu swap soubor: {filename}")
            targetSize = "0"

    if targetSize!="0" and not re.match(r"^\d+[GMK]$", targetSize):
        print(f"[ERROR] Neplatný formát velikosti: {targetSize}")
        return       

    # ----------------------------------------
    # 4) Pokud je aktivní → swapoff
    # ----------------------------------------
    if swapActive:
        print(f"[SWAPOFF] swapoff {filename}")
        th.run(["sudo", "swapoff", str(filename)])

    # ----------------------------------------
    # 5) Smazat starý soubor a vytvořit nový
    # ----------------------------------------
    if filename.exists():
        print(f"[RM] Odstraňuji starý swap: {filename}")
        filename.unlink()

    if targetSize == "0":
        modifyFstabSwapEntry(str(filename), add=False)
        
        print("[DONE] Swap soubor byl odstraněn.")
        return

    print(f"[CREATE] Vytvářím nový swap {filename} o velikosti {targetSize}")

    # vytvoření sparse file
    th.run(["sudo", "fallocate", "-l", targetSize, str(filename)])

    # správná práva
    th.run(["sudo", "chmod", "600", str(filename)])

    # vytvořit swap strukturu
    th.run(["sudo", "mkswap", str(filename)])

    # zapnout
    th.run(["sudo", "swapon", str(filename)])

    print(f"[OK] Swap aktivní: {filename}")

    # ----------------------------------------
    # 6) Zapsat do /etc/fstab pokud tam není
    # ----------------------------------------
    modifyFstabSwapEntry(str(filename), add=True)

    print("[DONE] Resize swap dokončen.")
