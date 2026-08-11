# lens

Wikimedia Commons image search is a design-preview customer of hev layer. The
public deliverable is `lens.hevlayer.com`; the visible artifact is Layer's
in-process CPU CLIP embedding performance echo.

Reimplement nothing the stack owns. The app does not fetch or preprocess images
for embedding, embed queries, tokenize, fuse, or rerank. Both backends issue the
same gateway `Embed` query against the image column. See `AGENTS.md` for commands
and feedback routing.
