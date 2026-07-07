## Code navigation (token efficiency)

Prefer scoped tools over broad grepping:

- **graphify** — for architecture/relationship questions across the repo (see below), before falling back to `grep`/`glob`.
- Full-file `Read` is fine here — this is a small codebase (a handful of Python files), so reading a whole module is cheap.
- **Serena/MCP was removed** (2026-07-07): its always-on language server (pyright) cost ~16GB RAM and competed with local MLX training, for negligible benefit at this scale. Do **not** re-add it unless the codebase grows large enough to justify it.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
