from pathlib import Path

import httpx

from indexer.__main__ import bounded_text, has_clean_license, page_row, plain_text, write_batch
from lens_common.config import Settings


def metadata(value: str) -> dict[str, str]:
    return {"value": value}


def test_plain_text_removes_commons_html():
    assert plain_text('<a href="/wiki/User:Sky">Sky &amp; Sea</a>') == "Sky & Sea"


def test_bounded_text_keeps_cards_safe_from_malformed_metadata():
    assert bounded_text("  concise metadata  ", 30) == "concise metadata"
    assert bounded_text("x" * 50, 10) == "x" * 9 + "…"


def test_clean_license_filter_accepts_cc_and_rejects_gfdl_only():
    assert has_clean_license(
        {
            "LicenseShortName": metadata("CC BY-SA 4.0"),
            "LicenseUrl": metadata("https://creativecommons.org/licenses/by-sa/4.0"),
        }
    )
    assert not has_clean_license(
        {
            "LicenseShortName": metadata("GFDL 1.2"),
            "LicenseUrl": metadata("https://www.gnu.org/licenses/old-licenses/fdl-1.2.html"),
        }
    )


def test_page_row_keeps_attribution_and_stable_id():
    page = {
        "pageid": 42,
        "title": "File:Sunset.jpg",
        "imageinfo": [
            {
                "thumburl": "https://upload.wikimedia.org/thumb/sunset.jpg",
                "thumbwidth": 640,
                "thumbheight": 427,
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Sunset.jpg",
                "extmetadata": {
                    "ObjectName": metadata("Sunset over water"),
                    "ImageDescription": metadata("<b>Evening</b> over the sea"),
                    "Artist": metadata('<a href="/wiki/User:Example">Example</a>'),
                    "LicenseShortName": metadata("CC BY 4.0"),
                    "LicenseUrl": metadata("https://creativecommons.org/licenses/by/4.0"),
                },
            }
        ],
    }
    row = page_row(page)
    assert row is not None
    assert row["id"] == "commons-42"
    assert row["description"] == "Evening over the sea"
    assert row["artist"] == "Example"
    assert row["license_name"] == "CC BY 4.0"


def test_deployed_indexer_uses_mesh_ecr_digest():
    manifest = (Path(__file__).parents[1] / "deploy" / "indexer-job.yaml").read_text()
    assert "186219257916.dkr.ecr.us-east-1.amazonaws.com/hev-lens-indexer@sha256:" in manifest
    assert "ghcr.io/hev/" not in manifest
    assert "layer.hev.dev/compute: cpu" in manifest
    assert "layer.hev.dev/node-role: worker-cpu" in manifest
    assert "nvidia.com/gpu" not in manifest


def test_write_batch_retries_gateway_wrapped_upstream_429():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                422,
                json={"error": "validation_error", "message": "HTTP status client error (429 throttled)"},
            )
        return httpx.Response(200, json={"performance": {"embedding_images": 1}})

    settings = Settings(
        gateway_url="https://gateway.test",
        gateway_api_key="secret",
        namespace="lens",
    )
    delays: list[float] = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = write_batch(
            client,
            settings,
            "lens",
            [{"id": "commons-1", "image_url": "https://example.test/image.jpg"}],
            sleep=delays.append,
        )
    assert attempts == 2
    assert delays == [2.0]
    assert result["performance"]["embedding_images"] == 1
