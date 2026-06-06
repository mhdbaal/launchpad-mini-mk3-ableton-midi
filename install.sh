#!/bin/bash

# Script d'installation pour les Launchpad (Mini MK3 / Pro MK3) dans Ableton Live 12.
#
# Architecture "overlay assembly" :
#   - les fichiers .py à la RACINE du repo sont partagés entre tous les devices
#   - mini/ et pro/ contiennent les modules device-specific (mêmes noms de
#     modules d'un device à l'autre : device_profile.py, elements.py, ...)
#   - l'installation assemble À PLAT racine + overlay dans le dossier cible,
#     donc tous les imports relatifs `from .x import y` résolvent tels quels.
#   L'ordre de copie shared → overlay est OBLIGATOIRE (l'overlay doit gagner
#   en cas de collision, même si le garde-fou ci-dessous interdit ce cas).
#
# Usage : ./install.sh [--mini|--pro|--all]   (défaut : --all)

set -u

# Couleurs pour l'output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Chemins
SOURCE_DIR="/home/mahed/projects/launchpad-mini-mk3-script"
DEST_PARENT="/mnt/c/ProgramData/Ableton/Live 12 Suite/Resources/MIDI Remote Scripts"
LOG_FILE="/mnt/c/Users/mahed/AppData/Roaming/Ableton/Live 12.3/Preferences/Log.txt"

# Sélection des cibles
INSTALL_MINI=false
INSTALL_PRO=false
case "${1:---all}" in
    --mini) INSTALL_MINI=true ;;
    --pro)  INSTALL_PRO=true ;;
    --all)  INSTALL_MINI=true; INSTALL_PRO=true ;;
    *) echo -e "${RED}Usage: ./install.sh [--mini|--pro|--all]${NC}"; exit 1 ;;
esac

echo -e "${YELLOW}=== Installation des scripts Launchpad ===${NC}"
echo ""

# Vérifier que le dossier source existe
if [ ! -d "$SOURCE_DIR" ]; then
    echo -e "${RED}Erreur: Le dossier source n'existe pas: $SOURCE_DIR${NC}"
    exit 1
fi

# Vérifier que le dossier MIDI Remote Scripts existe
if [ ! -d "$DEST_PARENT" ]; then
    echo -e "${RED}Erreur: Le dossier MIDI Remote Scripts n'existe pas: $DEST_PARENT${NC}"
    echo -e "${YELLOW}Vérifiez que Ableton Live 12 Suite est bien installé.${NC}"
    exit 1
fi

# Garde-fou : aucun basename ne doit exister à la fois à la racine (shared)
# et dans un overlay — sinon un device hériterait du mauvais fichier.
check_collisions() {
    local overlay_dir="$1"
    local collision=false
    for f in "$SOURCE_DIR/$overlay_dir"/*.py; do
        [ -e "$f" ] || continue
        if [ -e "$SOURCE_DIR/$(basename "$f")" ]; then
            echo -e "${RED}✗ Collision: $(basename "$f") existe à la racine ET dans $overlay_dir/${NC}"
            collision=true
        fi
    done
    if [ "$collision" = true ]; then
        echo -e "${RED}Installation annulée. Déplacez le fichier d'un seul côté.${NC}"
        exit 1
    fi
}

# Assemble racine (shared) + overlay (device) à plat dans le dossier cible.
install_device() {
    local overlay_dir="$1"   # mini | pro
    local dest_name="$2"     # Launchpad_Mini_MK3 | Launchpad_Pro_MK3
    local dest_dir="$DEST_PARENT/$dest_name"

    if [ ! -d "$SOURCE_DIR/$overlay_dir" ]; then
        echo -e "${YELLOW}⚠ Overlay $overlay_dir/ inexistant — $dest_name ignoré${NC}"
        return 0
    fi

    check_collisions "$overlay_dir"

    echo -e "${YELLOW}--- $dest_name ---${NC}"

    if [ -d "$dest_dir" ]; then
        rm -rf "$dest_dir" || { echo -e "${RED}✗ Erreur suppression ancien script${NC}"; exit 1; }
        echo -e "${GREEN}✓ Ancien script supprimé${NC}"
    fi

    mkdir -p "$dest_dir" || { echo -e "${RED}✗ Erreur création dossier${NC}"; exit 1; }

    # 1) fichiers partagés (racine), 2) overlay device — l'ordre compte.
    cp "$SOURCE_DIR"/*.py "$dest_dir/" || { echo -e "${RED}✗ Erreur copie fichiers partagés${NC}"; exit 1; }
    cp "$SOURCE_DIR/$overlay_dir"/*.py "$dest_dir/" || { echo -e "${RED}✗ Erreur copie overlay $overlay_dir${NC}"; exit 1; }

    echo -e "${GREEN}✓ $(ls -1 "$dest_dir"/*.py | wc -l) fichiers installés ($(basename "$dest_dir"))${NC}"
}

[ "$INSTALL_MINI" = true ] && install_device mini Launchpad_Mini_MK3
[ "$INSTALL_PRO" = true ] && install_device pro Launchpad_Pro_MK3

# Supprimer le log Ableton (une seule fois, partagé par toute l'instance Live)
if [ -f "$LOG_FILE" ]; then
    rm "$LOG_FILE" && echo -e "${GREEN}✓ Logs Ableton supprimés${NC}" \
        || echo -e "${RED}✗ Erreur lors de la suppression des logs${NC}"
else
    echo -e "${YELLOW}⚠ Fichier de log non trouvé (pas d'erreur)${NC}"
fi

echo ""
echo -e "${GREEN}=== Installation terminée avec succès! ===${NC}"
echo ""
echo -e "${YELLOW}Prochaines étapes:${NC}"
echo "1. Fermez Ableton Live complètement si il est ouvert"
echo "2. Relancez Ableton Live"
echo "3. Allez dans Préférences → Link/Tempo/MIDI"
echo "4. Control Surface :"
[ "$INSTALL_MINI" = true ] && echo "   • Launchpad Mini MK3 → Input/Output: MIDIIN2/MIDIOUT2 (LPMiniMK3 MIDI)"
[ "$INSTALL_PRO" = true ]  && echo "   • Launchpad Pro MK3  → Input/Output: 3e paire de ports (LPProMK3 MIDI / MIDIIN3)"
echo ""
