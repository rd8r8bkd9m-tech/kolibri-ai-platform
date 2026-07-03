# Tests

Commands run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest tests/test_factory_status.py -q
```

Result:

```text
3 passed in 0.12s
```

Frontend build:

```bash
cd frontend
rm -rf node_modules package-lock.json
npx -y -p node@20 -c 'npm install && npm run build'
npx -y -p node@20 -c 'npm run build'
```

Result:

```text
vite v8.1.3 building client environment for production...
668 modules transformed.
dist/index.html
dist/assets/index-Dc7-c_M8.css
dist/assets/index-ct0f24BK.js
built successfully
```

Notes:

- The worker default Node is `v18.19.1`, which is below Vite 8's required `20.19+` / `22.12+`.
- A one-off Node `v20.20.2` runtime via `npx -p node@20` was used for the successful build.
- Vite reported a non-blocking chunk-size warning for the existing app bundle.
