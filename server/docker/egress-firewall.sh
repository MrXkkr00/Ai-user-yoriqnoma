#!/bin/sh
# Egress rules of the worker (TZ SEC-10): run on the host as root after `docker compose up`
# and after every reboot (e.g. from a systemd unit, see docs/DEPLOY.md).
#
# The worker reaches the internet only through the "egress" network (172.30.0.0/24).
# Traffic from that network to private, loopback, link-local (cloud metadata) and other
# special ranges is dropped in the DOCKER-USER chain, so even a page that tricks the
# browser (DNS rebinding, a redirect, an <img> to 169.254.169.254) cannot reach the
# server's own network. The worker still talks to postgres, redis, minio and mailpit
# over the separate "internal" network, which these rules do not touch.
set -eu

EGRESS_SUBNET="${EGRESS_SUBNET:-172.30.0.0/24}"
BLOCKED="0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 \
192.168.0.0/16 224.0.0.0/4 240.0.0.0/4"

for net in $BLOCKED; do
    iptables -C DOCKER-USER -s "$EGRESS_SUBNET" -d "$net" -j DROP 2>/dev/null \
        || iptables -I DOCKER-USER -s "$EGRESS_SUBNET" -d "$net" -j DROP
done
# DNS to the outside resolver must still work (Docker's embedded DNS answers inside).
echo "egress rules for $EGRESS_SUBNET are in place"

if command -v ip6tables >/dev/null 2>&1; then
    for net in ::1/128 fc00::/7 fe80::/10 ff00::/8; do
        ip6tables -C DOCKER-USER -d "$net" -j DROP 2>/dev/null \
            || ip6tables -I DOCKER-USER -d "$net" -j DROP 2>/dev/null || true
    done
fi
