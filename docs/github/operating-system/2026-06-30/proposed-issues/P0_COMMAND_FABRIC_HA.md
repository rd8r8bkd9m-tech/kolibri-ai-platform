# P0 Command Fabric HA and Any-Node Control

## Context

Mac is a command center, but control should work from any trusted command node through Fabric API and fallback routing.

## Scope

- Any-node API access.
- Fallback relay routes.
- Owner command envelope.
- Home visual monitor alignment.

## Acceptance

- Any command node can query fleet state through API.
- Failed direct route produces structured repair task.
- SSH remains bootstrap/emergency/diagnostic only.

## Forbidden

- No bypass of authentication.
- No eternal shared key.
