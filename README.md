# Lens × Layer local CLIP

```json
"image_url": {"type": "string", "embed": {"model": "openai/clip-vit-base-patch32", "modality": "image",
  "serving": {"prefer": "local"}}}
```

A public text-to-image search demo over Wikimedia Commons Quality images. The
gateway fetches each image, runs CLIP's image tower in-process on CPU, and stores
the resulting vector. At query time the same gateway runs CLIP's text tower and
searches that image column. The app posts writes and queries and renders the
echo; it contains no embedding or image-preprocessing code.

Live: **https://lens.hevlayer.com**

## What is visible

Every response pairs the fixed serving contract (`prefer: local`, image schema,
`openai/clip-vit-base-patch32`, 512 dimensions) with the gateway's live
`performance.embedding_ms` echo. The UI labels this `local CLIP · gateway CPU`.
There is no pool, GPU worker, autoscaler, or Turbopuffer-native embedding leg in
the write or query path.

## Verified deployment

On 2026-08-11 the digest-pinned Kubernetes indexer completed 2,500 Commons
images across 54 source pages. Its final summary reported
`embedding: gateway LocalClipEmbeddingProvider on CPU` and `gpu_workers: 0`;
the pod selected the cluster's CPU worker pool and declared no GPU resource.
An uncached public `sunset over water` query returned a sunset first and echoed
the fixed local 512d text→image contract plus gateway embedding time.

## Corpus and license

The corpus is a deterministic slice of Wikimedia Commons'
[Quality images](https://commons.wikimedia.org/wiki/Commons:Quality_images)
category. Commons accepts only freely licensed or public-domain media, and the
indexer further keeps only Creative Commons BY, BY-SA, CC0, and public-domain
files. Each result carries its source page, creator, exact license name, and
license URL so attribution travels with the image. See Wikimedia Commons'
[reuse guide](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia)
for the per-file terms.

The indexer requests 640-pixel thumbnails from the public MediaWiki API. The
thumbnail URL is the schema value Layer embeds and the browser displays; no
dataset or image binary is checked into this repository.

## Run

```sh
cp .env.example .env
# Fill LAYER_GATEWAY_API_KEY from 1Password; never commit it.
uv sync

# Small disposable smoke. Use a lens-scratch-* namespace for live tests.
uv run python -m indexer --namespace lens-scratch-yourname --limit 24 --reset-state

# Reference backend + the same UI production serves.
uv run uvicorn search.app:app --host 127.0.0.1 --port 8000
```

For the live corpus, run `uv run python -m indexer --limit 2500 --reset-state`.
Stable Commons page IDs make rewrites idempotent. The checkpoint under `.state/`
stores the MediaWiki continuation token only after a complete API page is
written, so an interrupted page is safely replayed.

## Production

`src/worker.js` is the production backend. It injects `LAYER_API_KEY`
server-side and serves `web/static/` through Cloudflare assets.

```sh
cp .dev.vars.example .dev.vars
npm install
npm test
npx wrangler dev
npx wrangler secret put LAYER_API_KEY
npx wrangler deploy
```

Both backends send the same query directly to Layer:

```json
{
  "rank_by": ["image_url", "ANN", ["Embed", "sunset over water"]],
  "top_k": 16
}
```

There is no client-side image fetch, embedding model, tokenizer, query vector,
fusion, or reranker. Model weights land on the gateway through the checksum-
pinned Helm path documented in `deploy/README.md`.
