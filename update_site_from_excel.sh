#!/usr/bin/env bash
# update_site_from_excel.sh
# Regenera el sitio en docs/ a partir de plantilla_sitio.xlsx y opcionalmente
# lo publica en GitHub Pages.
#
# Uso:
#   ./update_site_from_excel.sh                # regenera docs/ sin pushear
#   ./update_site_from_excel.sh --push         # regenera + commit + push
#   ./update_site_from_excel.sh <plantilla>    # usa otro Excel
#   ./update_site_from_excel.sh --from-fichas  # re-convierte el Excel de fichas
#                                                 antes de regenerar
#   ./update_site_from_excel.sh --help

set -euo pipefail

# ─────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS_DIR="$REPO_ROOT/docs"
BACKUP_DIR="$REPO_ROOT/.docs.bak"
DEFAULT_PLANTILLA="$REPO_ROOT/plantilla_sitio.xlsx"
DEFAULT_FICHAS="$REPO_ROOT/NP00033 Fichas Técnicas Equipos 20250408 DG.xlsx"

DO_PUSH=0
FROM_FICHAS=0
PLANTILLA="$DEFAULT_PLANTILLA"

# Parsear flags
for arg in "$@"; do
    case "$arg" in
        --push)        DO_PUSH=1 ;;
        --from-fichas) FROM_FICHAS=1 ;;
        --help|-h)
            sed -n '/^# update_site_from_excel\.sh/,/^$/p' "$0"
            exit 0
            ;;
        *) PLANTILLA="$arg" ;;
    esac
done

cd "$REPO_ROOT"

# ─────────────────────────────────────────────────────────────
# Colores
# ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${BLUE}▶${NC} $1"; }
ok()    { echo -e "${GREEN}✅${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠️${NC}  $1"; }
fail()  { echo -e "${RED}❌${NC} $1" >&2; }

# ─────────────────────────────────────────────────────────────
# Pre-checks
# ─────────────────────────────────────────────────────────────
[ -f "$REPO_ROOT/excel_migrator.py" ] || { fail "Falta excel_migrator.py"; exit 1; }

if [ "$FROM_FICHAS" -eq 1 ]; then
    [ -f "$REPO_ROOT/convert_fichas_to_template.py" ] || {
        fail "Falta convert_fichas_to_template.py"; exit 1;
    }
    [ -f "$DEFAULT_FICHAS" ] || {
        fail "No se encuentra el Excel de fichas en: $DEFAULT_FICHAS"; exit 1;
    }
fi

# ─────────────────────────────────────────────────────────────
# Paso opcional: re-convertir fichas técnicas → plantilla
# ─────────────────────────────────────────────────────────────
if [ "$FROM_FICHAS" -eq 1 ]; then
    info "Convirtiendo fichas técnicas → plantilla_sitio.xlsx"
    python3 "$REPO_ROOT/convert_fichas_to_template.py" "$DEFAULT_FICHAS"
    echo
fi

[ -f "$PLANTILLA" ] || { fail "No existe: $PLANTILLA"; exit 1; }

# ─────────────────────────────────────────────────────────────
# Backup de docs/ actual
# ─────────────────────────────────────────────────────────────
if [ -d "$DOCS_DIR" ]; then
    info "Respaldando docs/ a .docs.bak/"
    rm -rf "$BACKUP_DIR"
    cp -r "$DOCS_DIR" "$BACKUP_DIR"
fi

# ─────────────────────────────────────────────────────────────
# Regenerar
# ─────────────────────────────────────────────────────────────
info "Regenerando sitio desde: $PLANTILLA"
echo
if python3 "$REPO_ROOT/excel_migrator.py" "$PLANTILLA" "$DOCS_DIR"; then
    rm -rf "$BACKUP_DIR"
else
    fail "Falló la generación"
    if [ -d "$BACKUP_DIR" ]; then
        warn "Restaurando docs/ desde backup..."
        rm -rf "$DOCS_DIR"
        mv "$BACKUP_DIR" "$DOCS_DIR"
        ok "Backup restaurado"
    fi
    exit 1
fi

# ─────────────────────────────────────────────────────────────
# Mostrar diff
# ─────────────────────────────────────────────────────────────
echo
info "Cambios respecto a la última versión commiteada:"
echo
git add -N docs/ 2>/dev/null || true
CHANGES=$(git status --short docs/ | wc -l)
if [ "$CHANGES" -eq 0 ]; then
    ok "Sin cambios — el sitio ya estaba al día."
    exit 0
fi
git status --short docs/ | head -30
[ "$CHANGES" -gt 30 ] && echo "  ... y $((CHANGES - 30)) archivos más"

# ─────────────────────────────────────────────────────────────
# Commit + push opcional
# ─────────────────────────────────────────────────────────────
echo
if [ "$DO_PUSH" -eq 1 ]; then
    info "Modo --push: subiendo a GitHub Pages..."
    git add docs/
    git commit -m "Actualizar sitio desde Excel ($(date '+%Y-%m-%d %H:%M'))"
    git push
    ok "Push completo. GitHub Pages recompila en ~1-2 min."
    echo
    echo "🌐 https://jagilren.github.io/groupe_seb_qr/"
else
    info "Para publicar a GitHub Pages, ejecuta:"
    echo
    echo "    git add docs/"
    echo "    git commit -m 'Actualizar sitio'"
    echo "    git push"
    echo
    info "O re-ejecuta este script con --push:"
    echo "    ./update_site_from_excel.sh --push"
fi
