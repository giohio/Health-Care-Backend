#!/bin/sh
set -e

PEM_FILE="/keys/kong_pubkey.pem"
KONG_YML="/kong.yml"
OUTPUT="/usr/local/kong/declarative/kong.yml"

if [ ! -f "$PEM_FILE" ]; then
  echo "ERROR: PEM file not found at $PEM_FILE"
  exit 1
fi

echo "Injecting RSA public key into Kong config..."

INDENTED_KEY=$(awk '{print "          " $0}' "$PEM_FILE")

mkdir -p "$(dirname "$OUTPUT")"
awk -v key="$INDENTED_KEY" '
/###RSA_PUBLIC_KEY###/ { print key; next }
{ print }
' "$KONG_YML" > "$OUTPUT"

echo "Kong config ready."
exec /docker-entrypoint.sh kong docker-start
