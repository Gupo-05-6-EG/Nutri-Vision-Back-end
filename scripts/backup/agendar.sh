#!/bin/sh
# Entrypoint do servico `backup` do docker-compose (Task 7.2, RNF10).
#
# Agenda no crond do Alpine o backup diario (BACKUP_CRON, padrao 03:00) e o
# teste de restauracao semanal (BACKUP_TESTE_CRON, padrao domingo 03:30). Os
# horarios seguem o TZ do container.
set -eu

CRON_BACKUP="${BACKUP_CRON:-0 3 * * *}"
CRON_TESTE="${BACKUP_TESTE_CRON:-30 3 * * 0}"
dir_scripts=$(cd "$(dirname "$0")" && pwd)

# O crond nao repassa o ambiente do container para os jobs: salva o que eles usam.
env | grep -E '^(PG|BACKUP_|TZ=)' | sed "s/'/'\\\\''/g; s/=\(.*\)/='\1'/; s/^/export /" >/etc/backup.env

cat >/etc/crontabs/root <<EOF
$CRON_BACKUP . /etc/backup.env && sh $dir_scripts/backup.sh >/proc/1/fd/1 2>&1
$CRON_TESTE . /etc/backup.env && sh $dir_scripts/testar_restauracao.sh >/proc/1/fd/1 2>&1
EOF

echo "[agendar] backup: '$CRON_BACKUP' | teste de restauracao: '$CRON_TESTE'"
if [ "${BACKUP_NA_INICIALIZACAO:-false}" = true ]; then
    sh "$dir_scripts/backup.sh"
fi
exec crond -f -l 8
