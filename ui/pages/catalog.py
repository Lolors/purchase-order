"""Catalog and master-data page adapters."""
from __future__ import annotations


def vendors(core_app, data) -> None:
    core_app.page_vendor_manage(data["vendors"])


def products(core_app, data) -> None:
    core_app.page_product_manage(data["products"])


def aliases(core_app, data) -> None:
    core_app.page_alias_manage(data["vendors"], data["products"], data["aliases"])
