"""1.0.x 애플리케이션 조립과 기존 UI 호환 연결."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

from repositories import purchase_repository


@st.cache_resource(show_spinner=False)
def build_application(base_dir: Path):
    # app_layers 안의 호환 모듈을 사용하는 Repository와 UI 모듈이 있으므로,
    # 관련 모듈을 import하기 전에 먼저 경로를 등록해야 합니다.
    layer_dir = base_dir / "app_layers"
    if str(layer_dir) not in sys.path:
        sys.path.insert(0, str(layer_dir))

    from repositories.catalog_repository import CatalogRepository
    from repositories.draft_repository import DraftRepository
    from repositories.order_repository import OrderRepository
    from ui.pages.router import run as run_pages
    from ui.preview_layout import render_order_html
    from ui.purchase_preview import render as render_purchase_preview

    import core_app
    sys.modules["app"] = core_app

    import db_migration
    db_status = db_migration.initialize_database(core_app.DATA)

    # 레거시 모듈은 아직 거래명세서 페이지 구현 제공자로만 사용합니다.
    import app_order_review as final_app
    purchase = final_app.purchase
    purchase.STATEMENT_ITEM_COLUMNS = purchase_repository.STATEMENT_ITEM_COLUMNS

    # 거래명세서 대체사유는 자유입력 대신 업무에서 사용하는 고정 선택지로 제한합니다.
    original_text_input = core_app.st.text_input

    def text_input_with_substitution_reason(label, *args, **kwargs):
        if str(label) != "대체사유":
            return original_text_input(label, *args, **kwargs)

        selectbox_kwargs = {
            key: kwargs[key]
            for key in ("key", "help", "disabled", "label_visibility", "on_change", "args", "kwargs")
            if key in kwargs
        }
        return core_app.st.selectbox(
            "대체사유",
            ["브랜드 대체", "발주 실수", "구매자 변심", "기타"],
            index=0,
            **selectbox_kwargs,
        )

    core_app.st.text_input = text_input_with_substitution_reason
    purchase.st.text_input = text_input_with_substitution_reason

    # 입고행을 복사한 뒤 처음 입력한 값이 다음 rerun에서 사라지지 않도록,
    # data_editor의 변경분을 위젯 콜백 단계에서 입고행 세션 상태에 즉시 반영합니다.
    original_data_editor = core_app.st.data_editor

    def persist_receipt_editor_changes(widget_key: str) -> None:
        prefix = "statement_receipt_input_"
        if not str(widget_key).startswith(prefix):
            return

        order_and_version = str(widget_key)[len(prefix):]
        selected_order, separator, _version = order_and_version.rpartition("_")
        if not separator or not selected_order:
            return

        widget_state = core_app.st.session_state.get(widget_key, {})
        edited_rows = widget_state.get("edited_rows", {}) if isinstance(widget_state, dict) else {}
        rows_key = f"statement_receipt_rows_{selected_order}"
        stored_rows = core_app.st.session_state.get(rows_key)
        if not isinstance(stored_rows, list):
            return

        editable_columns = {
            "입고수량",
            "매입단가",
            "제조번호",
            "유통기한",
            "현재 가격 적용",
        }
        for row_index, changes in edited_rows.items():
            try:
                index = int(row_index)
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= len(stored_rows) or not isinstance(changes, dict):
                continue
            for column, value in changes.items():
                if column in editable_columns:
                    stored_rows[index][column] = value

        core_app.st.session_state[rows_key] = stored_rows

    def data_editor_with_receipt_persistence(data, *args, **kwargs):
        widget_key = kwargs.get("key")
        if not str(widget_key or "").startswith("statement_receipt_input_"):
            return original_data_editor(data, *args, **kwargs)

        existing_on_change = kwargs.pop("on_change", None)
        existing_args = kwargs.pop("args", ())
        existing_kwargs = kwargs.pop("kwargs", {})

        def on_change() -> None:
            persist_receipt_editor_changes(str(widget_key))
            if existing_on_change is not None:
                existing_on_change(*existing_args, **existing_kwargs)

        kwargs["on_change"] = on_change
        return original_data_editor(data, *args, **kwargs)

    core_app.st.data_editor = data_editor_with_receipt_persistence
    purchase.st.data_editor = data_editor_with_receipt_persistence

    # 레거시 모듈 로딩이 끝난 뒤 최종 미리보기 렌더러를 적용합니다.
    core_app.render_order_html = lambda vendor, items, note, order_id=None, order_date=None: render_order_html(
        core_app, vendor, items, note, order_id=order_id, order_date=order_date
    )
    core_app.render_purchase_preview = lambda vendor, items, note, order_date=None: render_purchase_preview(
        core_app, vendor, items, note, order_date=order_date
    )

    if db_status.get("ok"):
        import app_product_schema as product_schema

        catalog_repo = CatalogRepository(core_app.DATA)
        draft_repo = DraftRepository(core_app.DATA)
        draft_repo.migrate_legacy_csv_once()
        order_repo = OrderRepository(core_app.DATA, core_app)

        @core_app.st.cache_data(show_spinner=False)
        def load_data_from_repositories():
            vendors = catalog_repo.load_vendors()
            products = catalog_repo.load_products()
            products["정식제품명"] = products["제품명"]
            products["단위"] = products["포장단위"]
            aliases = catalog_repo.load_aliases()
            drafts, draft_items = draft_repo.load_all()
            orders, order_items = order_repo.load_all()
            return vendors, products, aliases, drafts, draft_items, orders, order_items

        @core_app.st.cache_data(show_spinner=False)
        def load_purchase_data_cached():
            return purchase_repository.load_all(core_app.DATA)

        def clear_data_cache() -> None:
            load_data_from_repositories.clear()
            load_purchase_data_cached.clear()

        def read_products_from_db():
            return product_schema.products_for_app(catalog_repo.load_products())

        def save_products(products):
            catalog_repo.save_products(products)
            clear_data_cache()

        def save_aliases(aliases):
            catalog_repo.save_aliases(aliases)
            clear_data_cache()

        def save_vendors(vendors):
            catalog_repo.save_vendors(vendors)
            clear_data_cache()

        def save_order(vendor_name, request_note, items):
            order_id = order_repo.save(vendor_name, request_note, items)
            clear_data_cache()
            return order_id

        def delete_order(order_id):
            order_repo.delete(order_id)
            clear_data_cache()

        def save_draft(vendor_name, request_note, items):
            draft_id = draft_repo.save(vendor_name, request_note, items)
            clear_data_cache()
            return draft_id

        def delete_draft(draft_id):
            draft_repo.delete(draft_id)
            clear_data_cache()

        core_app.load_data = load_data_from_repositories
        product_schema.read_products_file = read_products_from_db
        product_schema.save_products_with_schema = save_products

        core_app.save_products = save_products
        core_app.save_aliases = save_aliases
        core_app.save_vendors = save_vendors
        core_app.save_order = save_order
        core_app.delete_order = delete_order
        core_app.save_draft = save_draft
        core_app.delete_draft = delete_draft

        purchase.load_purchase_data = load_purchase_data_cached

        def save_purchase_table(path, df, columns):
            filename = Path(path).name
            if filename == "purchase_statements.csv":
                purchase_repository.replace_statements(core_app.DATA, df)
            elif filename == "purchase_statement_items.csv":
                purchase_repository.replace_statement_items(core_app.DATA, df)
            elif filename == "price_history.csv":
                purchase_repository.replace_price_history(core_app.DATA, df)
            elif filename == "purchase_month_close.csv":
                purchase_repository.replace_monthly_closes(core_app.DATA, df)
            else:
                raise ValueError(f"지원하지 않는 매입 데이터 저장 대상입니다: {filename}")
            clear_data_cache()

        purchase.save_table = save_purchase_table

    return core_app, purchase, db_status, run_pages


def run(base_dir: Path) -> None:
    core_app, purchase, db_status, run_pages = build_application(base_dir)

    if not db_status.get("ok"):
        core_app.st.error(
            "SQLite DB 초기화에 실패했습니다. 기존 CSV 방식으로 앱을 계속 실행합니다.\n\n"
            f"오류: {db_status.get('error', '알 수 없는 오류')}"
        )
    elif db_status.get("migrated"):
        core_app.st.toast("기존 CSV 데이터를 SQLite DB로 안전하게 이전했습니다.", icon="✅")

    run_pages(core_app, purchase)
