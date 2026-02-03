#!/bin/bash

# Script d'installation pour Launchpad Mini MK3 dans Ableton Live 12
# Copie les fichiers du script vers le dossier MIDI Remote Scripts d'Ableton

# Couleurs pour l'output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Chemins
SOURCE_DIR="/home/mahed/projects/launchpad-mini-mk3-script"
DEST_DIR="/mnt/c/ProgramData/Ableton/Live 12 Suite/Resources/MIDI Remote Scripts/Launchpad_Mini_MK3"

echo -e "${YELLOW}=== Installation du script Launchpad Mini MK3 ===${NC}"
echo ""

# Vérifier que le dossier source existe
if [ ! -d "$SOURCE_DIR" ]; then
    echo -e "${RED}Erreur: Le dossier source n'existe pas: $SOURCE_DIR${NC}"
    exit 1
fi

# Vérifier que le dossier destination parent existe
DEST_PARENT="/mnt/c/ProgramData/Ableton/Live 12 Suite/Resources/MIDI Remote Scripts"
if [ ! -d "$DEST_PARENT" ]; then
    echo -e "${RED}Erreur: Le dossier MIDI Remote Scripts n'existe pas: $DEST_PARENT${NC}"
    echo -e "${YELLOW}Vérifiez que Ableton Live 12 Suite est bien installé.${NC}"
    exit 1
fi

# Supprimer l'ancien dossier s'il existe
if [ -d "$DEST_DIR" ]; then
    echo -e "${YELLOW}Suppression de l'ancien script...${NC}"
    rm -rf "$DEST_DIR"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Ancien script supprimé${NC}"
    else
        echo -e "${RED}✗ Erreur lors de la suppression de l'ancien script${NC}"
        exit 1
    fi
fi

# Créer le dossier de destination
echo -e "${YELLOW}Création du dossier de destination...${NC}"
mkdir -p "$DEST_DIR"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dossier créé${NC}"
else
    echo -e "${RED}✗ Erreur lors de la création du dossier${NC}"
    exit 1
fi

# Copier tous les fichiers .py
echo -e "${YELLOW}Copie des fichiers Python...${NC}"
cp "$SOURCE_DIR"/*.py "$DEST_DIR/"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Fichiers Python copiés${NC}"
else
    echo -e "${RED}✗ Erreur lors de la copie des fichiers${NC}"
    exit 1
fi

# Supprimer les logs Ableton
LOG_FILE="/mnt/c/Users/mahed/AppData/Roaming/Ableton/Live 12.3/Preferences/Log.txt"
if [ -f "$LOG_FILE" ]; then
    echo -e "${YELLOW}Suppression des logs Ableton...${NC}"
    rm "$LOG_FILE"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Logs supprimés${NC}"
    else
        echo -e "${RED}✗ Erreur lors de la suppression des logs${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Fichier de log non trouvé (pas d'erreur)${NC}"
fi

# Lister les fichiers copiés
echo ""
echo -e "${GREEN}Fichiers installés:${NC}"
ls -1 "$DEST_DIR"/*.py | while read file; do
    basename "$file"
done

echo ""
echo -e "${GREEN}=== Installation terminée avec succès! ===${NC}"
echo ""
echo -e "${YELLOW}Prochaines étapes:${NC}"
echo "1. Fermez Ableton Live complètement si il est ouvert"
echo "2. Relancez Ableton Live"
echo "3. Allez dans Préférences → Link/Tempo/MIDI"
echo "4. Sélectionnez 'Launchpad Mini MK3' dans Control Surface"
echo "5. Sélectionnez 'LPMiniMK3 MIDI' pour Input et Output"
echo ""
echo -e "${YELLOW}Pour tester le mode copier-coller:${NC}"
echo "• Maintenez le bouton Stop/Solo/Mute (bouton de scène en bas à droite)"
echo "• Cliquez sur un clip pour le copier"
echo "• Cliquez sur un slot vide pour coller"
echo "• Relâchez le bouton pour effacer le presse-papier"
echo ""
