"""1.0.0 애플리케이션 조립과 기존 UI 호환 연결."""
from __future__ import annotations

import sys
from pathlib import Path

from config import APP_TITLE
from repositories import purchase_repository
from repositories.catalog_repository import CatalogRepository
from repositories.order_repository import OrderRepository


def build_application(base_dir: Path):
    layer_dir = base_dir / "app_layers"
    if str(layer_dir) not in sys.path:
        sys.path.insert(0, str(layer_dir))

    import core_app
    sys.modules["app"] = core_app

    import db_migration
    db_status = db_migration.initialize_database(core_app.DATA)

    # 기존 화면 체인은 아직 유지하되 데이터 접근은 Repository로 주입합니다.
    import app_order_review as final_app

    if db_status.get("ok"):
        import app_product_schema as product_schema

        catalog_repo = CatalogRepository(core_app.DATA)
        order_repo = OrderRepository(core_app.DATA, core_app)
        original_load_data = core_app.load_data

        def load_data_from_repositories():
            _, _, _, drafts, draft_items, _, _ = original_load_data()
            vendors = catalog_repo.load_vendors()
            products = catalog_repo.load_products()
            products["정식제품명"] = products["제품명"]
            products["단위"] = products["포장단위"]
            aliases = catalog_repo.load_aliases()
            orders, order_items = order_repo.load_all()
            return vendors, products, aliases, drafts, draft_items, orders, order_items

        def read_products_from_db():
            return product_schema.products_for_app(catalog_repo.load_products())

        core_app.load_data = load_data_from_repositories
        product_schema.read_products_file = read_products_from_db
        product_schema.save_products_with_schema = catalog_repo.save_products

        core_app.save_products = catalog_repo.save_products
        core_app.save_aliases = catalog_repo.save_aliases
        core_app.save_vendors = catalog_repo.save_vendors
        core_app.save_order = order_repo.save
        core_app.delete_order = order_repo.delete

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
    core_app.st.sidebar.caption(APP_TITLE)

    if not db_status.get("ok"):
        core_app.st.error(
            "SQLite DB 초기화에 실패했습니다. 기존 CSV 방식으로 앱을 계속 실행합니다.\n\n"
            f"오류: {db_status.get('error', '알 수 없는 오류')}"
        )
    elif db_status.get("migrated"):
        core_app.st.toast("기존 CSV 데이터를 SQLite DB로 안전하게 이전했습니다.", icon="✅")

    final_app.purchase.main()
