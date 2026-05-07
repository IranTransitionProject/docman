Run the test suite (no infrastructure required):

```bash
uv run pytest tests/ -v
```

To test with live infrastructure (NATS + Heddle router):
```bash
docker run -p 4222:4222 nats:latest
uv run heddle router --nats-url nats://localhost:4222
uv run heddle processor --config configs/workers/doc_extractor.yaml --nats-url nats://localhost:4222
uv run heddle pipeline --config configs/orchestrators/doc_pipeline_smart.yaml --nats-url nats://localhost:4222
```
