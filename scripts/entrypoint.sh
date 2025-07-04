#!/bin/sh
# Hata durumunda script'in hemen durmasını sağlar.
set -e

# Sır dosyalarının yollarını tanımla
POSTGRES_USER_FILE="/run/secrets/postgres_user"
POSTGRES_PASSWORD_FILE="/run/secrets/postgres_password"

# Dosyaların var olup olmadığını kontrol et
if [ -f "$POSTGRES_USER_FILE" ]; then
    export POSTGRES_USER=$(cat "$POSTGRES_USER_FILE")
else
    echo "PostgreSQL user secret not found!"
    exit 1
fi

if [ -f "$POSTGRES_PASSWORD_FILE" ]; then
    export POSTGRES_PASSWORD=$(cat "$POSTGRES_PASSWORD_FILE")
else
    echo "PostgreSQL password secret not found!"
    exit 1
fi

# DATABASE_URL'i oluştur ve export et.
# Diğer DB parametreleri (host, db_name) ortamdan gelir.
export DATABASE_URL="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_DB_PORT}/${POSTGRES_DB}"

echo "DATABASE_URL is set."
echo "Waiting for PostgreSQL to be ready..."

# 'wait-for-it.sh' script'ini kullanarak veritabanını bekle.
# Bu script, Dockerfile ile /usr/local/bin/ içine kopyalanmalı.
wait-for-it.sh "${POSTGRES_HOST}:${POSTGRES_DB_PORT}" -t 60 -- echo "PostgreSQL is up."

# Verilen asıl komutu (CMD) çalıştır.
# "$@" ifadesi, docker-compose'daki 'command' satırının tamamını alır.
echo "Starting application command: $@"
exec "$@"