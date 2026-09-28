# lens

A public demo on hev layer: text-to-image search over Wikimedia Commons
Quality images at `lens.hevlayer.com`. The headline is Layer's in-process CPU
CLIP (`openai/clip-vit-base-patch32`, 512d, `serving.prefer: local`). The
gateway fetches each image URL and embeds it with CLIP's image tower on write,
embeds the query text with the text tower at query time, and echoes
`performance.embedding_ms`. The design of record is RFC 0110 in
`../layer-pro/docs/rfcs/`. `README.md` is the public tour; `deploy/README.md`
is the cluster run book.

**This repo is public.** Never put client names, client systems or anything
from a client engagement in code, comments, docs or commit messages.

## You are a Layer customer

lens exists to use Layer the way a customer would and to report what it
hits. The demo working is table stakes; the report is the deliverable.

- **Reimplement nothing Layer owns:** image fetch and preprocessing for
  embedding, query embedding, tokenization, fusion, reranking. Both backends
  send the same `["image_url", "ANN", ["Embed", "<text>"]]` query and render
  the echo. If you're writing a tokenizer or resizing images, the boundary
  is wrong.
- **Read the docs, don't invent API.** The request and response shapes are in
  `../layer-pro/site/src/content/docs/` (local CLIP: `api/embed.mdx`, public
  at https://hevlayer.com/docs/api/embed/) and
  `../layer-pro/apps/layer-gateway/openapi.yaml`.
- **Report friction in Linear** (team LYR, hevmind workspace, via the
  `linear` CLI): a bug or a wrong or missing doc is an issue; a missing
  capability is an RFC, written as an `RFC: <name>` document on a Linear
  project with this workload as the motivating case. New RFCs are not files
  in `../layer-pro/docs/rfcs/` and are not numbered.
- **Layer operates itself.** Don't hand-tune scaling. If you must intervene
  to keep the demo up, the intervention gets an issue too.

## Run and test

```sh
uv sync
uv run pytest                  # Python: gateway client, indexer
npm install
npm test                       # Worker: node --test tests/worker.test.js
export LAYER_GATEWAY_API_KEY="$(op read op://mesh-staging/layer-turbopuffer/credential)"
uv run uvicorn search.app:app --host 127.0.0.1 --port 8000   # FastAPI dev backend
uv run python -m indexer --namespace lens-scratch-yourname --limit 24 --reset-state
```

The gateway key comes from 1Password (`op://mesh-staging/layer-turbopuffer/credential`)
at run time. Never write it to a `.env` or `.dev.vars` file or print it.
Settings are `LAYER_`-prefixed env vars (`lens_common/config.py`):
`LAYER_GATEWAY_URL`, `LAYER_GATEWAY_API_KEY`, `LAYER_NAMESPACE` (default
`lens-commons-quality`), `LAYER_TIMEOUT_SECONDS`. The Worker reads the same
key as `LAYER_API_KEY`.

- The live namespace is `lens-commons-quality`. Disposable checks use
  `lens-scratch-*` and delete it afterward.
- The indexer checkpoint lives in `.state/` and records the MediaWiki
  continuation token only after a whole API page is written; `--reset-state`
  starts over. Stable Commons page IDs make rewrites idempotent.
- Writes go one image at a time with a pause between them
  (`--write-delay-seconds`, default 0.5) and bounded exponential retry when
  the gateway reports an upstream Wikimedia 429. Don't remove the pacing.

## Deploy

- **Web (prod):** a Cloudflare Worker (`src/worker.js`, `wrangler.jsonc`)
  serving `web/static/`, on the `lens.hevlayer.com` custom domain. There is
  no CI; deploy by hand with `npx wrangler deploy` and set the key with
  `op read op://mesh-staging/layer-turbopuffer/credential | npx wrangler secret put LAYER_API_KEY`.
  For local Worker dev pass it as `npx wrangler dev --var LAYER_API_KEY:"$(op read …)"`.
  Keep `src/worker.js` and the FastAPI dev backend (`search/`) in lockstep.
- **Cluster:** namespace `lens` on `layer-prod`. `deploy/` is the declarative
  bundle (VectorStore, Warehouse, Index, the CPU-only indexer Job, secret
  `lens-turbopuffer`); see `deploy/README.md` for apply order. The gateway's
  CLIP weights come from the checksum-pinned Helm path documented there.
- **Images** go to the mesh-account ECR (`hev-lens-indexer`, built with
  Depot), never `ghcr.io`; a test enforces it.

## State (2026-09-27)

`lens-commons-quality` holds 2,500 images (`/api/stats`, last write
2026-08-11). The `lens-indexer` Job in namespace `lens` is Complete and
nothing is running. `lens.hevlayer.com` serves, and `/api/config` reports
`compute: gateway-in-process-cpu`. To grow the corpus, run the indexer with a
higher `--limit`.
