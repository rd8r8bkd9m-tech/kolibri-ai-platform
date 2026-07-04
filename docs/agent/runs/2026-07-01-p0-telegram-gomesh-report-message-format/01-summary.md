# Summary

Task: `P0_TELEGRAM_GOMESH_REPORT_MESSAGE_FORMAT_2026_07_01`

Implemented owner-facing Telegram formatting for Kolibri GoMesh speed-gate/status reports.

The gateway now recognizes noisy GoMesh production report text from completed owner remote tasks and converts it into a concise Russian Telegram card with:

- status and verdict
- Home endpoint and health
- direct and GoMesh Mbps metrics
- 300+ Mbps target
- selector status
- pytest pass count
- rollback backup paths
- next action

The formatter avoids task ids, raw node metadata, stdout/stderr noise, token-like strings, unrelated internal paths, and false completed claims when the speed gate failed.
