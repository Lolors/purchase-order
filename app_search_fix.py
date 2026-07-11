"""발주 화면 제품명 직접검색 결과가 검색어를 별칭처럼 표시하는 문제를 수정하는 실행 런처."""

import pandas as pd

import app_purchase_management as purchase

base_app = purchase.base_app


def search_products(keyword, vendor_name, products, aliases):
    """제품 검색 결과에서 실제 별칭과 제품명 직접검색을 구분합니다.

    기존 검색 함수는 제품명으로 직접 검색된 결과의 '별칭(검색어)' 값에 현재 검색창
    입력값을 넣었습니다. 그래서 기본 검색어가 '마취크림'인 상태에서 새 제품이
    제품명 유사검색으로 잡히면, 별칭 관리에 연결이 없어도 전부 마취크림 별칭처럼
    보였습니다.
    """
    keyword = (keyword or "").strip()

    if not keyword:
        return pd.DataFrame()

    rows = []
    active = products.copy().fillna("")
    alias_df = aliases.copy().fillna("")
    alias_df = alias_df[alias_df["거래처명"].isin([vendor_name, "전체", ""])]

    # 1) 실제 별칭으로 매칭된 결과
    for _, alias_row in alias_df.iterrows():
        alias = str(alias_row.get("별칭", "")).strip()
        product_code = str(alias_row.get("제품코드", "")).strip()

        if not alias or not product_code:
            continue

        score = base_app.fuzz.partial_ratio(keyword, alias)
        if keyword in alias:
            score += 30

        if score >= 45:
            product = active[active["제품코드"] == product_code]
            if not product.empty:
                p = product.iloc[0]
                rows.append({
                    "별칭(검색어)": alias,
                    "제품코드": p["제품코드"],
                    "정식제품명": p["정식제품명"],
                    "규격": p["규격"],
                    "단위": p["단위"],
                    "점수": score + 10,
                    "매칭구분": "별칭",
                })

    # 2) 제품명 자체로 매칭된 결과
    for _, p in active.iterrows():
        official = str(p.get("정식제품명", "")).strip()
        if not official:
            continue

        score = base_app.fuzz.partial_ratio(keyword, official)
        if keyword in official:
            score += 30

        if score >= 45:
            rows.append({
                "별칭(검색어)": "제품명 직접검색",
                "제품코드": p["제품코드"],
                "정식제품명": p["정식제품명"],
                "규격": p["규격"],
                "단위": p["단위"],
                "점수": score,
                "매칭구분": "제품명",
            })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result = result.sort_values(["점수", "매칭구분"], ascending=[False, True])
    result = result.drop_duplicates("제품코드", keep="first")
    return result.reset_index(drop=True)


base_app.search_products = search_products


if __name__ == "__main__":
    purchase.main()
