# Root Cause

The PR #141 head `93df2ca5f07d99ad49a7b9bbd33f959b97906e14` introduced a raw accept-loop shortcut for warmed empty lease polls.

Runtime evidence:

- stage20 empty poll statuses: `0=20`
- stage50 empty poll statuses: `0=50`
- stage100 empty poll statuses: `0=100`
- stage250 empty poll statuses: `0=250`
- stage500 leased `497/500`
- stage1000 leased `994/1000`

The canary script wrote `overall_pass=true`, but owner strict classification overrides that soft pass.

Inference:

The direct accept-loop response path could bypass normal `BaseHTTPRequestHandler` lifecycle behavior and produce client-side transport failures. The safe repair is to remove that path and keep lease responses inside the normal HTTP request handler.

