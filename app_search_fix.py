"""발주 검색 기본값과 대량 제품 검색 속도를 개선하는 실행 런처."""

import pandas as pd

import app_purchase_management as purchase

base_app = purchase.base_app
ORIGINAL_TEXT_INPUT = base_app.st.text_input


def text_input_without_default_sample(label, *args, **kwargs):
    """발주 검색창의 예시값 '마취크림'을 실제 입력값으로 사용하지 않습니다."""
    if label == "검색" and kwargs.get("value") == "마취크림":
        kwargs["value"] = ""
        kwargs.setdefault("key", "product_search_keyword")
    return ORIGINAL_TEXT_INPUT(label, *args, **kwargs)


def _empty_result():
    return pd.DataFrame(columns=[
        "별칭(검색어)", "제품코드", "정식제품명", "규격", "단위", "점수", "매칭구분"
    ])


def _sort_results(rows):
    """실제 별칭 일치 결과를 제품명 직접검색보다 항상 먼저 정렬합니다."""
    if not rows:
        return _empty_result()

    result = pd.DataFrame(rows)
    result["검색우선순위"] = result["매칭구분"].map({"별칭": 0, "제품명": 1}).fillna(2)
    result = result.sort_values(
        ["검색우선순위", "점수", "정식제품명"],
        ascending=[True, False, True],
    )
    result = result.drop_duplicates("제품코드", keep="first").head(30)
    return result.drop(columns=["검색우선순위"]).reset_index(drop=True)


def search_products(keyword, vendor_name, products, aliases):
    """빠른 포함검색을 우선하고, 별칭 결과를 제품명 직접검색보다 먼저 보여줍니다."""
    keyword = str(keyword or "").strip()
    if not keyword:
        return _empty_result()

    keyword_lower = keyword.casefold()
    active = products.copy().fillna("")
    alias_df = aliases.copy().fillna("")
    alias_df = alias_df[alias_df["거래처명"].isin([vendor_name, "전체", ""])]

    product_lookup = active.drop_duplicates("제품코드").set_index("제품코드", drop=False)
    rows = []

    # 1) 실제 별칭의 정확/포함 검색: 벡터 연산으로 빠르게 처리
    if not alias_df.empty:
        alias_text = alias_df["별칭"].astype(str).str.strip()
        alias_mask = alias_text.str.casefold().str.contains(keyword_lower, regex=False, na=False)
        for _, alias_row in alias_df[alias_mask].head(30).iterrows():
            code = str(alias_row.get("제품코드", "")).strip()
            if not code or code not in product_lookup.index:
                continue
            p = product_lookup.loc[code]
            alias = str(alias_row.get("별칭", "")).strip()
            rows.append({
                "별칭(검색어)": alias,
                "제품코드": p["제품코드"],
                "정식제품명": p["정식제품명"],
                "규격": p["규격"],
                "단위": p["단위"],
                "점수": 130 if alias.casefold() == keyword_lower else 110,
                "매칭구분": "별칭",
            })

    # 2) 제품명/제품코드의 정확/포함 검색
    product_name = active["정식제품명"].astype(str).str.strip()
    product_code = active["제품코드"].astype(str).str.strip()
    direct_mask = (
        product_name.str.casefold().str.contains(keyword_lower, regex=False, na=False)
        | product_code.str.casefold().str.contains(keyword_lower, regex=False, na=False)
    )
    for _, p in active[direct_mask].head(30).iterrows():
        official = str(p.get("정식제품명", "")).strip()
        code = str(p.get("제품코드", "")).strip()
        exact = official.casefold() == keyword_lower or code.casefold() == keyword_lower
        rows.append({
            "별칭(검색어)": "제품명 직접검색",
            "제품코드": p["제품코드"],
            "정식제품명": p["정식제품명"],
            "규격": p["규격"],
            "단위": p["단위"],
            "점수": 120 if exact else 100,
            "매칭구분": "제품명",
        })

    # 포함검색 결과가 있으면 비싼 유사도 검색을 생략합니다.
    if rows:
        return _sort_results(rows)

    # 3) 오타 대응 유사검색: 검색어 2자 이상일 때만, 상위 후보만 계산
    if len(keyword) < 2:
        return _empty_result()

    fuzzy_rows = []
    for _, alias_row in alias_df.head(500).iterrows():
        alias = str(alias_row.get("별칭", "")).strip()
        code = str(alias_row.get("제품코드", "")).strip()
        if not alias or not code or code not in product_lookup.index:
            continue
        score = base_app.fuzz.partial_ratio(keyword, alias)
        if score >= 70:
            p = product_lookup.loc[code]
            fuzzy_rows.append({
                "별칭(검색어)": alias,
                "제품코드": p["제품코드"],
                "정식제품명": p["정식제품명"],
                "규격": p["규격"],
                "단위": p["단위"],
                "점수": score + 10,
                "매칭구분": "별칭",
            })

    for _, p in active.head(1000).iterrows():
        official = str(p.get("정식제품명", "")).strip()
        if not official:
            continue
        score = base_app.fuzz.partial_ratio(keyword, official)
        if score >= 70:
            fuzzy_rows.append({
                "별칭(검색어)": "제품명 직접검색",
                "제품코드": p["제품코드"],
                "정식제품명": p["정식제품명"],
                "규격": p["규격"],
                "단위": p["단위"],
                "점수": score,
                "매칭구분": "제품명",
            })

    return _sort_results(fuzzy_rows)


base_app.st.text_input = text_input_without_default_sample
base_app.search_products = search_products


if __name__ == "__main__":
    purchase.main()
