"""대체입고를 지원하는 거래명세서 등록 화면."""
from __future__ import annotations

from datetime import datetime

import pandas as pd


def _to_int(purchase_module, value) -> int:
    return purchase_module.to_int(value)


def item_key(row) -> tuple:
    """입고상태 계산은 실제 입고품이 아니라 원발주품목 기준으로 수행합니다."""
    original_code = str(row.get("원발주제품코드", "") or "").strip()
    code = original_code or str(row.get("제품코드", "") or "").strip()
    if code:
        return ("CODE", code)
    original_name = str(row.get("원발주제품명", "") or "").strip()
    original_spec = str(row.get("원발주규격", "") or "").strip()
    original_unit = str(row.get("원발주단위", "") or "").strip()
    return (
        "TEXT",
        original_name or str(row.get("정식제품명", row.get("제품명", "")) or "").strip(),
        original_spec or str(row.get("규격", "") or "").strip(),
        original_unit or str(row.get("단위", row.get("포장단위", "")) or "").strip(),
    )


def _received_by_order(purchase_module, statements, statement_items, order_id: str) -> dict[tuple, int]:
    linked_ids = statements.loc[
        statements["발주ID"].astype(str) == str(order_id), "명세서ID"
    ].astype(str).tolist()
    received: dict[tuple, int] = {}
    if not linked_ids:
        return received
    related = statement_items[statement_items["명세서ID"].astype(str).isin(linked_ids)]
    for _, row in related.iterrows():
        key = item_key(row)
        received[key] = received.get(key, 0) + _to_int(purchase_module, row.get("입고수량", 0))
    return received


def _open_orders(purchase_module, orders, order_items):
    statements, statement_items, _, _ = purchase_module.load_purchase_data()
    open_ids = []
    for order_id in orders["발주ID"].astype(str).tolist():
        rows = order_items[order_items["발주ID"].astype(str) == order_id]
        if rows.empty:
            continue
        received = _received_by_order(purchase_module, statements, statement_items, order_id)
        if any(
            received.get(item_key(row), 0) < _to_int(purchase_module, row.get("수량", 0))
            for _, row in rows.iterrows()
        ):
            open_ids.append(order_id)
    return orders[orders["발주ID"].astype(str).isin(open_ids)].copy()


def _catalog(products: pd.DataFrame) -> tuple[list[str], dict[str, dict]]:
    rows = products.copy().fillna("")
    if "제품명" not in rows.columns:
        rows["제품명"] = rows.get("정식제품명", "")
    if "포장단위" not in rows.columns:
        rows["포장단위"] = rows.get("단위", "")
    rows["제품명"] = rows["제품명"].astype(str).str.strip()
    rows = rows[rows["제품명"] != ""].drop_duplicates("제품명")
    lookup = {
        str(row["제품명"]): {
            "제품코드": str(row.get("제품코드", "") or ""),
            "정식제품명": str(row.get("제품명", "") or ""),
            "규격": str(row.get("규격", "") or ""),
            "단위": str(row.get("포장단위", "") or ""),
        }
        for _, row in rows.iterrows()
    }
    return sorted(lookup), lookup


def _editor_rows(purchase_module, order_rows, statements, statement_items, selected_order, product_names):
    received = _received_by_order(purchase_module, statements, statement_items, selected_order)
    rows = []
    for _, row in order_rows.iterrows():
        ordered_qty = _to_int(purchase_module, row.get("수량", 0))
        received_qty = received.get(item_key(row), 0)
        remaining = max(0, ordered_qty - received_qty)
        original_name = str(row.get("정식제품명", row.get("제품명", "")) or "").strip()
        actual_default = original_name if original_name in product_names else (product_names[0] if product_names else original_name)
        rows.append({
            "원발주제품코드": str(row.get("제품코드", "") or ""),
            "원발주제품명": original_name,
            "원발주규격": str(row.get("규격", "") or ""),
            "원발주단위": str(row.get("단위", row.get("포장단위", "")) or ""),
            "발주수량": ordered_qty,
            "누적입고수량": received_qty,
            "남은수량": remaining,
            "실제 입고제품": actual_default,
            "이번입고수량": remaining,
            "매입단가": 0,
            "현재 가격 적용": True,
            "대체사유": "",
        })
    return pd.DataFrame(rows)


def render(purchase_module, data) -> None:
    st = purchase_module.st
    orders = data["orders"].copy()
    order_items = data["order_items"].copy()
    products = data["products"].copy()
    statements, statement_items, price_history, _ = purchase_module.load_purchase_data()

    st.markdown("## 거래명세서 등록")
    st.caption("발주품목과 실제 입고품목이 다르면 실제 입고제품을 변경하세요. 원발주품목은 별도로 보존됩니다.")

    if orders.empty:
        st.info("등록된 발주서가 없습니다.")
        return

    open_orders = _open_orders(purchase_module, orders, order_items)
    if open_orders.empty:
        st.info("입고가 남아 있는 발주서가 없습니다.")
        return

    vendor_map = open_orders.set_index("발주ID")["거래처명"].astype(str).to_dict()
    order_options = open_orders.sort_values("발주일시", ascending=False)["발주ID"].astype(str).tolist()
    selected_order = st.selectbox(
        "연결할 발주서",
        order_options,
        format_func=lambda oid: f'[{vendor_map.get(oid, "")}] {oid}',
    )
    order_header = open_orders[open_orders["발주ID"].astype(str) == selected_order].iloc[0]
    order_rows = order_items[order_items["발주ID"].astype(str) == selected_order].copy()

    product_names, product_lookup = _catalog(products)
    if not product_names:
        st.warning("제품 관리에 등록된 제품이 없어 실제 입고제품을 선택할 수 없습니다.")
        return

    with st.container(border=True):
        st.markdown("### 명세서 기본 정보")
        c1, c2, c3 = st.columns(3)
        statement_no = c1.text_input("거래명세서 번호", value="")
        statement_date = c1.date_input("거래명세서 일자", value=datetime.now().date())
        freight = c2.number_input("운송비(배송비)", min_value=0, value=0, step=1000)
        freight_checked = c2.checkbox("운송비 입력 완료", value=False)
        memo = c3.text_area("메모", height=88)

    st.markdown("### 실제 입고품목 및 매입가 입력")
    st.caption("실제 입고제품을 바꾸면 대체입고로 처리됩니다. 대체입고 행에는 대체사유를 입력하세요.")
    editor_source = _editor_rows(
        purchase_module, order_rows, statements, statement_items, selected_order, product_names
    )
    edited = st.data_editor(
        editor_source,
        use_container_width=True,
        hide_index=True,
        disabled=[
            "원발주제품코드", "원발주제품명", "원발주규격", "원발주단위",
            "발주수량", "누적입고수량", "남은수량",
        ],
        column_config={
            "실제 입고제품": st.column_config.SelectboxColumn("실제 입고제품", options=product_names, required=True, width="large"),
            "이번입고수량": st.column_config.NumberColumn("이번 입고수량", min_value=0, step=1),
            "매입단가": st.column_config.NumberColumn("매입단가", min_value=0, step=100),
            "현재 가격 적용": st.column_config.CheckboxColumn("현재 가격 적용"),
            "대체사유": st.column_config.TextColumn("대체사유", width="medium"),
        },
        key=f"statement_substitution_items_{selected_order}",
    )

    preview_rows = []
    for _, row in edited.iterrows():
        quantity = _to_int(purchase_module, row.get("이번입고수량", 0))
        if quantity <= 0:
            continue
        actual_name = str(row.get("실제 입고제품", "") or "").strip()
        actual = product_lookup.get(actual_name)
        if not actual:
            continue
        original_name = str(row.get("원발주제품명", "") or "").strip()
        receipt_type = "정상입고" if actual_name == original_name else "대체입고"
        price = _to_int(purchase_module, row.get("매입단가", 0))
        preview_rows.append({
            **actual,
            "발주수량": _to_int(purchase_module, row.get("발주수량", 0)),
            "입고수량": quantity,
            "매입단가": price,
            "상품금액": quantity * price,
            "출고단가": purchase_module.calc_sell_price(price),
            "가격적용여부": "Y" if bool(row.get("현재 가격 적용", True)) else "N",
            "원발주제품코드": str(row.get("원발주제품코드", "") or ""),
            "원발주제품명": original_name,
            "원발주규격": str(row.get("원발주규격", "") or ""),
            "원발주단위": str(row.get("원발주단위", "") or ""),
            "입고유형": receipt_type,
            "대체사유": str(row.get("대체사유", "") or "").strip(),
        })
    preview = pd.DataFrame(preview_rows)

    product_total = int(preview["상품금액"].sum()) if not preview.empty else 0
    a, b, c = st.columns(3)
    a.metric("상품 매입금액", f"{product_total:,}원")
    b.metric("운송비", f"{int(freight):,}원")
    c.metric("총 매입금액", f"{product_total + int(freight):,}원")

    if st.button("거래명세서 저장", type="primary", use_container_width=True):
        if not statement_no.strip():
            st.warning("거래명세서 번호를 입력하세요.")
            return
        if preview.empty:
            st.warning("입고수량이 1 이상인 품목을 입력하세요.")
            return
        if (preview["매입단가"] <= 0).any():
            st.warning("입고 품목의 매입단가를 입력하세요.")
            return
        missing_reason = preview[(preview["입고유형"] == "대체입고") & (preview["대체사유"].astype(str).str.strip() == "")]
        if not missing_reason.empty:
            st.warning("대체입고 품목에는 대체사유를 입력하세요.")
            return

        sid = purchase_module.make_id("ST", statements["명세서ID"].tolist())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_statement = pd.DataFrame([{
            "명세서ID": sid,
            "발주ID": selected_order,
            "거래처명": order_header["거래처명"],
            "명세서번호": statement_no.strip(),
            "명세서일자": statement_date.strftime("%Y-%m-%d"),
            "운송비": int(freight),
            "운송비입력여부": "Y" if freight_checked or int(freight) > 0 else "N",
            "메모": memo.strip(),
            "등록일시": now,
            "수정일시": now,
        }])

        item_rows = []
        price_rows = []
        existing_price_ids = price_history["가격ID"].tolist()
        for index, row in preview.reset_index(drop=True).iterrows():
            item_rows.append({"명세서ID": sid, "순번": index + 1, **row.to_dict()})
            if str(row.get("가격적용여부", "")) == "Y":
                price_id = purchase_module.make_id(
                    "PR", existing_price_ids + [item.get("가격ID", "") for item in price_rows]
                )
                price_rows.append({
                    "가격ID": price_id,
                    "명세서ID": sid,
                    "명세서일자": statement_date.strftime("%Y-%m-%d"),
                    "제품코드": row["제품코드"],
                    "정식제품명": row["정식제품명"],
                    "매입단가": _to_int(purchase_module, row["매입단가"]),
                    "출고단가": _to_int(purchase_module, row["출고단가"]),
                    "등록일시": now,
                })

        purchase_module.save_table(
            purchase_module.STATEMENTS_FILE,
            pd.concat([statements, new_statement], ignore_index=True),
            purchase_module.STATEMENT_COLUMNS,
        )
        purchase_module.save_table(
            purchase_module.STATEMENT_ITEMS_FILE,
            pd.concat([statement_items, pd.DataFrame(item_rows)], ignore_index=True),
            purchase_module.STATEMENT_ITEM_COLUMNS,
        )
        if price_rows:
            purchase_module.save_table(
                purchase_module.PRICE_HISTORY_FILE,
                pd.concat([price_history, pd.DataFrame(price_rows)], ignore_index=True),
                purchase_module.PRICE_HISTORY_COLUMNS,
            )
        st.success(f"거래명세서를 저장했습니다: {sid}")
        st.rerun()
