#!/bin/sh
# Hata durumunda script'in hemen durmasını sağlar.
set -e

# --- DEĞİŞİKLİK BURADA BAŞLIYOR ---
# Eğer DATABASE_URL ortam değişkeni zaten dışarıdan ayarlanmışsa,
# sır dosyalarını okuma ve kendi URL'mizi oluşturma adımlarını atla.
if [ -z "$DATABASE_URL" ]; then
    echo "DATABASE_URL not set. Attempting to build from Docker secrets..."

    # Sır dosyalarının yollarını tanımla
    POSTGRES_USER_FILE="/run/secrets/postgres_user"
    POSTGRES_PASSWORD_FILE="/run/secrets/postgres_password"

    # Dosyaların var olup olmadığını kontrol et
    if [ -f "$POSTGRES_USER_FILE" ]; then
        export POSTGRES_USER=$(cat "$POSTGRES_USER_FILE")
    else
        echo "PostgreSQL user secret not found! Cannot build DATABASE_URL."
        if [ -n "$POSTGRES_HOST" ]; then
            exit 1
        fi
    fi

    if [ -f "$POSTGRES_PASSWORD_FILE" ]; then
        export POSTGRES_PASSWORD=$(cat "$POSTGRES_PASSWORD_FILE")
    else
        echo "PostgreSQL password secret not found! Cannot build DATABASE_URL."
        if [ -n "$POSTGRES_HOST" ]; then
            exit 1
        fi
    fi

    # DATABASE_URL'i oluştur ve export et.
    if [ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_PASSWORD" ] && [ -n "$POSTGRES_HOST" ]; then
        export DATABASE_URL="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_DB_PORT}/${POSTGRES_DB}"
        echo "DATABASE_URL constructed from secrets."
    else
        echo "Could not construct DATABASE_URL from secrets/env vars."
    fi
else
    echo "DATABASE_URL is already set. Skipping secret handling."
fi
# --- DEĞİŞİKLİK BURADA BİTİYOR ---

# Sadece POSTGRES_HOST ayarlıysa bekle.
if [ -n "$POSTGRES_HOST" ]; then
    echo "Waiting for PostgreSQL to be ready at ${POSTGRES_HOST}:${POSTGRES_DB_PORT}..."
    wait-for-it.sh "${POSTGRES_HOST}:${POSTGRES_DB_PORT}" -t 60 -- echo "PostgreSQL is up."
fi

# Verilen asıl komutu (CMD) çalıştır.
echo "Starting application command: $@"
exec "$@"