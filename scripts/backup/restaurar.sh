#!/bin/sh
# Restaura um dump gerado por backup.sh (Task 7.2, RNF10).
#
#   sh restaurar.sh <arquivo.dump> [banco_destino]
#
# Sem banco_destino, restaura em PGDATABASE (o banco em uso): como isso apaga os
# dados atuais, exige CONFIRMAR=sim. O banco destino e criado se nao existir.
set -eu

arquivo="${1:?uso: restaurar.sh <arquivo.dump> [banco_destino]}"
destino="${2:-${PGDATABASE:?defina PGDATABASE ou informe o banco destino}}"

if [ "$destino" = "${PGDATABASE:-}" ] && [ "${CONFIRMAR:-}" != sim ]; then
    echo "[restaurar] isso sobrescreve o banco '$destino'. Rode com CONFIRMAR=sim." >&2
    exit 1
fi

if [ -f "$arquivo.sha256" ]; then
    (cd "$(dirname "$arquivo")" && sha256sum -c "$(basename "$arquivo").sha256" >/dev/null)
    echo "[restaurar] checksum ok"
fi

# Conecta no banco de manutencao para criar o destino.
existe=$(psql --dbname=postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$destino'")
[ "$existe" = 1 ] || createdb --maintenance-db=postgres "$destino"

echo "[restaurar] $(date -u +%FT%TZ) $arquivo -> $destino"
pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error \
    --dbname="$destino" "$arquivo"
echo "[restaurar] ok"
