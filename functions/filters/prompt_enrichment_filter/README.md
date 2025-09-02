# Prompt Enrichment Filter

Appends cached user context (from services like M365) to the system prompt before the request enters the manifold.

## Valves
- `CACHE_TTL_SECONDS`: seconds before cached data expires.
