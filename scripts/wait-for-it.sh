#!/bin/sh
# wait-for-it.sh: Wait for a service to be available before executing a command.
# Kullanım: wait-for-it.sh host:port [-t timeout] -- command args
# Örnek: wait-for-it.sh postgres:5432 -t 30 -- uvicorn main:app

set -e

HOST=$(echo $1 | cut -d : -f 1)
PORT=$(echo $1 | cut -d : -f 2)
shift

TIMEOUT=15
while getopts "t:" opt; do
  case "$opt" in
    t) TIMEOUT="$OPTARG" ;;
    *) ;;
  esac
done
shift $((OPTIND - 1))

# Komutu sakla
CMD="$@"

echo "Waiting for $HOST:$PORT..."

# Python'un standart kütüphanesi ile portu kontrol et. 'nc'ye gerek yok.
WAIT_COMMAND="
import socket
import sys
import time
host = '${HOST}'
port = int('${PORT}')
timeout = ${TIMEOUT}
start_time = time.time()
while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            break
    except OSError as ex:
        if time.time() - start_time >= timeout:
            print(f'Timed out after {timeout} seconds waiting for {host}:{port}')
            sys.exit(1)
        time.sleep(0.5)
"

# Python komutunu çalıştır
python3 -c "$WAIT_COMMAND"

echo "$HOST:$PORT is up - executing command: $CMD"
exec $CMD