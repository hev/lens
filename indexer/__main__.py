from __future__ import annotations

import argparse
import html
import json
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

import httpx

from lens_common.config import Settings
from lens_common.gateway import embedding_schema

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
CATEGORY = "Category:Quality images"
DEFAULT_STATE = Path(".state/indexer.json")
THUMB_WIDTH = 640
USER_AGENT = "hev-lens-demo/0.1 (+https://github.com/hev/lens; contact: hello@hevmind.com)"
DEFAULT_WRITE_DELAY_SECONDS = 0.5
DEFAULT_WRITE_ATTEMPTS = 7
DEFAULT_RETRY_BASE_SECONDS = 2.0


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(value: str | None) -> str:
    parser = _PlainText()
    parser.feed(value or "")
    return " ".join(html.unescape("".join(parser.parts)).split())


def metadata_value(metadata: dict[str, Any], key: str) -> str:
    item = metadata.get(key) or {}
    return plain_text(str(item.get("value") or ""))


def has_clean_license(metadata: dict[str, Any]) -> bool:
    name = metadata_value(metadata, "LicenseShortName").lower()
    url = metadata_value(metadata, "LicenseUrl").lower()
    return (
        "cc by" in name
        or "cc0" in name
        or "public domain" in name
        or "/licenses/by/" in url
        or "/licenses/by-sa/" in url
        or "/publicdomain/" in url
    )


def page_row(page: dict[str, Any]) -> dict[str, Any] | None:
    imageinfo = (page.get("imageinfo") or [None])[0]
    if not isinstance(imageinfo, dict):
        return None
    metadata = imageinfo.get("extmetadata") or {}
    image_url = imageinfo.get("thumburl")
    source_url = imageinfo.get("descriptionurl")
    license_name = metadata_value(metadata, "LicenseShortName")
    license_url = metadata_value(metadata, "LicenseUrl")
    if not image_url or not source_url or not license_name or not has_clean_license(metadata):
        return None
    raw_title = metadata_value(metadata, "ObjectName") or str(page.get("title") or "")
    title = raw_title.removeprefix("File:").strip()
    return {
        "id": f"commons-{page['pageid']}",
        "title": title or f"Commons image {page['pageid']}",
        "description": metadata_value(metadata, "ImageDescription") or title,
        "image_url": str(image_url),
        "source_url": str(source_url),
        "artist": metadata_value(metadata, "Artist") or "Wikimedia Commons contributor",
        "license_name": license_name,
        "license_url": license_url or str(source_url),
        "width": int(imageinfo.get("thumbwidth") or THUMB_WIDTH),
        "height": int(imageinfo.get("thumbheight") or THUMB_WIDTH),
    }


def fetch_page(
    client: httpx.Client,
    *,
    limit: int,
    continuation: dict[str, str] | None,
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    params: dict[str, str | int] = {
        "action": "query",
        "generator": "categorymembers",
        "gcmtitle": CATEGORY,
        "gcmtype": "file",
        "gcmlimit": max(1, min(limit, 500)),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": THUMB_WIDTH,
        "iilimit": 1,
        "format": "json",
        "formatversion": 2,
    }
    if continuation:
        params.update(continuation)
    response = client.get(COMMONS_API, params=params, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    payload = response.json()
    pages = (payload.get("query") or {}).get("pages") or []
    rows = [row for page in pages if (row := page_row(page)) is not None]
    next_page = payload.get("continue")
    return rows, {str(key): str(value) for key, value in next_page.items()} if next_page else None


def write_batch(
    client: httpx.Client,
    settings: Settings,
    namespace: str,
    rows: list[dict[str, Any]],
    *,
    max_attempts: int = DEFAULT_WRITE_ATTEMPTS,
    retry_base_seconds: float = DEFAULT_RETRY_BASE_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    for attempt in range(max_attempts):
        response = client.post(
            f"{settings.gateway_url.rstrip('/')}/v2/namespaces/{namespace}",
            headers={"Authorization": f"Bearer {settings.gateway_api_key}"},
            json={
                "distance_metric": "cosine_distance",
                "schema": embedding_schema(),
                "upsert_rows": rows,
            },
        )
        if not response.is_error:
            return response.json()
        retryable = response.status_code in {429, 502, 503, 504} or (
            response.status_code == 422 and "HTTP status client error (429" in response.text
        )
        if not retryable or attempt + 1 == max_attempts:
            raise RuntimeError(f"gateway write failed ({response.status_code}): {response.text[:1000]}")
        delay = min(retry_base_seconds * (2**attempt), 60.0)
        print(
            f"retrying gateway image write after upstream throttling "
            f"attempt={attempt + 1}/{max_attempts} delay_seconds={delay:g}",
            file=sys.stderr,
        )
        sleep(delay)
    raise AssertionError("unreachable")


def load_checkpoint(path: Path) -> tuple[int, dict[str, str] | None]:
    if not path.exists():
        return 0, None
    saved = json.loads(path.read_text())
    if saved.get("category") != CATEGORY or saved.get("thumb_width") != THUMB_WIDTH:
        raise RuntimeError("checkpoint belongs to a different Commons corpus configuration")
    continuation = saved.get("continuation")
    return int(saved.get("rows", 0)), continuation if isinstance(continuation, dict) else None


def save_checkpoint(path: Path, *, rows: int, continuation: dict[str, str] | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {
                "category": CATEGORY,
                "thumb_width": THUMB_WIDTH,
                "rows": rows,
                "continuation": continuation,
            },
            indent=2,
        )
        + "\n"
    )
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Index freely licensed Commons images through Layer's in-process CPU CLIP leg."
    )
    parser.add_argument("--namespace", default=None)
    parser.add_argument("--limit", type=int, default=2_500, help="total indexed rows; 0 runs until the category ends")
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--write-delay-seconds", type=float, default=DEFAULT_WRITE_DELAY_SECONDS)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--reset-state", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings()
    if not settings.gateway_api_key:
        raise SystemExit("LAYER_GATEWAY_API_KEY is required")
    if args.limit < 0 or args.page_size < 1 or args.batch_size < 1 or args.write_delay_seconds < 0:
        raise SystemExit("--limit and write delay must be >= 0; page and batch sizes must be positive")
    namespace = args.namespace or settings.namespace
    if args.reset_state and args.state.exists():
        args.state.unlink()
    indexed, continuation = load_checkpoint(args.state)
    started_indexed = indexed
    started = time.perf_counter()
    api_pages = 0

    timeout = httpx.Timeout(settings.timeout_seconds)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        while args.limit == 0 or indexed < args.limit:
            remaining = args.page_size if args.limit == 0 else min(args.page_size, args.limit - indexed)
            rows, next_page = fetch_page(client, limit=remaining, continuation=continuation)
            api_pages += 1
            for offset in range(0, len(rows), args.batch_size):
                batch = rows[offset : offset + args.batch_size]
                result = write_batch(client, settings, namespace, batch)
                indexed += len(batch)
                performance = result.get("performance") or {}
                print(
                    f"rows={indexed:,} batch={len(batch)} "
                    f"gateway_images={performance.get('embedding_images')} "
                    f"gateway_embed_ms={performance.get('embedding_ms')}",
                    file=sys.stderr,
                )
                if args.write_delay_seconds:
                    time.sleep(args.write_delay_seconds)
            continuation = next_page
            save_checkpoint(args.state, rows=indexed, continuation=continuation)
            if continuation is None:
                break

    elapsed = time.perf_counter() - started
    print(
        json.dumps(
            {
                "namespace": namespace,
                "rows_written": indexed - started_indexed,
                "checkpoint_rows": indexed,
                "api_pages": api_pages,
                "elapsed_seconds": round(elapsed, 1),
                "rows_per_second": round((indexed - started_indexed) / elapsed, 2) if elapsed else None,
                "embedding": "gateway LocalClipEmbeddingProvider on CPU",
                "gpu_workers": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
