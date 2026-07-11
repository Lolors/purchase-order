"""발주 검색 속도, 별칭 우선순위, 선택 발주일자 저장을 보정하는 실행 런처."""

from datetime import date, datetime

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


def _selected_order_date():
    """발주 작성 화면에서 선택한 발주일자를 date 객체로 반환합니다."""
    value = base_app.st.session_state.get("order_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return pd.to_datetime(value).date()
        except Exception:
            pass
    return datetime.now().date()


def save_order_with_selected_date(vendor_name, request_note, order_items):
    """선택한 발주일자로 발주ID와 발주일시를 생성해 저장합니다."""
    orders = base_app.read_csv(
        base_app.ORDERS_FILE,
        ["발주ID", "발주일시", "거래처명", "요청사항", "상태", "총품목수", "총수량"],
    )
    order_items_df = base_app.read_csv(
        base_app.ORDER_ITEMS_FILE,
        ["발주ID", "순번", "제품코드", "정식제품명", "검색별칭", "규격", "단위", "수량"],
    )

    selected_date = _selected_order_date()
    now = datetime.now()
    selected_datetime = datetime.combine(selected_date, now.time().replace(microsecond=0))
    order_id = f"PO-{selected_datetime.strftime('%Y%m%d-%H%M%S')}"

    # 같은 초에 중복 저장했을 때 기존 발주를 덮어쓰지 않도록 순번을 붙입니다.
    existing_ids = set(orders["발주ID"].astype(str).tolist())
    if order_id in existing_ids:
        suffix = 2
        candidate = f"{order_id}-{suffix}"
        while candidate in existing_ids:
            suffix += 1
            candidate = f"{order_id}-{suffix}"
        order_id = candidate

    total_count, total_qty = base_app.calc_totals(order_items)
    orders = pd.concat([
        orders,
        pd.DataFrame([{
            "발주ID": order_id,
            "발주일시": selected_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "거래처명": vendor_name,
            "요청사항": request_note,
            "상태": "발주완료",
            "총품목수": total_count,
            "총수량": total_qty,
        }]),
    ], ignore_index=True)

    rows = []
    for idx, item in enumerate(order_items, 1):
        rows.append({
            "발주ID": order_id,
            "순번": idx,
            "제품코드": item.get("제품코드", ""),
            "정식제품명": item.get("정식제품명", ""),
            "검색별칭": item.get("검색별칭", ""),
            "규격": item.get("규격", ""),
            "단위": item.get("단위", ""),
            "수량": base_app.safe_int(item.get("수량", 0)),
        })

    if rows:
        order_items_df = pd.concat([order_items_df, pd.DataFrame(rows)], ignore_index=True)

    orders.to_csv(base_app.ORDERS_FILE, index=False, encoding="utf-8-sig")
    order_items_df.to_csv(base_app.ORDER_ITEMS_FILE, index=False, encoding="utf-8-sig")
    return order_id


base_app.st.text_input = text_input_without_default_sample
base_app.search_products = search_products
base_app.save_order = save_order_with_selected_date


if __name__ == "__main__":
    purchase.main()
