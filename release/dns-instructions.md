# DNS Configuration for kolibriai.ru

## Overview
Configure DNS records in REG.RU to point kolibriai.ru to GitHub Pages and api.kolibriai.ru to the backend VPS.

## DNS Records to Add

### A Records (GitHub Pages apex)
| Type | Host | Value | TTL | Purpose |
|------|------|-------|-----|---------|
| A | @ | 185.199.108.153 | 3600 | GitHub Pages |
| A | @ | 185.199.109.153 | 3600 | GitHub Pages |
| A | @ | 185.199.110.153 | 3600 | GitHub Pages |
| A | @ | 185.199.111.153 | 3600 | GitHub Pages |

### CNAME Record (www subdomain)
| Type | Host | Value | TTL | Purpose |
|------|------|-------|-----|---------|
| CNAME | www | rd8r8bkd9m-tech.github.io | 3600 | www alias to GitHub Pages |

### A Record (API backend)
| Type | Host | Value | TTL | Purpose |
|------|------|-------|-----|---------|
| A | api | <production-vps-ip> | 3600 | Kolibri backend API |

## Notes
- Replace `<production-vps-ip>` with the actual VPS IP address
- Do not modify MX/TXT/SPF/DKIM records
- After changes, save DNS records to dns-after.txt
