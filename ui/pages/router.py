"""Top-level page router for the 1.0 application."""
from __future__ import annotations

from ui.navigation import render_sidebar
from ui.pages import catalog, orders, purchases


def run(core_app, purchase_module) -> None:
    purchase_module.ensure_purchase_files()
    core_app.inject_css()
    core_app.init_state()

    vendors, products, aliases, drafts, draft_items, order_headers, order_items = core_app.load_data()
    data = {
        "vendors": vendors,
        "products": products,
        "aliases": aliases,
        "drafts": drafts,
        "draft_items": draft_items,
        "orders": order_headers,
        "order_items": order_items,
    }
    page = render_sidebar(core_app.st)

    routes = {
        "발주 작성": lambda: orders.write(core_app, data),
        "임시저장 목록": lambda: orders.drafts(core_app, data),
        "발주서 목록": lambda: orders.order_list(core_app, data, purchase_module),
        "최근 발주 내역": lambda: orders.recent(core_app, data),
        "거래명세서 등록": lambda: purchases.register(purchase_module, data),
        "거래명세서 내역": lambda: purchases.statement_list(purchase_module, data),
        "월별 매입 현황": lambda: purchases.monthly(purchase_module, data),
        "거래처 관리": lambda: catalog.vendors(core_app, data),
        "제품 관리": lambda: catalog.products(core_app, data),
        "별칭 관리": lambda: catalog.aliases(core_app, data),
    }

    handler = routes.get(page)
    if handler is None:
        core_app.page_placeholder(page)
        return
    handler()
