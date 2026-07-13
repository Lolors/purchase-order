"""Purchase and statement page adapters."""
from __future__ import annotations


def register(purchase_module, data) -> None:
    purchase_module.page_statement_register(data["orders"], data["order_items"])


def statement_list(purchase_module, data) -> None:
    purchase_module.page_statement_list()


def monthly(purchase_module, data) -> None:
    purchase_module.page_monthly_purchase()
