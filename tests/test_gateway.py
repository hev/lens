import json

import httpx
import pytest
import respx

from lens_common.gateway import (
    DIMS,
    MODEL,
    embedding_schema,
    search_body,
    search_gateway,
    serving_contract,
    stats_gateway,
)


def test_embedding_schema_is_local_clip_image_contract():
    embed = embedding_schema()["image_url"]["embed"]
    assert embed == {
        "model": MODEL,
        "dims": DIMS,
        "modality": "image",
        "serving": {"prefer": "local"},
    }


def test_search_uses_one_inline_text_embed_against_image_field():
    body = search_body("sunset over water", 999)
    assert body["rank_by"] == ["image_url", "ANN", ["Embed", "sunset over water"]]
    assert body["top_k"] == 30
    serialized = json.dumps(body)
    assert "vector" not in serialized
    assert "model" not in serialized


def test_serving_contract_names_gateway_cpu_path():
    assert serving_contract() == {
        "prefer": "local",
        "model": MODEL,
        "dims": 512,
        "write_modality": "image",
        "query_modality": "text",
        "compute": "gateway-in-process-cpu",
    }


@pytest.mark.asyncio
@respx.mock
async def test_gateway_performance_echo_is_preserved():
    route = respx.post("https://gateway.test/v2/namespaces/lens/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [{"id": "commons-1", "title": "Sunset"}],
                "performance": {"embedding_ms": 7.25, "embedding_tokens": 4},
                "billing": None,
            },
        )
    )
    async with httpx.AsyncClient() as client:
        result = await search_gateway(
            client,
            gateway_url="https://gateway.test",
            api_key="secret",
            namespace="lens",
            query="sunset",
            top_k=5,
        )
    assert route.call_count == 1
    request = json.loads(route.calls[0].request.content)
    assert request["rank_by"] == ["image_url", "ANN", ["Embed", "sunset"]]
    assert result["performance"] == {"embedding_ms": 7.25, "embedding_tokens": 4}
    assert result["serving"]["compute"] == "gateway-in-process-cpu"


@pytest.mark.asyncio
@respx.mock
async def test_stats_gateway_projects_metadata():
    respx.get("https://gateway.test/v1/namespaces/lens/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "approx_row_count": 2_500,
                "approx_logical_bytes": 42_000_000,
                "updated_at": "2026-08-11T00:00:00Z",
                "schema": {"image_url": {"type": "string"}},
            },
        )
    )
    async with httpx.AsyncClient() as client:
        result = await stats_gateway(
            client,
            gateway_url="https://gateway.test",
            api_key="secret",
            namespace="lens",
        )
    assert result == {
        "approx_row_count": 2_500,
        "approx_logical_bytes": 42_000_000,
        "updated_at": "2026-08-11T00:00:00Z",
    }
