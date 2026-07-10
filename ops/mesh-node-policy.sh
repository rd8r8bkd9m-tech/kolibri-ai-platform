#!/bin/sh
set -eu
MESH_IF="${KOLIBRI_MESH_IF:-wg-kolibri}"
UPLINK_IF="${KOLIBRI_UPLINK_IF:-eth0}"
add() { iptables -w "$@" -C 2>/dev/null || iptables -w "$@"; }
apply() {
  sysctl -w net.ipv4.ip_forward=1 >/dev/null
  add -I FORWARD 1 -i "$MESH_IF" -o "$MESH_IF" -m comment --comment Kolibri-mesh-east-west -j ACCEPT
  add -I FORWARD 1 -i "$MESH_IF" -o "$UPLINK_IF" -m comment --comment Kolibri-mesh-to-uplink -j ACCEPT
  add -I FORWARD 1 -i "$UPLINK_IF" -o "$MESH_IF" -m conntrack --ctstate RELATED,ESTABLISHED -m comment --comment Kolibri-uplink-to-mesh-return -j ACCEPT
  add -I INPUT 1 -i "$MESH_IF" -p tcp --dport 9291 -m comment --comment Kolibri-mesh-registry -j ACCEPT
}
remove() {
  while iptables -w -C FORWARD -i "$MESH_IF" -o "$MESH_IF" -m comment --comment Kolibri-mesh-east-west -j ACCEPT 2>/dev/null; do iptables -w -D FORWARD -i "$MESH_IF" -o "$MESH_IF" -m comment --comment Kolibri-mesh-east-west -j ACCEPT; done
  while iptables -w -C FORWARD -i "$MESH_IF" -o "$UPLINK_IF" -m comment --comment Kolibri-mesh-to-uplink -j ACCEPT 2>/dev/null; do iptables -w -D FORWARD -i "$MESH_IF" -o "$UPLINK_IF" -m comment --comment Kolibri-mesh-to-uplink -j ACCEPT; done
  while iptables -w -C FORWARD -i "$UPLINK_IF" -o "$MESH_IF" -m conntrack --ctstate RELATED,ESTABLISHED -m comment --comment Kolibri-uplink-to-mesh-return -j ACCEPT 2>/dev/null; do iptables -w -D FORWARD -i "$UPLINK_IF" -o "$MESH_IF" -m conntrack --ctstate RELATED,ESTABLISHED -m comment --comment Kolibri-uplink-to-mesh-return -j ACCEPT; done
  while iptables -w -C INPUT -i "$MESH_IF" -p tcp --dport 9291 -m comment --comment Kolibri-mesh-registry -j ACCEPT 2>/dev/null; do iptables -w -D INPUT -i "$MESH_IF" -p tcp --dport 9291 -m comment --comment Kolibri-mesh-registry -j ACCEPT; done
}
case "${1:-apply}" in apply) apply ;; remove) remove ;; *) exit 2 ;; esac
