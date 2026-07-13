"""v18 애플리케이션 조립과 기존 UI 호환 연결."""
from __future__ import annotations

import sys
from pathlib import Path

from repositories import purchase_repository


def build_application(base_dir: Path):
    layer_dir = base_dir / "app_layers"
    if str(layer_dir) not in sys.path:
        sys.path.insert(0, str(layer_dir))

    import core_app
    sys.modules["app"] = core_app

    import db_migration
    db_status = db_migration.initialize_database(core_app.DATA)

    import app_order_review as final_app

    if db_status.get("ok"):
        import db_store
        import app_product_schema as product_schema

        db_store.activate(core_app)

        def read_products_from_db():
            return product_schema.products_for_app(db_store.load_products(core_app.DATA))

        def save_products_to_db(df):
            db_store.save_products(core_app.DATA, df)

        product_schema.read_products_file = read_products_from_db
        product_schema.save_products_with_schema = save_products_to_db
        core_app.save_products = save_products_to_db
        core_app.save_aliases = lambda df: db_store.save_aliases(core_app.DATA, df)
        core_app.save_vendors = lambda df: db_store.save_vendors(core_app.DATA, df)
        core_app.save_order = lambda vendor_name, request_note, items: db_store.save_order(
            core_app.DATA, core_app, vendor_name, request_note, items
        )
        core_app.delete_order = lambda order_id: db_store.delete_order(core_app.DATA, order_id)

        purchase = final_app.purchase
        purchase.load_purchase_data = lambda: purchase_repository.load_all(core_app.DATA)

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

        purchase.save_table = save_purchase_table

    return core_app, final_app, db_status


def run(base_dir: Path) -> None:
    core_app, final_app, db_status = build_application(base_dir)
    if not db_status.get("ok"):
        core_app.st.error(
            "SQLite DB 초기화에 실패했습니다. 기존 CSV 방식으로 앱을 계속 실행합니다.\n\n"
            f"오류: {db_status.get('error', '알 수 없는 오류')}"
        )
    elif db_status.get("migrated"):
        core_app.st.toast("기존 CSV 데이터를 SQLite DB로 안전하게 이전했습니다.", icon="✅")
    final_app.purchase.main()
