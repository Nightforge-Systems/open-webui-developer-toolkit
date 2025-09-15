"""
title: Status Emitter Example (Cookbook + Multiline)
author: ChatGPT
version: 1.2.0
description: A clear, linear demo of Open WebUI status events (no loops), including a collapsible panel via action='web_search'. At the end, shows how to enable multi-line status descriptions by injecting a tiny CSS rule (no frontend rebuild).
"""

import asyncio
from typing import Optional, Callable, Awaitable, Union
from pydantic import BaseModel, Field

class Pipe:
    class Valves(BaseModel):
        STEP_DELAY_SECONDS: float = Field(
            default=0.6, description="Delay between status steps (for demo pacing)."
        )
        ENABLE_MULTILINE_PATCH: bool = Field(
            default=True,
            description="If True, injects a tiny CSS rule so status descriptions can be multi-line."
        )

    def __init__(self):
        self.type = "pipe"
        self.id = "status_emitter_cookbook_multiline"
        self.name = "Status Emitter Example (Cookbook + Multiline)"
        self.valves = self.Valves()

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
        __event_call__: Optional[Callable[[dict], Awaitable[dict]]] = None,
    ) -> Union[str, dict]:

        # For demo pacing (lets you see each status appear)
        D = self.valves.STEP_DELAY_SECONDS

        if self.valves.ENABLE_MULTILINE_PATCH and __event_call__ is not None:
            await __event_call__({
                "type": "execute",
                "data": {
                    "code": """
                    (() => {
                    // Only inject once per tab
                    if (document.getElementById("owui-status-unclamp")) return "ok";

                    const style = document.createElement("style");
                    style.id = "owui-status-unclamp";

                    style.textContent = `
                        /* Allow multi-line in the status strip */
                        .status-description .line-clamp-1,
                        .status-description .text-base.line-clamp-1,
                        .status-description .text-gray-500.text-base.line-clamp-1 {
                        display: block !important;
                        overflow: visible !important;
                        -webkit-line-clamp: unset !important;
                        -webkit-box-orient: initial !important;
                        white-space: pre-wrap !important;  /* render \\n as line breaks */
                        word-break: break-word;
                        }

                        /* Bold the first visual line */
                        .status-description .text-base::first-line,
                        .status-description .text-gray-500.text-base::first-line {
                        font-weight: 500 !important;
                        }
                    `;

                    document.head.appendChild(style);
                    return "ok";
                    })();
                    """
                }
            })

        # -----------------------------------------------------------
        # 1) Plain pending line — shimmer + ping shows it's in-flight
        # -----------------------------------------------------------
        await __event_emitter__({
            "type": "status",
            "data": {
                "description": "Preparing job…",
                "done": False,
                "hidden": False  # set True to not render this.
            }
        })
        await asyncio.sleep(D)

        # -----------------------------------------------------------
        # 2) Another visible, pending line
        # -----------------------------------------------------------
        await __event_emitter__({
            "type": "status",
            "data": {
                "description": "Queued task",
                "done": False
            }
        })
        await asyncio.sleep(D)

        # -----------------------------------------------------------
        # 3) Knowledge search branch — frontend shows fixed copy
        #    “Searching Knowledge for "<query>””
        # -----------------------------------------------------------
        await __event_emitter__({
            "type": "status",
            "data": {
                "action": "knowledge_search",
                "description": 'Searching Knowledge for "{{searchQuery}}"',
                "query": "Widget Spec v2",
                "done": False
            }
        })
        await asyncio.sleep(D)

        # -----------------------------------------------------------
        # 4) Web search queries as CHIPS
        # -----------------------------------------------------------
        await __event_emitter__({
            "type": "status",
            "data": {
                "action": "web_search_queries_generated",
                "description": "Searching",
                "queries": [
                    "widget spec v2 breaking changes",
                    "widget spec v2 migration checklist",
                    "widget v1 vs v2 compatibility matrix"
                ],
                "done": False
            }
        })
        await asyncio.sleep(D)

        # -----------------------------------------------------------
        # 5) Generic "queries_generated" chips
        # -----------------------------------------------------------
        await __event_emitter__({
            "type": "status",
            "data": {
                "action": "queries_generated",
                "description": "Querying",
                "queries": [
                    "internal changelog search",
                    "recent incidents affecting widgets"
                ],
                "done": False
            }
        })
        await asyncio.sleep(D)

        # -----------------------------------------------------------
        # 6) Retrieved sources count — frontend pluralizes via i18n
        # -----------------------------------------------------------
        await __event_emitter__({
            "type": "status",
            "data": {
                "action": "sources_retrieved",
                "description": "Retrieved {{count}} sources",
                "count": 3,     # 0 → "No sources found", 1 → "Retrieved 1 source", N → "Retrieved N sources"
                "done": False
            }
        })
        await asyncio.sleep(D)

        # -----------------------------------------------------------
        # 7) Collapsible panel (links) using action='web_search' + ITEMS
        #    - Omit "query" to hide the Google search row
        #    - Provide your own label in "description"
        #    - The panel shows "items" as a list of links (title → label, link → href)
        # -----------------------------------------------------------
        await __event_emitter__({
            "type": "status",
            "data": {
                "action": "web_search",                 # enables the collapsible panel
                "description": "Artifacts • {{count}} items",  # '{{count}}' uses len(items)
                "items": [
                    {"title": "Runbook (Markdown)", "link": "https://example.com/runbook.md"},
                    {"title": "Rollout Checklist",  "link": "https://example.com/checklist"},
                    {"title": "FAQ",                "link": "https://example.com/faq"}
                ],
                "done": True
            }
        })
        await asyncio.sleep(D)

        # -----------------------------------------------------------
        # 8) Collapsible panel using simple URLs (and a Google row via "query")
        # -----------------------------------------------------------
        await __event_emitter__({
            "type": "status",
            "data": {
                "action": "web_search",
                "description": "References • Searched {{count}} sites",
                "query": "Widget v2 migration",  # omit this to hide the "Google" line
                "urls": [
                    "https://example.com/widget-v2/overview",
                    "https://example.com/widget-v2/migration",
                    "https://example.com/widget-v2/faq"
                ],
                "done": True
            }
        })
        await asyncio.sleep(D)

        # -----------------------------------------------------------
        # 9) A final pending step
        # -----------------------------------------------------------
        await __event_emitter__({
            "type": "status",
            "data": {
                "description": "Post‑processing results…",
                "done": False,
                "action": "stage"
            }
        })
        await asyncio.sleep(D)

        # -----------------------------------------------------------
        # 10) Final status — clicking this line toggles the history panel
        # -----------------------------------------------------------
        await __event_emitter__({
            "type": "status",
            "data": {
                "description": "All steps complete ✅",
                "done": True,
                "action": "stage"
            }
        })
        await asyncio.sleep(D)

        # Optional: a toast to show the run finished
        await __event_emitter__({
            "type": "notification",
            "data": {"type": "success", "content": "Pipeline finished successfully."}
        })

        # ------------------------------------------------------------------
        # BONUS: Multi-line Status Descriptions
        #
        # By default, Open WebUI clamps status description text to one line
        # (`line-clamp-1`). This CSS patch removes the clamp and enables
        # `white-space: pre-wrap`, so `\n` show as real line breaks.
        #
        # Additionally, it uses the ::first-line pseudo-element to make the
        # first visual line of each status description bold for emphasis.
        #
        # Key points:
        #   • Runs once per tab (idempotent: checks for existing <style>).
        #   • Safe: only affects `.status-description` nodes.
        #   • Requires no frontend rebuild; works immediately at runtime.
        # ------------------------------------------------------------------
        if self.valves.ENABLE_MULTILINE_PATCH and __event_call__ is not None:
            # Now emit a demonstration status that contains explicit newlines.
            await asyncio.sleep(0.2)
            await __event_emitter__({
                "type": "status",
                "data": {
                    "description": (
                        "Reasoning summary (multi-line demo):\n"
                        "• Validate inputs\n"
                        "• Compute delta\n"
                        "• Plan safe rollout\n\n"
                        "Expected: AvailableReplicas == DesiredReplicas"
                    ),
                    "done": False
                }
            })

            # Emit final status done message
            await asyncio.sleep(D)
            await __event_emitter__({
                "type": "status",
                "data": {
                    "description": "All steps complete ✅",
                    "done": True,
                }
            })
        # -----------------------------------------------------------



        # The assistant message body (the bubble under the strip)
        return (
            "✅ Done.\n"
            "• Click the latest status row to expand/collapse earlier steps.\n"
            "• Notice how two steps include collapsible panels (via `action: \"web_search\"`).\n"
            "• Multi‑line status text is enabled with a tiny CSS patch; no frontend rebuild needed."
        )
