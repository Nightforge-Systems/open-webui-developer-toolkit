# Status Emitter Example

Demonstrates how a pipe can emit every supported `status` action to Open WebUI.
Each update waits **two seconds** before sending the next so you can observe the
UI transitions.

The accompanying [`status_emitter_example.py`](status_emitter_example.py) script
sends:

- a plain status message
- expandable `web_search` results using both `items` and `urls`
- a `knowledge_search` lookup
- `web_search_queries_generated` and `queries_generated` suggestions
- a `sources_retrieved` count
- hidden and error statuses

Run this pipe in your Open WebUI instance to see how the frontend renders each
entry in the status history.
