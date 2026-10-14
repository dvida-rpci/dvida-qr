#!/usr/bin/env bash
# Prepara el proyecto Supabase de una planta NUEVA: aplica todas las migraciones de
# supabase/migrations/ (histórico + plan de mantenimiento) y lista los pasos manuales.
#
# Uso: ./setup_supabase_planta.sh <project-ref>
#
# No usar en proyectos que ya tienen el histórico aplicado a mano con psql (DVida,
# qgxvukllzuaiyhzegaef): su historial de migraciones remoto no está sincronizado y
# `db push` intentaría recrear tablas existentes. Ahí cada migración nueva va con psql.
set -euo pipefail
cd "$(dirname "$0")"

if [[ $# -ne 1 ]]; then
    echo "Uso: $0 <project-ref>   (el ref está en la URL del proyecto: https://<ref>.supabase.co)"
    exit 1
fi
REF="$1"

command -v supabase >/dev/null || { echo "❌ Falta la CLI de Supabase (https://supabase.com/docs/guides/cli)"; exit 1; }

echo "📦 Migraciones a aplicar en $REF:"
ls -1 supabase/migrations/*.sql | sed 's|^|   |'
echo
echo "⚠️  La CLI debe tener sesión (supabase login) en la cuenta dueña de $REF."
read -r -p "Escribí el project-ref otra vez para confirmar: " CONFIRM
[[ "$CONFIRM" == "$REF" ]] || { echo "❌ Cancelado: el ref no coincide"; exit 1; }

supabase link --project-ref "$REF"
supabase db push

cat <<EOF

✅ Migraciones aplicadas en $REF.

Pasos manuales que quedan:
  1. 👤 Crear usuarios en Supabase → Authentication → Users (email + contraseña).
  2. 🔐 Darles perfil y rol (SQL Editor del proyecto):
       insert into public.profiles (user_id, full_name, role)
       select id, 'Nombre Apellido', 'oficina'   -- o 'tecnico'
       from auth.users where email = 'persona@empresa.com';
  3. 🔑 Copiar URL y anon key a site_config.json → bloque "supabase":
       supabase projects api-keys --project-ref $REF
       "supabase": { "url": "https://$REF.supabase.co", "anon_key": "<anon key>" }
     (nunca la service_role key)
  4. 🏗️ Generar el sitio (gui.py → Generar sitio, o ./update_site_from_excel.sh).
  5. 📋 gui.py → Plan de mantenimiento: Importar sábana base → Auto-asignar equipos →
     revisar el régimen de cada par A/B.
EOF
