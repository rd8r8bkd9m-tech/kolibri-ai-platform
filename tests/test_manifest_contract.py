import json
from pathlib import Path

def test_manifest_components_reference_existing_capabilities_and_intents():
    manifest = json.loads(Path('configs/fone-os/manifest.json').read_text(encoding='utf-8'))
    caps = set(manifest['capabilities'])
    intents = set(manifest['intents'])
    for component in manifest['components'].values():
        assert set(component['required']).issubset(caps)
        assert set(component['intents']).issubset(intents | {'*'})

def test_client_role_has_no_server_grants():
    manifest = json.loads(Path('configs/fone-os/manifest.json').read_text(encoding='utf-8'))
    grants = set(manifest['roles']['client']['grants'])
    assert 'server.metrics.read' not in grants
    assert 'factory.task.execute' not in grants
