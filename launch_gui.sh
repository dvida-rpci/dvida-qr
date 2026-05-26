#!/usr/bin/env bash
# launch_gui.sh — lanza la interfaz NiceGUI del configurador del sitio.
#
# Requisitos: pip3 install --break-system-packages nicegui openpyxl

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'

echo -e "${BLUE}▶${NC} Iniciando configurador en http://localhost:8080"
echo -e "${BLUE}▶${NC} Para abrir en Windows desde WSL:"
echo -e "    ${GREEN}cmd.exe /c start http://localhost:8080${NC}"
echo

exec python3 gui.py
