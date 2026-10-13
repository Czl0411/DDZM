#!/bin/sh
set -eu

[ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/chess-ip ] || exit 0

install -o root -g caddy -m 0644 "$RENEWED_LINEAGE/fullchain.pem" /etc/caddy/certs/chess-ip.crt
install -o root -g caddy -m 0640 "$RENEWED_LINEAGE/privkey.pem" /etc/caddy/certs/chess-ip.key
systemctl reload caddy
