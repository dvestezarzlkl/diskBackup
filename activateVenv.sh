#!/usr/bin/env bash
set -e

# Blokace spouštění jako ./skript
if [ "$0" = "$BASH_SOURCE" ]; then
    echo "Tento skript musí být spuštěn takto:"
    echo "    source $0"
    exit 1
fi

# Název "aktuálního" venvu (bude symlink na verzi)
CUR_VENV=".venv"

print_usage() {
    cat <<EOF
Použití:
  $0               - aktivuje existující .venv (bez vytváření)
  $0 3.10          - vytvoří/aktualizuje venv pro Python 3.10 (.venv310) a nastaví .venv
  $0 3.12          - vytvoří/aktualizuje venv pro Python 3.12 (.venv312) a nastaví .venv

Poznámka:
  - Pro tvorbu nového venv MUSÍŠ zadat verzi (např. 3.10).
  - Pokud .venv existuje a spustíš bez parametru, jen se aktivuje.
EOF
}

# ---------------------------------------------------------------------
#  ŽÁDNÝ ARGUMENT → jen aktivace, pokud existuje .venv
# ---------------------------------------------------------------------
if [ $# -eq 0 ]; then
    if [ -d "$CUR_VENV" ] || [ -L "$CUR_VENV" ]; then
        echo "Aktivuji existující virtuální prostředí: $CUR_VENV"
        # shellcheck disable=SC1091
        source "$CUR_VENV/bin/activate"
        echo "Python: $(python --version 2>/dev/null || echo 'neznámý')"
        return 0
    else
        echo "Chyba: .venv neexistuje a nebyla zadána verze."
        print_usage
        exit 1
    fi
fi

# ---------------------------------------------------------------------
#  MÁME ARGUMENT → očekáváme verzi typu 3.10, 3.12, ...
# ---------------------------------------------------------------------
PY_VER="$1"           # např. "3.10"
PY_CMD="python${PY_VER}"   # např. "python3.10"

echo "Požadovaná verze Pythonu: ${PY_VER} (${PY_CMD})"

if ! command -v "$PY_CMD" >/dev/null 2>&1; then
    echo "Chyba: ${PY_CMD} nebyl nalezen v PATH."
    echo "Nainstaluj ho např.:"
    echo "  sudo apt install ${PY_CMD} ${PY_CMD}-venv"
    exit 1
fi

# Suffix venv podle verze, např. .venv310
VENV_DIR=".venv$(echo "$PY_VER" | tr -d '.')"

echo "Vytvářím / používám venv: $VENV_DIR (Python: $PY_CMD)"

# ---------------------------------------------------------------------
#  VYTVOŘENÍ VENV, POKUD NEEXISTUJE
# ---------------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtuální prostředí $VENV_DIR neexistuje, vytvářím..."
    "$PY_CMD" -m venv "$VENV_DIR"
    echo "Venv $VENV_DIR vytvořen."
else
    echo "Virtuální prostředí $VENV_DIR již existuje."
fi

# ---------------------------------------------------------------------
#  AKTUALIZACE .venv → symlink na verzi specifický venv
# ---------------------------------------------------------------------
if [ -L "$CUR_VENV" ]; then
    echo "Odstraňuji starý symlink $CUR_VENV"
    rm "$CUR_VENV"
elif [ -d "$CUR_VENV" ]; then
    echo "Pozor: $CUR_VENV je adresář, nepřepisuji automaticky."
    echo "Pokud ho chceš nahradit symlinkem, smaž ho ručně:"
    echo "  rm -rf $CUR_VENV"
    echo "a spusť skript znovu."
    exit 1
elif [ -e "$CUR_VENV" ]; then
    echo "Pozor: $CUR_VENV existuje a není ani adresář, ani symlink."
    echo "Odstraň ho ručně a spusť skript znovu."
    exit 1
fi

ln -s "$VENV_DIR" "$CUR_VENV"
echo ".venv nyní ukazuje na $VENV_DIR"

# ---------------------------------------------------------------------
#  AKTIVACE
# ---------------------------------------------------------------------
echo "Aktivuji $CUR_VENV..."
# shellcheck disable=SC1091
source "$CUR_VENV/bin/activate"
echo "Python: $(python --version)"

# Případně auto-install requirements.txt:
if [ -f "requirements.txt" ]; then
    echo "Instaluji závislosti z requirements.txt..."
    pip install -r requirements.txt
fi

echo "Hotovo."
return 0
