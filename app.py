"""발주관리 시스템 최종 실행 진입점.

핵심 앱은 core_app.py에 보존하고, 기능 확장 모듈은 app_layers 폴더에서 순서대로 불러옵니다.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LAYER_DIR = BASE_DIR / "app_layers"

if str(LAYER_DIR) not in sys.path:
    sys.path.insert(0, str(LAYER_DIR))

import core_app

# 기존 확장 모듈들이 `import app as base_app`을 사용하므로 핵심 앱 모듈을 app 이름으로 연결합니다.
sys.modules["app"] = core_app

import db_migration

DB_STATUS = db_migration.initialize_database(core_app.DATA)

# 기능 모듈을 모두 불러온 뒤 DB 저장소를 최종 적용해야 CSV 함수가 다시 살아나지 않습니다.
import app_order_review as final_app

if DB_STATUS.get("ok"):
    import db_store
    import app_product_schema as product_schema

    db_store.activate(core_app)

    # 제품 관리 모듈은 자체 읽기·저장 함수를 사용하므로 해당 경로도 SQLite로 교체합니다.
    def _read_products_from_db():
        return product_schema.products_for_app(db_store.load_products(core_app.DATA))

    def _save_products_to_db(df):
        db_store.save_products(core_app.DATA, df)

    product_schema.read_products_file = _read_products_from_db
    product_schema.save_products_with_schema = _save_products_to_db

    # 최종 실행 시점에 다시 명시해 각 확장 모듈의 CSV 저장 함수보다 DB 함수를 우선합니다.
    core_app.save_products = _save_products_to_db
    core_app.save_aliases = lambda df: db_store.save_aliases(core_app.DATA, df)
    core_app.save_vendors = lambda df: db_store.save_vendors(core_app.DATA, df)
    core_app.save_order = lambda vendor_name, request_note, items: db_store.save_order(
        core_app.DATA, core_app, vendor_name, request_note, items
    )
    core_app.delete_order = lambda order_id: db_store.delete_order(core_app.DATA, order_id)


if __name__ == "__main__":
    if not DB_STATUS.get("ok"):
        core_app.st.error(
            "SQLite DB 초기화에 실패했습니다. 기존 CSV 방식으로 앱을 계속 실행합니다.\n\n"
            f"오류: {DB_STATUS.get('error', '알 수 없는 오류')}"
        )
    elif DB_STATUS.get("migrated"):
        core_app.st.toast("기존 CSV 데이터를 SQLite DB로 안전하게 이전했습니다.", icon="✅")

    final_app.purchase.main()
