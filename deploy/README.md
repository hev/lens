# Deployment

The public UI is a Cloudflare Worker; this bundle contains the CPU-only batch
indexer and the declarative Layer source/store/index records. Image embedding
does not happen in the indexer pod. It sends image URLs to the public gateway,
where `LocalClipEmbeddingProvider` fetches, decodes, preprocesses, and embeds
them in-process on the gateway's CPU.

## Gateway CLIP artifact

The shared gateway loads the Hugging Face safetensors conversion of
`openai/clip-vit-base-patch32`, pinned to immutable revision
`b33cedfd0df4e43b8238760678fcc89e1a0d38b3`. The four files are staged at:

```text
s3://hevlayer-turbopuffer-bench-186219257916-us-east-1/artifacts/models/openai/clip-vit-base-patch32/b33cedfd0df4e43b8238760678fcc89e1a0d38b3
```

Layer's Helm chart downloads them into an `emptyDir`, verifies every checksum,
mounts the directory read-only, and sets `LAYER_LOCAL_CLIP_MODEL_PATH`:

```text
model.safetensors         99d28a652e6ec46629ab7047a0ac82c69b1fe11e0ce672c43af65d3a9a3fc05d
tokenizer.json            b556ac8c99757ffb677208af34bc8c6721572114111a6e0aaf5fa69ff0b8d842
config.json               b575ef3c36f2a057fa19e221650105052d61cc9c1a972ec15019c6261ec98770
preprocessor_config.json  910e70b3956ac9879ebc90b22fb3bc8a75b6a0677814500101a4c072bd7857bd
```

The chart path and render guard are in `hev/layer-pro#477`. No model file or
dataset is committed here.

The verified live Helm revision 79 uses gateway image digest
`sha256:f55e76b3455e6dd07824d8cf5f5c66bec07205eb1e0c13ba128183c0da720177`
from the mesh-account ECR. The gateway pod runs on an `i4i.xlarge` CPU system
node with no GPU allocatable resource.

## Indexer image

Build and push only to the mesh-account ECR, using Depot:

```sh
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin 186219257916.dkr.ecr.us-east-1.amazonaws.com
DEPOT_DISABLE_OTEL=1 depot build --project 8zfcn2cf80 --platform linux/amd64,linux/arm64 \
  -f Dockerfile.indexer \
  -t 186219257916.dkr.ecr.us-east-1.amazonaws.com/hev-lens-indexer:v0.1.2 \
  --push .
```

There is intentionally no `ghcr.io/hev/*` image.

The live Job is pinned to the multi-architecture manifest digest produced by
that build:

```text
186219257916.dkr.ecr.us-east-1.amazonaws.com/hev-lens-indexer@sha256:6b857b975b948741de1ef575bc45a13f514e888968359446869a48cdd457145f
```

## Apply and run

Create the credential without committing it, then apply the records and Job:

```sh
kubectl apply -f deploy/namespace.yaml
kubectl -n lens create secret generic lens-turbopuffer \
  --from-literal=credential="$LAYER_GATEWAY_API_KEY"
kubectl apply -f deploy/vectorstore.yaml -f deploy/warehouse.yaml
kubectl apply -f deploy/index.yaml
kubectl apply -f deploy/indexer-job.yaml
kubectl logs -n lens -l app.kubernetes.io/component=indexer -f
```

The Job requests ordinary CPU and no GPU resource. It writes one image at a
time at a sub-one-request-per-second steady cadence, and applies bounded
exponential retry when the gateway reports an upstream Wikimedia 429 (tracked
in `hev/layer-pro#481`). Its
final JSON summary states
`"embedding": "gateway LocalClipEmbeddingProvider on CPU"` and
`"gpu_workers": 0`. Stable Commons page IDs make a clean Job retry idempotent.
