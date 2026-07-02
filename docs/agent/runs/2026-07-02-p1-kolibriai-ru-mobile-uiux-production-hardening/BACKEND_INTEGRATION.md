# Backend Integration

## Existing Integration

The frontend continues using the existing estimates API integration. No backend files were modified in this repair.

## Health Fallback

The authored frontend change improves API state detection:

- first attempts `health.v1()`;
- if that fails, attempts `estimates.list({ page_size: 1 })`;
- marks the API online if the estimates endpoint is reachable.

## Result

Backend integration remains unchanged at the API contract level. The frontend now handles environments where the estimates API is reachable but the health probe is not.
