import os
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import List
import re
from libs.JBLibs.c_menu import c_menu,c_menu_block_items,c_menu_item,onSelReturn


@dataclass
class c_fs_itm:
    name: str
    ext: str
    size: int
    mtime: int
    type: int   # 0=file, 1=dir

    @property
    def is_file(self) -> bool:
        return self.type == 0

    @property
    def is_dir(self) -> bool:
        return self.type == 1


def getDir(
    dir: str|Path,
    filterFile: str|bool = True,
    filterDir:str|bool=True,
    current_dir: str|Path|None = None,
    hidden: bool = False
) -> tuple[Path, List[c_fs_itm]]:
    """
    Vrátí seznam souborů a adresářů v zadaném adresáři.
    
    Args:
        dir (str): Cesta k adresáři. 
                   - Absolutní → použije se přímo
                   - Relativní → spojí se s current_dir
                   - "." → parent dir
        filterFile (str): regexp filtr pro názvy souborů
        filterDir (str|bool): buď:
            str - regexp filtr pro názvy adresářů
            False - nezahrnovat adresáře
            True - zahrnout všechny adresáře
        current_dir (str|Path|None): výchozí adresář pokud je relativní cesta
        hidden (bool): zda zahrnout skryté soubory (začínající tečkou)
            True - zahrnout
            False - nezahrnovat
        
    Returns:
        tuple[Path,List[c_fs_itm]]: adresář (popř změněnný) ze kterého se čte a seznam položek, a seznam položek
        
    Raises:
        FileNotFoundError
        NotADirectoryError
        TypeError
    """
    if not isinstance(dir, (str, Path)):
        raise TypeError("dir musí být string nebo Path")
    if not isinstance(filterFile, (str, bool)):
        raise TypeError("filterFile musí být string nebo None")
    if not isinstance(filterDir, (str, bool)):
        raise TypeError("filterDir musí být string nebo bool")
    if isinstance(current_dir, str):
        current_dir = Path(current_dir).resolve()
    if not isinstance(current_dir, (Path, type(None))):
        raise TypeError("current_dir musí být string nebo None")
    
    if isinstance(dir, str):
        dir = Path(dir).resolve()
    
    # určení výchozí cesty
    if current_dir is None:
        current_dir = Path(os.getcwd()).resolve()

    # Pokud ".", přejdi do parent
    if dir == ".":
        base = current_dir.parent
    else:
        p = Path(dir)
        base = p if p.is_absolute() else current_dir / p

    base = base.resolve()

    if not base.exists():
        raise FileNotFoundError(f"Cesta neexistuje: {base}")

    if not base.is_dir():
        raise NotADirectoryError(f"Není adresář: {base}")

    items: List[c_fs_itm] = []
    
    flRgx:None|re.Pattern = None
    dirRgx:bool|re.Pattern = None
    if isinstance(filterFile, str):
        flRgx = re.compile(filterFile,re.IGNORECASE)
    if isinstance(filterDir, str):
        dirRgx = re.compile(filterDir,re.IGNORECASE)
    else:
        dirRgx = filterDir

    # projdi adresář
    for entry in base.iterdir():
        name = entry.name

        # filtrace podle masky
        if entry.is_file():
            if not hidden and name.startswith("."):
                continue            
            if flRgx is False:
                continue
            if isinstance(flRgx, re.Pattern) and flRgx.search(name) is None:
                continue
        if entry.is_dir():
            if not hidden and name.startswith("."):
                continue            
            if dirRgx is False:
                continue
            if isinstance(dirRgx, re.Pattern) and dirRgx.search(name) is None:
                continue

        stat = entry.stat()
        ext = entry.suffix.lower() if entry.is_file() else ""

        items.append(
            c_fs_itm(
                name=name,
                ext=ext,
                size=stat.st_size,
                mtime=int(stat.st_mtime),
                type=1 if entry.is_dir() else 0
            )
        )

    # řazení: dirs first, then files, alphabetical
    items.sort(
        key=lambda x: (0 if x.type == 1 else 1, x.name.lower())
    )

    return (base, items)

class fs_menu(c_menu):
    """Menu pro výběr souborů a adresářů v daném adresáři.
    Využívá getDir pro získání seznamu položek.
    """
    
    def __init__(
        self,
        dir: str,
        filterFile: str|bool = True,
        filterDir: str|bool = True,
        hidden: bool = False,
        itemsOnPage: int = 30,
        *args,
        **kwargs
    ) -> None:
        super().__init__(*args, **kwargs,minMenuWidth=80)
        self.dir = dir
        self.filterFile = filterFile
        self.filterDir = filterDir
        self.current_dir = Path(dir).resolve()
        self.hidden = hidden
        self.items = []
        self.title = c_menu_block_items()
        self.title.append( ("Výběr souboru/adresáře","c") )
        
        self.keyBind('\x1b[C', self.toAdr)
        self.keyBind('\x1b[D', self.outAdr)
        # zaregistrujeeme page up/down
        self.keyBind('\x1b[5~', self.pageUp)
        self.keyBind('\x1b[6~', self.pageDown)
        # home a end
        self.keyBind('\x1b[H', self.toTop)
        self.keyBind('\x1b[F', self.toBottom)
                
        # f4 toggle hidden
        self.keyBind('\x1bOS', self.toggleHidden)
        
        # f2 toggle show dir
        self.keyBind('\x1bOQ', self.toggleShowDir)
                
        self.oldDir = None
        self.dirItems=[]
        self.page=0
        self.pageItemsCount=itemsOnPage
        # pokud je míň jak 10 nebo víc jak 100, tak nastavíme očetříme na 10 nebo 100
        if self.pageItemsCount < 10:
            self.pageItemsCount = 10
        elif self.pageItemsCount > 100:
            self.pageItemsCount = 100
            
        self.filterList:None|re.Pattern=None
        
    def onShowMenu(self) -> None:
        """Při zobrazení menu načte položky z adresáře."""
        if self.oldDir != self.current_dir:
            self.oldDir = self.current_dir            
                
            self.current_dir, items = getDir(
                self.current_dir,
                filterFile=self.filterList or self.filterFile,
                filterDir=self.filterList or self.filterDir,
                hidden=self.hidden
            )
            self.dirItems=[]
            
            self.page=0
            choice=0
            for itm in items:
                display_name = f"[DIR] {itm.name}" if itm.is_dir else itm.name
                
                self.dirItems.append(
                    c_menu_item(
                        display_name+itm.ext,
                        f"{choice:02}",
                        self.vyberItem,
                        None,
                        itm
                    )
                )
                choice+=1
                
        # do .menu přidáme položky z dirItems se stránkováním
        start_idx = self.page * self.pageItemsCount
        end_idx = start_idx + self.pageItemsCount
        paged_items = self.dirItems[start_idx:end_idx]
        self.menu = paged_items
        
        self.menu.append(None)  # oddělovač
        self.menu.append(c_menu_item("Nápověda", "h", self.showHelp))
        self.menu.append(c_menu_item("Nastav filtr názvů", "f", self.setFilter))
        
        # aktualizace subtitle
        self.subTitle = c_menu_block_items()
        self.subTitle.append( (f"Aktuální adresář:", str(self.current_dir)) )
        self.subTitle.append( (f"Stránka:", f"{self.page + 1} / {((len(self.dirItems) - 1) // self.pageItemsCount) + 1}") )
        self.subTitle.append( (f"Zobrazení skrytých souborů (F4):", "ANO" if self.hidden else "NE") )
        self.subTitle.append( (f"Zobrazování pouze souborů (F2):", "NE" if self.filterDir is True else (self.filterDir if isinstance(self.filterDir,str) else "ANO")) )
        self.subTitle.append( (f"Filtr názvů souborů ('f'):", self.filterList if self.filterList else "ŽÁDNÝ") )
        
    def vyberItem(self, item:c_menu_item) -> onSelReturn:
        """Zpracuje výběr položky."""
        return onSelReturn(endMenu=True,data=item.data.name + item.data.ext)
        
    def toAdr(self, item:c_menu_item) -> None:
        """Zpracuje vložení klávesy."""
        
        if isinstance(item, c_menu_item):
            fs:c_fs_itm = getattr(item,'data',None)
            if isinstance(fs, c_fs_itm) and fs.is_dir:
                self.current_dir = self.current_dir / fs.name
                self.filterList = None
                self.menuRecycle=True
        
        return None
    
    def outAdr(self, item:c_menu_item) -> None:
        """Zpracuje vložení klávesy."""

        if isinstance(item, c_menu_item):
            fs:c_fs_itm = getattr(item,'data',None)
            if isinstance(fs, c_fs_itm):        
                parent = self.current_dir.parent
                if parent != self.current_dir:
                    self.current_dir = parent
                    self.filterList = None
                    self.menuRecycle=True
        
        return None
    
    def pageUp(self, item:c_menu_item) -> None:
        """Zpracuje vložení klávesy Page Up."""
        if self.page > 0:
            self.page -= 1
            self.menuRecycle = True
        return None
    
    def pageDown(self, item:c_menu_item) -> None:
        """Zpracuje vložení klávesy Page Down."""
        max_page = len(self.dirItems) // self.pageItemsCount
        if self.page < max_page:
            self.page += 1
            self.menuRecycle = True
        return None
    
    def toTop(self, item:c_menu_item) -> None:
        """Zpracuje vložení klávesy Home."""
        if self.page != 0:
            self.page = 0
            self.menuRecycle = True
        return None
    def toBottom(self, item:c_menu_item) -> None:
        """Zpracuje vložení klávesy End."""
        max_page = len(self.dirItems) // self.pageItemsCount
        if self.page != max_page:
            self.page = max_page
            self.menuRecycle = True
        return None
    
    def setFilter(self, item:c_menu_item) -> None:
        """Zpracuje vložení klávesy F3 pro zadání filtru."""
        from libs.JBLibs.input import get_input,reset
        
        reset()
        inp = get_input(
            "Zadejte filtr pro názvy souborů a adresářů (regexp), prázdné pro všechny:",
            True
        )
        inp = inp.strip()
        if inp is not None:
            if inp == "":
                self.filterList = None
            else:
                rg=re.compile(inp,re.IGNORECASE)
                self.filterList = rg.pattern
            self.menuRecycle = True
            self.oldDir = None  # vynutí načtení znovu
        return None
    
    def toggleHidden(self, item:c_menu_item) -> None:
        """Zpracuje vložení klávesy F4 pro přepnutí zobrazení skrytých souborů."""
        self.hidden = not self.hidden
        self.oldDir = None  # vynutí načtení znovu
        self.menuRecycle = True
        return None
    
    def toggleShowDir(self, item:c_menu_item) -> None:
        """Zpracuje vložení klávesy F2 pro přepnutí zobrazení adresářů."""
        if self.filterDir is False:
            self.filterDir = True
        else:
            self.filterDir = False
        self.oldDir = None  # vynutí načtení znovu
        self.menuRecycle = True
        return None
    
    def showHelp(self, item:c_menu_item) -> None:
        """Zobrazí nápovědu pro ovládání FS menu."""
        from libs.JBLibs.term import cls   # pokud máš vlastní cls(), jinak použij print("\033c")
        from libs.JBLibs.input import reset, anyKey

        cls()
        print("=== Nápověda pro prohlížeč souborů ===\n")
        print("Navigace:")
        print("  →   vstoupit do adresáře")
        print("  ←   o úroveň výš")
        print("  ↑↓  pohyb v seznamu")
        print("  PgUp / PgDown  stránkování")
        print("  Home / End     skok na začátek / konec")
        print("")
        print("Filtry a zobrazení:")
        print("  F2  přepnout zobrazování adresářů")
        print("  F4  zobrazit / skrýt skryté soubory (.)")
        print("  f   zadat regexp filtr pro názvy")
        print("        ponech prázdné pro zrušení filtru")
        print("")
        print("Obecné:")
        print("  ENTER   vybrat položku")
        print("  ESC     zavřít menu")
        print("")
        print("----------------------------------------")
        print(" Stiskněte ENTER pro návrat do menu ...")
        print("----------------------------------------\n")

        reset()
        anyKey()

        self.menuRecycle = True
        return None
    
            
m=fs_menu('/',itemsOnPage=15)

if m.run() is None:
    print(m.getLastSelItem().data)