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

import app_order_review as final_app


if __name__ == "__main__":
    if not DB_STATUS.get("ok"):
        core_app.st.error(
            "SQLite DB 초기화에 실패했습니다. 기존 CSV 방식으로 앱을 계속 실행합니다.\n\n"
            f"오류: {DB_STATUS.get('error', '알 수 없는 오류')}"
        )
    elif DB_STATUS.get("migrated"):
        core_app.st.toast("기존 CSV 데이터를 SQLite DB로 안전하게 이전했습니다.", icon="✅")

    final_app.purchase.main()
