"""Top-level page router for the 1.0 application.

Legacy page functions are intentionally reused during the migration. New pages can be
moved here one at a time without changing the application entrypoint again.
"""
from __future__ import annotations

from ui.navigation import render_sidebar


def run(core_app, purchase_module) -> None:
    purchase_module.ensure_purchase_files()
    core_app.inject_css()
    core_app.init_state()

    vendors, products, aliases, drafts, draft_items, orders, order_items = core_app.load_data()
    page = render_sidebar(core_app.st)

    routes = {
        "발주 작성": lambda: core_app.page_write(
            vendors, products, aliases, drafts, draft_items, orders, order_items
        ),
        "임시저장 목록": lambda: core_app.page_drafts(drafts, draft_items),
        "발주서 목록": lambda: core_app.page_orders(vendors, orders, order_items),
        "최근 발주 내역": lambda: core_app.page_recent_orders(orders),
        "거래명세서 등록": lambda: purchase_module.page_statement_register(orders, order_items),
        "거래명세서 내역": purchase_module.page_statement_list,
        "월별 매입 현황": purchase_module.page_monthly_purchase,
        "거래처 관리": lambda: core_app.page_vendor_manage(vendors),
        "제품 관리": lambda: core_app.page_product_manage(products),
        "별칭 관리": lambda: core_app.page_alias_manage(vendors, products, aliases),
    }

    handler = routes.get(page)
    if handler is None:
        core_app.page_placeholder(page)
        return
    handler()
