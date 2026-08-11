# lens contributor guide

This repository is a Layer design-preview customer. It posts native request
shapes to the gateway and renders the gateway echo. Do not add client-side
embedding, image preprocessing, retrieval fusion, tokenization, or reranking.

Read request and response shapes from `../layer-pro/site/src/content/docs/`
and `../layer-pro/apps/layer-gateway/openapi.yaml`. Gateway/API friction becomes
a GitHub issue on `hev/layer-pro`; engine friction becomes an issue on
`hev/search`.

## Local verification

```sh
uv sync
uv run pytest
npm install
npm test
uv run uvicorn search.app:app --host 127.0.0.1 --port 8000
```

Secrets belong only in gitignored `.env` and `.dev.vars`. The live namespace is
`lens-commons-quality`; disposable checks must use `lens-scratch-*` and delete
them afterward.

Every container image built for this repo goes to the mesh-account ECR with
Depot. A `ghcr.io/hev/*` image is never valid.
