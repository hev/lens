import assert from "node:assert/strict";
import test from "node:test";

import { proxySearch, searchBody, servingContract } from "../src/worker.js";

test("worker sends one inline text Embed against the image field", () => {
  assert.deepEqual(searchBody("sunset over water", 50), {
    rank_by: ["image_url", "ANN", ["Embed", "sunset over water"]],
    top_k: 30,
    include_attributes: [
      "title",
      "description",
      "image_url",
      "source_url",
      "artist",
      "license_name",
      "license_url",
      "width",
      "height",
    ],
  });
});

test("worker declares the fixed in-process CPU serving contract", () => {
  assert.deepEqual(servingContract(), {
    prefer: "local",
    model: "openai/clip-vit-base-patch32",
    dims: 512,
    write_modality: "image",
    query_modality: "text",
    compute: "gateway-in-process-cpu",
  });
});

test("worker preserves the gateway embedding performance echo", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = previousFetch; });
  let sent;
  globalThis.fetch = async (_url, options) => {
    sent = JSON.parse(options.body);
    return new Response(JSON.stringify({
      rows: [{ id: "commons-1", title: "Sunset" }],
      performance: { embedding_ms: 8.5, embedding_tokens: 4 },
      billing: null,
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const request = new Request("https://lens.test/api/search", {
    method: "POST",
    body: JSON.stringify({ query: "sunset over water", top_k: 12 }),
  });
  const response = await proxySearch(request, {
    LAYER_API_KEY: "secret",
    LAYER_GATEWAY_URL: "https://gateway.test",
    LAYER_NAMESPACE: "lens",
  });
  const body = await response.json();
  assert.deepEqual(sent.rank_by, ["image_url", "ANN", ["Embed", "sunset over water"]]);
  assert.deepEqual(body.performance, { embedding_ms: 8.5, embedding_tokens: 4 });
  assert.equal(body.serving.prefer, "local");
  assert.equal(body.serving.compute, "gateway-in-process-cpu");
});
