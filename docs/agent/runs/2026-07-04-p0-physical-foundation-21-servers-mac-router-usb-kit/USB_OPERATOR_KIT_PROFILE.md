# USB_OPERATOR_KIT_PROFILE.md

**Date:** 2026-07-04T22:20:00Z

## Profile

```json
{
  "node_id": "usb-operator-kit",
  "class": "operator_kit",
  "role": "emergency_recovery_package",
  "physical_asset": true,
  "contains": [
    "README_START_HERE.md",
    "OFFLINE_RECOVERY_RUNBOOK.md",
    "SERVER_21_CANONICAL_TABLE.md",
    "SSH_ACCESS_MATRIX.md",
    "CONTROL_PLANE_URLS.md",
    "GITHUB_RECOVERY.md",
    "HOME_NOC_RECOVERY.md",
    "ROUTER_RECOVERY_NOTES.md",
    "PUBLIC_KEYS/",
    "CHECKSUMS.sha256",
    "NO_PRIVATE_KEYS_HERE.txt"
  ],
  "private_keys": "NO (unless owner approves encrypted storage)",
  "role_purpose": "restore command access when Mac/Home unavailable"
}
```

## Rules
- Public keys only unless owner approves encrypted backup
- One-time recovery token procedure
- Printed/offline runbook recommended
- Help recover if Mac/Home unavailable
