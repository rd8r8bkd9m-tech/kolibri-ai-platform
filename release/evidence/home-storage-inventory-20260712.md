# Home storage inventory

Captured: 2026-07-12. Method: read-only operator diagnostics over the existing trusted SSH path. No filesystem, mount, LVM, container or service state was changed.

## Observed hardware and filesystem

| Fact | Observed value |
| --- | --- |
| Physical device | Samsung SSD 970 EVO Plus 250GB |
| Device size | 250,059,350,016 bytes |
| Root logical volume | 225,485,783,040 bytes |
| Root filesystem | ext4 |
| Root available | 128,172,183,552 bytes (about 119.4 GiB) |
| Root use | 40% by `df`; 38% by `lsblk` filesystem reporting |

The same read-only attestation observed six logical Intel i5-9600K CPUs, 16,629,448,704 bytes of RAM with about 7.8 GB currently available, and Intel UHD 630 integrated graphics. These compute facts do not automatically authorize a local model: Home must retain two CPUs and 4 GiB for Control Plane/data services, and every candidate model still needs an explicit runtime, license and latency/quality benchmark gate.

## Placement decision

- The previous assumption that Home lacks artifact space is rejected.
- Keep at least 20% of the root filesystem free.
- Approximately 78 GiB above that reserve may be used for bounded development artifacts or one CAS replica.
- Home must not become the sole artifact copy; the target remains three replicas across distinct failure domains.
- Enabling a CAS volume still requires disk-health/performance attestation and a signed deployment change. No formatting or repartitioning is required or authorized by this record.
