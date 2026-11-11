#!/bin/sh
# Backup do banco (Task 7.2, RNF10).
#
# Gera um dump no formato custom do pg_dump (comprimido e restauravel tabela a
# tabela), confere se ele e legivel, grava o sha256 ao lado e aplica a retencao:
#
#   diario/  -> um dump por execucao, mantidos por BACKUP_RETENCAO_DIAS (7)
#   semanal/ -> copia do dump de domingo, mantida por BACKUP_RETENCAO_SEMANAS (4)
#
# Conexao pelas variaveis padrao do libpq: PGHOST, PGPORT, PGUSER, PGPASSWORD,
# PGDATABASE. BACKUP_DIR deve apontar para um disco/volume separado do banco.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENCAO_DIAS="${BACKUP_RETENCAO_DIAS:-7}"
RETENCAO_SEMANAS="${BACKUP_RETENCAO_SEMANAS:-4}"
: "${PGDATABASE:?defina PGDATABASE}"

mkdir -p "$BACKUP_DIR/diario" "$BACKUP_DIR/semanal"

nome="${PGDATABASE}_$(date -u +%Y%m%d_%H%M%S).dump"
destino="$BACKUP_DIR/diario/$nome"

echo "[backup] $(date -u +%FT%TZ) gerando $destino"
# Grava num .parcial e so renomeia no fim: um dump interrompido nunca parece valido.
pg_dump --format=custom --no-owner --no-privileges --file="$destino.parcial"
pg_restore --list "$destino.parcial" >/dev/null
mv "$destino.parcial" "$destino"
(cd "$BACKUP_DIR/diario" && sha256sum "$nome" >"$nome.sha256")
echo "[backup] ok: $(du -h "$destino" | cut -f1)"

if [ "$(date -u +%u)" = 7 ]; then
    cp "$destino" "$destino.sha256" "$BACKUP_DIR/semanal/"
    echo "[backup] copia semanal guardada"
fi

# -mtime +N apaga o que tem mais de N+1 dias completos.
find "$BACKUP_DIR/diario" -name '*.dump*' -mtime +"$((RETENCAO_DIAS - 1))" -print -delete
find "$BACKUP_DIR/semanal" -name '*.dump*' -mtime +"$((RETENCAO_SEMANAS * 7 - 1))" -print -delete
