---
title: "Python API Reference"
---
The pages under this section are generated from the Google-style docstrings in `micboard/`
by `scripts/generate_api_docs.py`, which reads the source statically with
[Griffe](https://mkdocstrings.github.io/griffe/). Nothing is imported at build time, so the
documentation build never needs Django settings.

Regenerate the reference after changing a documented module:

```bash
just docs-api
```

## Generated reference

- [Models](reference/models.md) — model domains, managers, and querysets
- [Services](reference/services.md) — the typed service layer and its DTOs
- [Management Commands](reference/management-commands.md) — command classes and their options
- [WebSocket Consumers](reference/websocket-consumers.md) — Channels consumers and routing
- [Exceptions](reference/exceptions.md) — the consolidated exception hierarchy

## Hand-authored references

- [HTTP Endpoints](endpoints.md) — REST surface and current status
- [WebSocket API](websocket.md) — message contract and authorization rules
- [Python and integration reference](../development/api-reference.md) — the supported
  integration surface with worked examples

The curated module list lives in `PAGES` inside `scripts/generate_api_docs.py`; add a module
there when a new public surface needs to appear in the reference.
