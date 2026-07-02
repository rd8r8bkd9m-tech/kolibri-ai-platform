# Tests

Commands run:

```bash
python3 -m py_compile ops/factory_control.py tests/test_prompt3_fabric_api_surface.py tests/test_fabric_control.py
```

Result: pass.

```bash
python3 -m pytest -q tests/test_prompt3_fabric_api_surface.py tests/test_fabric_control.py
```

Result: pass, `13 passed in 0.11s`.

Live discovery invocation:

```bash
python3 - <<'PY'
import importlib.util, json
from pathlib import Path
spec = importlib.util.spec_from_file_location('factory_control', Path('ops/factory_control.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
catalog = module.fabric_model_catalog()
print(json.dumps({
    'first_working_route': catalog['first_working_route'],
    'model_ids': [model['id'] for model in catalog['data']],
    'route_statuses': [
        {
            'provider': route['provider'],
            'base_url': route['base_url'],
            'status': route['status'],
            'model_count': len(route.get('models') or []),
            'error': route.get('error', ''),
        }
        for route in catalog['local_model_route_inventory']
    ],
    'repair_task': catalog['repair_task'],
}, indent=2, sort_keys=True))
PY
```

Result:

- `first_working_route`: `null`
- `model_ids`: `["mimo-auto"]`
- Ollama `127.0.0.1:11434`: blocked, `URLError`
- vLLM `127.0.0.1:8000`: blocked, `HTTPError`
- LiteLLM `127.0.0.1:4000`: blocked, `URLError`
- OpenAI-compatible `127.0.0.1:8080`: blocked, `URLError`
