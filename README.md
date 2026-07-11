# Vista OS

**Vista OS** is a single-window AI operating workspace for real business workflows. The first production vertical is construction estimates: project brief → editable estimate → verified PDF/XLSX/DOCX/JSON documents → secure client delivery.

- [Русская документация](README.ru.md)
- [English documentation](README.en.md)
- [Architecture](docs/architecture/VISTA_OS_11_ARCHITECTURE.md)
- [Product API](docs/api/PRODUCT_API.md)
- [OpenAI-compatible gateway](docs/api/OPENAI_COMPATIBILITY.md)
- [Release evidence](docs/release/VISTA_OS_11_1_PRODUCT_RELEASE.ru.md)
- [Build report](docs/release/VISTA_OS_11_1_BUILD_REPORT.md)
- [Production deployment](docs/deploy/PRODUCTION_DEPLOYMENT.ru.md)

## One-command local start

```bash
./scripts/dev-fone.sh
```

Frontend: `http://127.0.0.1:5173`  
API: `http://127.0.0.1:8000/api/health`

## Release verification

```bash
./scripts/validate-fone.sh
./scripts/release-check.sh
```

## Production deployment

```bash
cp .env.example .env
# Replace every secret and origin in .env
docker compose up --build -d
```

Vista never uses demo API fallbacks in production. If the Core API is unavailable, the shell reports the failure instead of showing invented data.
