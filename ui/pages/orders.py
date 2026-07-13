"""Order-related page adapters."""
from __future__ import annotations


def write(core_app, data) -> None:
    core_app.page_write(
        data["vendors"], data["products"], data["aliases"],
        data["drafts"], data["draft_items"], data["orders"], data["order_items"],
    )


def drafts(core_app, data) -> None:
    core_app.page_drafts(data["drafts"], data["draft_items"])


def order_list(core_app, data) -> None:
    core_app.page_orders(data["vendors"], data["orders"], data["order_items"])


def recent(core_app, data) -> None:
    core_app.page_recent_orders(data["orders"])
