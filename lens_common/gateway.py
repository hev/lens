from __future__ import annotations

import time
from typing import Any

import httpx

MODEL = "openai/clip-vit-base-patch32"
DIMS = 512
SERVING = "local"
IMAGE_FIELD = "image_url"
INCLUDE_ATTRIBUTES = [
    "title",
    "description",
    "image_url",
    "source_url",
    "artist",
    "license_name",
    "license_url",
    "width",
    "height",
]


def embedding_schema() -> dict[str, Any]:
    """Layer fetches and embeds image_url; the app stores no client vector."""
    return {
        IMAGE_FIELD: {
            "type": "string",
            "embed": {
                "model": MODEL,
                "dims": DIMS,
                "modality": "image",
                "serving": {"prefer": SERVING},
            },
        },
        "title": {"type": "string"},
        "description": {"type": "string"},
        "source_url": {"type": "string"},
        "artist": {"type": "string"},
        "license_name": {"type": "string"},
        "license_url": {"type": "string"},
        "width": {"type": "int"},
        "height": {"type": "int"},
    }


def search_body(query: str, top_k: int) -> dict[str, Any]:
    return {
        "rank_by": [IMAGE_FIELD, "ANN", ["Embed", query]],
        "top_k": max(1, min(top_k, 30)),
        "include_attributes": INCLUDE_ATTRIBUTES,
    }


def serving_contract() -> dict[str, Any]:
    return {
        "prefer": SERVING,
        "model": MODEL,
        "dims": DIMS,
        "write_modality": "image",
        "query_modality": "text",
        "compute": "gateway-in-process-cpu",
    }


async def search_gateway(
    client: httpx.AsyncClient,
    *,
    gateway_url: str,
    api_key: str,
    namespace: str,
    query: str,
    top_k: int,
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("LAYER_GATEWAY_API_KEY is not configured")
    started = time.perf_counter()
    response = await client.post(
        f"{gateway_url.rstrip('/')}/v2/namespaces/{namespace}/query",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "x-hevlayer-search-query": query,
            "x-hevlayer-tags": "app:lens,serving:local-clip,search:cross-modal",
        },
        json=search_body(query, top_k),
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    if response.is_error:
        detail = response.text[:1000]
        raise httpx.HTTPStatusError(detail, request=response.request, response=response)
    upstream = response.json()
    return {
        "query": query,
        "rows": upstream.get("rows", []),
        "performance": upstream.get("performance", {}),
        "billing": upstream.get("billing"),
        "serving": serving_contract(),
        "took_ms": elapsed_ms,
    }


async def stats_gateway(
    client: httpx.AsyncClient,
    *,
    gateway_url: str,
    api_key: str,
    namespace: str,
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("LAYER_GATEWAY_API_KEY is not configured")
    response = await client.get(
        f"{gateway_url.rstrip('/')}/v1/namespaces/{namespace}/metadata",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if response.is_error:
        detail = response.text[:1000]
        raise httpx.HTTPStatusError(detail, request=response.request, response=response)
    upstream = response.json()
    return {
        "approx_row_count": upstream.get("approx_row_count"),
        "approx_logical_bytes": upstream.get("approx_logical_bytes"),
        "updated_at": upstream.get("updated_at"),
    }
