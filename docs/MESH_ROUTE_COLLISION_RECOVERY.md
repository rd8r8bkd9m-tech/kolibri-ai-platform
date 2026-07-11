# Guarded mesh route-collision recovery

Status: reusable operator recovery contract.

## Proven failure

This procedure handles a node where `wg-quick@wg-kolibri` cannot start because
a legacy WireGuard `AllowedIPs` token overlaps a route already owned by a
different live interface. The affected node, conflicting CIDR, and current
route-owner interface are explicit operator inputs.

This repair is deliberately separate from the peer-persistence rollout. It
does not install runtime files, alter the current route owner, change Mac routes, or
touch `utun6`.

## Guard conditions

`scripts/repair-mesh-route-collision.sh` refuses apply unless:

1. the selected node exists exactly once in the 21-member manifest;
2. external SSH succeeds directly or through Home;
3. the explicitly named route-owner interface is up and owns the conflicting route;
4. `wg-kolibri` is inactive;
5. the WireGuard configuration is a regular non-symlink file;
6. exactly one `AllowedIPs` token equals the explicit CIDR;
7. that line retains at least one other AllowedIP after removal.

The patch is an atomic same-directory replacement. It removes only that exact
token. It never deletes or replaces the live route.

## Commands

Read-only proof:

```bash
scripts/repair-mesh-route-collision.sh \
  --manifest /path/to/peers.json \
  --node NODE \
  --conflict-cidr CONFLICTING_CIDR \
  --route-owner CURRENT_INTERFACE
```

Owner-gated apply:

```bash
scripts/repair-mesh-route-collision.sh \
  --manifest /path/to/peers.json \
  --node NODE \
  --conflict-cidr CONFLICTING_CIDR \
  --route-owner CURRENT_INTERFACE \
  --apply
```

The node name is an operator argument; the script resolves both mesh and
external addresses from the manifest.

## Verification and rollback

Apply starts `wg-quick@wg-kolibri`, confirms that the named interface still owns the
LAN route, waits for a fresh Home handshake, and requires Mac and Home SSH to
the restored mesh address.

Before editing, the original configuration, checksum, route evidence and unit
state are stored under:

```text
/var/backups/kolibri/mesh-route-collision/<run-id>/<node-id>/
```

Any failed gate stops the newly started mesh interface, restores the exact
checksum-verified configuration, and confirms that the pre-existing
pre-existing route is still present.
