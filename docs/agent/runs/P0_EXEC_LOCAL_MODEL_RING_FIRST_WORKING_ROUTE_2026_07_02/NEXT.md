# Next

Next exact task:

Deploy one scoped local model runtime and canary Fabric model listing:

```bash
docker run -d --name kolibri-ollama -p 127.0.0.1:11434:11434 -v kolibri-ollama:/root/.ollama ollama/ollama:latest && docker exec kolibri-ollama ollama pull qwen2.5:0.5b
curl --noproxy '*' -sS http://127.0.0.1:11434/api/tags
curl --noproxy '*' -sS http://10.99.0.10:9101/v1/models
```

Expected success signal:

- `/api/tags` returns at least one model.
- Fabric `/v1/models` returns `first_working_route.provider == "ollama"`.
- Fabric `/v1/models` includes the pulled model in `data.data`.

Rollback:

```bash
docker rm -f kolibri-ollama
```
