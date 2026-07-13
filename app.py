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

import app_order_review as final_app


if __name__ == "__main__":
    final_app.purchase.main()
