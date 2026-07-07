## Code navigation (token efficiency)

Prefer semantic tools over reading whole files or broad grepping:

- **Serena (MCP)** — for code symbols. Use `find_symbol` to fetch a single function/class body, `find_referencing_symbols` to see callers, and `replace_symbol_body` for targeted edits, instead of `Read`-ing an entire file. Serena is backed by a real language server, so it is precise.
- **graphify** — for architecture/relationship questions across the repo (see below), before falling back to `grep`/`glob`.
- Full-file `Read` is still fine for small files or when you genuinely need the whole thing (e.g. a short script or doc).

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
