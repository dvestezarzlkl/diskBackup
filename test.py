from libs.JBLibs.fs_helper import e_fs_menu_select,fs_menu
from pathlib import Path
            
m=fs_menu('python',
    select=e_fs_menu_select.file,
    itemsOnPage=15,
    lockToDir=Path('/mnt')
)

if m.run() is None:
    print(m.getLastSelItem().data)