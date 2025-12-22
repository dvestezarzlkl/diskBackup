# JB disk tool

!!! DEPRECATED !!!

Přesunuto do [Terminal Manager](https://github.com/dvestezarzlkl/Dvestezar-Terminal-Manager-Debian-Based)

## imgtool – nástroj pro zálohy a obnovu disků

### urychlení spuštění

Pokud nechceme být v adresář a chceme rychle spouštět nástroj vytvoříme si ling do `/usr/local/bin/imgtool`:

```bash
sudo ln -s /cesta/k/imgtool.py /usr/bin/imgtool
```

pak už používáme jen `imgtool` místo `./imgtool.py`

### Popis

*RAW + SMART (layout + partitions) režim, gzip podpora, SHA kontrola:*

`imgtool.py` je univerzální CLI nástroj pro:

* **Zálohování celých disků** (`dd`)
* **Obnovu raw nebo gzip obrazů**
* **Chytrou zálohu** (layout + každá partition zvlášť přes partclone)
* **Chytrou obnovu** (včetně volitelného zvětšení poslední ext4)
* **Komprimaci / dekomprimaci** obrazů
* **Automatické generování SHA256 pro každý výstupní soubor**
* **Interaktivní výběr disku** (pokud není zadán `--disk`)
* **Automatické prefixování názvů souborů** (YYYY-MM-DD-HHMM_...)

Je určený pro Linux prostředí, včetně **WSL2**, a umožňuje jednoduché zálohování SD karet, USB disků, systémových image, nebo celé struktury partitions s minimem zásahů.

### Instalace

```bash
chmod +x imgtool.py
sudo apt install partclone gdisk gptfdisk growpart -y
```

Pro WSL VBox

```bash
sudo apt install partclone gdisk cloud-guest-utils parted -y
```

### Použití

```sh
imgtool.py MODE [parametry]
```

Dostupné režimy:

* `backup`
* `restore`
* `extract`
* `smart-backup`
* `smart-restore`
* `compress`
* `decompress`
* `shrink`

### Parametry (globální)

| Parametr         | Význam                                                |
| ---------------- | ----------------------------------------------------- |
| `--disk sdb`     | Název disku bez /dev (např. sdb, nvme0n1)             |
| `--file soubor`  | Cesta k .img / .img.gz nebo základní jméno pro výstup |
| `--dir adresář`  | Adresář pro smart backup/restore pokud nezadáme, nabídne se výběr |
| `--fast`         | Gzip -1 (rychlá komprese, velký soubor)               |
| `--max`          | Gzip -9 (pomalá komprese, malý soubor)                |
| `--noautoprefix` | Nevkládat prefix YYYY-MM-DD-HHMM_                     |
| `--resize`       | U smart-restore zvětšit poslední ext4 partition       |
| `--no-sha`       | Neověřovat SHA256 při restore (nedoporučeno)          |
| `--shrink-size` | U shrink zmenšit image na danou velikost (např. 4G) pokud nezadáme tak se automaticky vypočítá  |

Každý výstupní soubor generuje i `*.sha256`.

### Módy použití

#### 1) RAW BACKUP (dd)

##### Vytvoření zálohy bez komprese

```bash
sudo imgtool backup --disk sdf --file opi
```

Vytvoří:

```txt
2025-11-26-1420_opi.img
2025-11-26-1420_opi.img.sha256
```

##### Rychlá gzip komprese

```bash
sudo imgtool backup --disk sdf --fast
```

##### Maximální komprese

```bash
sudo imgtool backup --disk sdf --max
```

#### 2) RAW RESTORE nebo instalace Original image

Toto lze použít jak pro obnovení RESTORE tak pro instalaci image staženého z webu (např. Orangepi).

Obnova .img nebo .img.gz přímo na disk:

```bash
sudo imgtool restore --disk sdf --file 2025-11-26-1420_opi.img.gz
```

nebo

```bash
sudo imgtool restore --no-sha --file opi.img
```

* Pokud nepoužijeme `--disk` , zobrazí se interaktivní výběr disku, takže vyberem správný
* Také použijeme `--no-sha` pokud instalujeme image z webu, kde nemáme SHA256 k dispozici

Před obnovou se ověří SHA256
(lze vypnout `--no-sha`).

#### 3) Extract .img.gz → .img

```bash
sudo imgtool extract --file opi.img.gz
```

Vytvoří:

```txt
opi.img
opi.img.sha256
```

#### 4) SMART BACKUP (layout + partitions)

Tvoří:

* diskový layout (GPT nebo MBR)
* image každé partition
* SHA256 pro každý soubor
* manifest.json

```bash
sudo imgtool smart-backup --disk sdf --dir ./backup --fast
```

Výsledek:

```txt
backup/
  layout.gpt
  2025-11-26-1420_sdf_sdf1.img.gz
  2025-11-26-1420_sdf_sdf1.img.gz.sha256
  2025-11-26-1420_sdf_sdf2.img.gz
  2025-11-26-1420_sdf_sdf2.img.gz.sha256
  manifest.json
```

Obsah `manifest.json`:

```json
{
  "disk": "sdf",
  "created": "2025-11-26-1420",
  "size_bytes": 62537072640,
  "layout_file": "layout.gpt",
  "partitions": [
    {
      "name": "sdf1",
      "fstype": "vfat",
      "image": "2025-11-26-1420_sdf_sdf1.img.gz",
      "sha256_file": "2025-11-26-1420_sdf_sdf1.img.gz.sha256"
    },
    {
      "name": "sdf2",
      "fstype": "ext4",
      "image": "2025-11-26-1420_sdf_sdf2.img.gz",
      "sha256_file": "2025-11-26-1420_sdf_sdf2.img.gz.sha256"
    }
  ]
}
```

#### 5) SMART RESTORE

Obnova layoutu + partitions podle manifestu.

```bash
sudo imgtool smart-restore --disk sdf --dir ./backup
```

##### Volitelné zvětšení poslední ext4 partition

```bash
sudo imgtool smart-restore --disk sdf --dir ./backup --resize
```

Použije:

* `growpart`
* `resize2fs`

#### 6) Komprese existujícího .img

Po editaci loop zařízení:

```bash
sudo imgtool compress --file rootfs.img --max
```

#### 7) Dekomprese existujícího .img.gz

```bash
sudo imgtool decompress --file rootfs.img.gz
```

#### 8) Zmenšení existujícího .img

```bash
sudo imgtool shrink --file rootfs.img --shrink-size 4G
```

## Chování gzip

| Režim      | Parametr                 | Úroveň |
| ---------- | ------------------------ | ------ |
| rychlý     | `--fast`                 | -1     |
| maximální  | `--max`                  | -9     |
| default    | nic                      | -6     |
| žádný gzip | prostě nezvolíš fast/max |        |

## SHA256

Každý výstupní soubor dostane:

```txt
soubor.img
soubor.img.sha256
```

Kontrola při restore je automatická,
vypnout lze `--no-sha`.

## Interaktivní výběr disku

Pokud nevyplníš `--disk`, skript ukáže:

```txt
=== Dostupné disky ===
/dev/sda 512G disk
/dev/sdb 64G  disk
...
Zadej název disku:
```

## Bezpečnostní ochrany

* každá nevratná operace vyžaduje potvrzení `[y/N]`
* restore validuje SHA256 (pokud neřekneš jinak)
* disk musíš určit ručně nebo interaktivně
* partclone fallback na `dd`, pokud FS není podporován

## Doporučené workflow

### Záloha disku se stahováním do gzipu

```bash
sudo imgtool backup --disk sdf --fast --file orangepi
```

### Úpravy systémového image přes loop + komprese zpět

```bash
# loop-mount
  losetup --find --show --partscan orangepi.img
  mount /dev/loop0p2 /mnt/x

  # nebo

  imgmount.py --img orangepi.img

# edituj...

  # popř zmenši parititonu
    # zjistíme si velikost dat v ext4
    df -h /mnt/x
    # např je to 3.2G, tak zmenšíme na 4G
    umount /mnt/x # nebo použij imgmount.py pro odpojení
    growpart /dev/loop0 2 4G # zmenšíme partition 2 na 4G
    e2fsck -f /dev/loop0p2 # zkontrolujeme ext4

# umount

  umount /mnt/x
  losetup -d /dev/loop0

  # nebo jednoduše
  imgmount.py  # odpojí přes výběrové menu všechny připojené loop zařízení


# recompress
sudo imgtool compress --file orangepi.img --max
```

**Odpojení image a loop zařízení:**

```bash
umount /mnt/x
losetup -d /dev/loop0
```

**vytvoření hash souboru:**

```bash
sha256sum orangepi.img.gz > orangepi.img.gz.sha256
```

### Smart záloha SD karty Orangepi

```bash
sudo imgtool smart-backup --disk sdf --dir ./opi-backups --fast
```

### Smart restore

```bash
sudo imgtool smart-restore --disk sdf --dir ./opi-backups --resize
```

## Licence

MIT License © Jan Zedník dvestezar.cz 2025
