#!/bin/sh
# Teste periodico de restauracao (Task 7.2, RNF10).
#
# Restaura o backup diario mais recente num banco temporario e confere que:
#   - o dump passa no checksum e restaura sem erro;
#   - as tabelas do banco em uso existem no restaurado;
#   - a versao do Alembic e a mesma.
# Grava o resultado (com as contagens por tabela) em $BACKUP_DIR/restauracoes.log
# e apaga o banco temporario. Sai com erro se alguma conferencia falhar.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
TESTE_DB="${BACKUP_TESTE_DB:-${PGDATABASE:?defina PGDATABASE}_teste_restauracao}"
LOG="$BACKUP_DIR/restauracoes.log"
dir_scripts=$(dirname "$0")

ultimo=$(ls -1t "$BACKUP_DIR"/diario/*.dump 2>/dev/null | head -n 1 || true)
if [ -z "$ultimo" ]; then
    echo "$(date -u +%FT%TZ) FALHA: nenhum backup em $BACKUP_DIR/diario" | tee -a "$LOG" >&2
    exit 1
fi

falhar() {
    echo "$(date -u +%FT%TZ) FALHA $(basename "$ultimo"): $1" | tee -a "$LOG" >&2
    dropdb --maintenance-db=postgres --if-exists "$TESTE_DB" || true
    exit 1
}

dropdb --maintenance-db=postgres --if-exists "$TESTE_DB"
sh "$dir_scripts/restaurar.sh" "$ultimo" "$TESTE_DB" || falhar "pg_restore"

tabelas_sql="SELECT table_name FROM information_schema.tables
             WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1"
origem=$(psql -tAc "$tabelas_sql")
restaurado=$(psql --dbname="$TESTE_DB" -tAc "$tabelas_sql")
[ -n "$restaurado" ] || falhar "nenhuma tabela restaurada"
for tabela in $origem; do
    echo "$restaurado" | grep -qx "$tabela" || falhar "tabela $tabela ausente no backup"
done

versao_sql="SELECT version_num FROM alembic_version"
[ "$(psql -tAc "$versao_sql")" = "$(psql --dbname="$TESTE_DB" -tAc "$versao_sql")" ] ||
    falhar "versao do Alembic diferente (backup anterior a uma migration?)"

contagens=""
for tabela in $restaurado; do
    n=$(psql --dbname="$TESTE_DB" -tAc "SELECT count(*) FROM \"$tabela\"")
    contagens="$contagens $tabela=$n"
done

dropdb --maintenance-db=postgres "$TESTE_DB"
echo "$(date -u +%FT%TZ) OK $(basename "$ultimo"):$contagens" | tee -a "$LOG"
