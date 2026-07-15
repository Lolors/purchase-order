"""체크 선택과 개별 대체 버튼을 지원하는 거래명세서 등록 화면."""
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


def _selection_rows(purchase_module, order_rows, statements, statement_items, selected_order):
    received = _received_by_order(purchase_module, statements, statement_items, selected_order)
    rows = []
    for source_index, (_, row) in enumerate(order_rows.reset_index(drop=True).iterrows()):
        ordered_qty = _to_int(purchase_module, row.get("수량", 0))
        received_qty = received.get(item_key(row), 0)
        remaining = max(0, ordered_qty - received_qty)
        if remaining <= 0:
            continue
        rows.append({
            "이번 입고": False,
            "품목번호": source_index,
            "제품코드": str(row.get("제품코드", "") or ""),
            "제품명": str(row.get("정식제품명", row.get("제품명", "")) or ""),
            "규격": str(row.get("규격", "") or ""),
            "포장단위": str(row.get("단위", row.get("포장단위", "")) or ""),
            "발주수량": ordered_qty,
            "누적입고": received_qty,
            "남은수량": remaining,
        })
    return pd.DataFrame(rows)


def _substitution_state(st, selected_order: str) -> dict[str, bool]:
    key = f"statement_substitution_state_{selected_order}"
    state = st.session_state.get(key)
    if not isinstance(state, dict):
        state = {}
        st.session_state[key] = state
    return state


def _input_key(selected_order: str, item_no: int, field: str) -> str:
    return f"statement_{field}_{selected_order}_{item_no}"


def render(purchase_module, data) -> None:
    st = purchase_module.st
    orders = data["orders"].copy()
    order_items = data["order_items"].copy()
    products = data["products"].copy()
    statements, statement_items, price_history, _ = purchase_module.load_purchase_data()

    st.markdown("## 거래명세서 등록")
    st.caption(
        "먼저 이번에 입고된 발주품목만 체크하세요. 체크한 품목만 아래에서 수량과 매입정보를 입력할 수 있습니다."
    )

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
        key="statement_register_order",
    )
    order_header = open_orders[open_orders["발주ID"].astype(str) == selected_order].iloc[0]
    order_rows = order_items[order_items["발주ID"].astype(str) == selected_order].copy()

    product_names, product_lookup = _catalog(products)
    if not product_names:
        st.warning("제품 관리에 등록된 제품이 없어 대체제품을 선택할 수 없습니다.")
        return

    with st.container(border=True):
        st.markdown("### 명세서 기본 정보")
        c1, c2, c3 = st.columns(3)
        statement_no = c1.text_input("거래명세서 번호", value="")
        statement_date = c1.date_input("거래명세서 일자", value=datetime.now().date())
        freight = c2.number_input("운송비(배송비)", min_value=0, value=0, step=1000)
        freight_checked = c2.checkbox("운송비 입력 완료", value=False)
        memo = c3.text_area("메모", height=88)

    st.markdown("### 1) 이번 입고 품목 선택")
    selection_source = _selection_rows(
        purchase_module, order_rows, statements, statement_items, selected_order
    )
    if selection_source.empty:
        st.info("이 발주서에는 입고가 남은 품목이 없습니다.")
        return

    selected_table = st.data_editor(
        selection_source,
        use_container_width=True,
        hide_index=True,
        disabled=[
            "품목번호", "제품코드", "제품명", "규격", "포장단위",
            "발주수량", "누적입고", "남은수량",
        ],
        column_config={
            "이번 입고": st.column_config.CheckboxColumn("이번 입고", width="small"),
            "품목번호": None,
            "제품명": st.column_config.TextColumn("제품명", width="large"),
        },
        key=f"statement_receipt_selection_{selected_order}",
    )
    selected_items = selected_table[selected_table["이번 입고"] == True].copy()  # noqa: E712

    st.markdown("### 2) 선택 품목 입력")
    if selected_items.empty:
        st.info("이번에 입고된 품목을 위 표에서 체크하세요.")

    substitution_state = _substitution_state(st, selected_order)
    preview_rows = []

    for _, selected_row in selected_items.iterrows():
        item_no = int(selected_row["품목번호"])
        original_name = str(selected_row.get("제품명", "") or "")
        original_code = str(selected_row.get("제품코드", "") or "")
        original_spec = str(selected_row.get("규격", "") or "")
        original_unit = str(selected_row.get("포장단위", "") or "")
        remaining = _to_int(purchase_module, selected_row.get("남은수량", 0))
        state_key = str(item_no)
        is_substitution = bool(substitution_state.get(state_key, False))

        with st.container(border=True):
            title_col, substitute_col = st.columns([4, 1])
            title_col.markdown(f"#### {original_name}")
            title_col.caption(
                f"{original_code} · {original_spec} · {original_unit} · 남은수량 {remaining:,}"
            )
            button_label = "대체 취소" if is_substitution else "대체"
            if substitute_col.button(
                button_label,
                key=_input_key(selected_order, item_no, "substitute_button"),
                use_container_width=True,
            ):
                substitution_state[state_key] = not is_substitution
                st.session_state[f"statement_substitution_state_{selected_order}"] = substitution_state
                st.rerun()

            actual_name = original_name
            reason = ""
            if is_substitution:
                sub1, sub2 = st.columns([2, 2])
                default_index = product_names.index(original_name) if original_name in product_names else 0
                actual_name = sub1.selectbox(
                    "실제 입고제품",
                    product_names,
                    index=default_index,
                    key=_input_key(selected_order, item_no, "actual_product"),
                )
                reason = sub2.text_input(
                    "대체사유",
                    key=_input_key(selected_order, item_no, "substitution_reason"),
                    placeholder="예: 거래처 재고 부족으로 다른 브랜드 대체",
                )

            actual = product_lookup.get(actual_name)
            if actual is None and actual_name == original_name:
                actual = {
                    "제품코드": original_code,
                    "정식제품명": original_name,
                    "규격": original_spec,
                    "단위": original_unit,
                }

            q1, q2, q3, q4 = st.columns([1, 1.2, 1.2, 1.2])
            quantity = q1.number_input(
                "이번 입고수량",
                min_value=0,
                max_value=remaining,
                value=remaining,
                step=1,
                key=_input_key(selected_order, item_no, "quantity"),
            )
            price = q2.number_input(
                "매입단가",
                min_value=0,
                value=0,
                step=100,
                key=_input_key(selected_order, item_no, "price"),
            )
            lot_number = q3.text_input(
                "제조번호",
                key=_input_key(selected_order, item_no, "lot"),
            )
            expiry_date = q4.text_input(
                "유통기한",
                key=_input_key(selected_order, item_no, "expiry"),
                placeholder="예: 2028-03-01",
            )
            apply_price = st.checkbox(
                "현재 가격 적용",
                value=True,
                key=_input_key(selected_order, item_no, "apply_price"),
            )

            if quantity > 0 and actual:
                receipt_type = "대체입고" if is_substitution else "정상입고"
                preview_rows.append({
                    **actual,
                    "발주수량": _to_int(purchase_module, selected_row.get("발주수량", 0)),
                    "입고수량": int(quantity),
                    "매입단가": int(price),
                    "상품금액": int(quantity) * int(price),
                    "출고단가": purchase_module.calc_sell_price(price),
                    "가격적용여부": "Y" if apply_price else "N",
                    "원발주제품코드": original_code,
                    "원발주제품명": original_name,
                    "원발주규격": original_spec,
                    "원발주단위": original_unit,
                    "입고유형": receipt_type,
                    "대체사유": str(reason or "").strip(),
                    "제조번호": str(lot_number or "").strip(),
                    "유통기한": str(expiry_date or "").strip(),
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
        if selected_items.empty:
            st.warning("이번에 입고된 품목을 체크하세요.")
            return
        if preview.empty:
            st.warning("선택 품목의 이번 입고수량을 입력하세요.")
            return
        if len(preview) != len(selected_items):
            st.warning("체크한 모든 품목의 입고수량을 1 이상 입력하세요.")
            return
        if (preview["매입단가"] <= 0).any():
            st.warning("입고 품목의 매입단가를 입력하세요.")
            return
        missing_reason = preview[
            (preview["입고유형"] == "대체입고")
            & (preview["대체사유"].astype(str).str.strip() == "")
        ]
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
        st.session_state.pop(f"statement_substitution_state_{selected_order}", None)
        st.success(f"거래명세서를 저장했습니다: {sid}")
        st.rerun()
