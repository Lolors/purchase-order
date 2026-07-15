"""표 입력과 선택 품목 대체를 지원하는 거래명세서 등록 화면."""
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


def _next_statement_number(statements: pd.DataFrame, order_id: str) -> int:
    """선택 발주서에 연결된 명세서의 다음 순번을 계산합니다."""
    linked = statements[statements["발주ID"].astype(str) == str(order_id)]
    numbers = []
    for value in linked.get("명세서번호", pd.Series(dtype=str)).tolist():
        text = str(value or "").strip()
        try:
            numbers.append(int(float(text)))
        except (TypeError, ValueError):
            continue
    return (max(numbers) + 1) if numbers else 1


def _editor_rows(purchase_module, order_rows, statements, statement_items, selected_order):
    received = _received_by_order(purchase_module, statements, statement_items, selected_order)
    rows = []
    for source_index, (_, row) in enumerate(order_rows.reset_index(drop=True).iterrows()):
        ordered_qty = _to_int(purchase_module, row.get("수량", 0))
        received_qty = received.get(item_key(row), 0)
        remaining = max(0, ordered_qty - received_qty)
        if remaining <= 0:
            continue
        rows.append({
            "선택": False,
            "품목번호": source_index,
            "제품코드": str(row.get("제품코드", "") or ""),
            "제품명": str(row.get("정식제품명", row.get("제품명", "")) or ""),
            "규격": str(row.get("규격", "") or ""),
            "포장단위": str(row.get("단위", row.get("포장단위", "")) or ""),
            "발주수량": ordered_qty,
            "누적입고": received_qty,
            "남은수량": remaining,
            "이번입고수량": remaining,
            "매입단가": 0,
            "제조번호": "",
            "유통기한": "",
            "현재 가격 적용": True,
        })
    return pd.DataFrame(rows)


def _substitution_state(st, selected_order: str) -> dict[str, dict]:
    key = f"statement_substitution_state_{selected_order}"
    state = st.session_state.get(key)
    if not isinstance(state, dict):
        state = {}
        st.session_state[key] = state
    return state


def render(purchase_module, data) -> None:
    st = purchase_module.st
    orders = data["orders"].copy()
    order_items = data["order_items"].copy()
    products = data["products"].copy()
    statements, statement_items, price_history, _ = purchase_module.load_purchase_data()

    st.markdown("## 거래명세서 등록")
    st.caption(
        "표에서 이번 입고수량과 매입정보를 입력하세요. 체크박스는 대체할 품목을 선택할 때만 사용합니다."
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

    statement_number = _next_statement_number(statements, selected_order)
    with st.container(border=True):
        st.markdown("### 명세서 기본 정보")
        c1, c2, c3 = st.columns(3)
        c1.text_input(
            "거래명세서 번호",
            value=str(statement_number),
            disabled=True,
            help="이 발주서에 연결된 거래명세서 순서에 따라 자동으로 생성됩니다.",
        )
        statement_date = c1.date_input("거래명세서 일자", value=datetime.now().date())
        freight = c2.number_input("운송비(배송비)", min_value=0, value=0, step=1000)
        freight_checked = c2.checkbox("운송비 입력 완료", value=False)
        memo = c3.text_area("메모", height=88)

    st.markdown("### 품목별 입고정보 입력")
    editor_source = _editor_rows(
        purchase_module, order_rows, statements, statement_items, selected_order
    )
    if editor_source.empty:
        st.info("이 발주서에는 입고가 남은 품목이 없습니다.")
        return

    edited = st.data_editor(
        editor_source,
        use_container_width=True,
        hide_index=True,
        disabled=[
            "품목번호", "제품코드", "제품명", "규격", "포장단위",
            "발주수량", "누적입고", "남은수량",
        ],
        column_config={
            "선택": st.column_config.CheckboxColumn("선택", width="small", help="대체할 품목만 체크하세요."),
            "품목번호": None,
            "제품명": st.column_config.TextColumn("제품명", width="large"),
            "이번입고수량": st.column_config.NumberColumn("이번 입고수량", min_value=0, step=1),
            "매입단가": st.column_config.NumberColumn("매입단가", min_value=0, step=100),
            "제조번호": st.column_config.TextColumn("제조번호", width="medium"),
            "유통기한": st.column_config.TextColumn(
                "유통기한", help="예: 2028-03-01, 28.3.1, 20280301", width="medium"
            ),
            "현재 가격 적용": st.column_config.CheckboxColumn("현재 가격 적용"),
        },
        key=f"statement_items_table_{selected_order}",
    )

    selected_for_substitution = edited[edited["선택"] == True].copy()  # noqa: E712
    substitution_state = _substitution_state(st, selected_order)
    action_col, cancel_col, _ = st.columns([1, 1, 3])
    if action_col.button("대체", type="primary", use_container_width=True):
        if selected_for_substitution.empty:
            st.warning("대체할 품목을 먼저 체크하세요.")
        else:
            for _, row in selected_for_substitution.iterrows():
                item_no = str(int(row["품목번호"]))
                original_name = str(row.get("제품명", "") or "")
                current = substitution_state.get(item_no, {})
                substitution_state[item_no] = {
                    "제품명": str(current.get("제품명", original_name) or original_name),
                    "대체사유": str(current.get("대체사유", "") or ""),
                }
            st.session_state[f"statement_substitution_state_{selected_order}"] = substitution_state
            st.rerun()

    if cancel_col.button("대체 취소", use_container_width=True):
        if selected_for_substitution.empty:
            st.warning("대체를 취소할 품목을 먼저 체크하세요.")
        else:
            for _, row in selected_for_substitution.iterrows():
                substitution_state.pop(str(int(row["품목번호"])), None)
            st.session_state[f"statement_substitution_state_{selected_order}"] = substitution_state
            st.rerun()

    substitution_rows = []
    source_by_item = {
        str(int(row["품목번호"])): row
        for _, row in edited.iterrows()
    }
    for item_no, values in substitution_state.items():
        source = source_by_item.get(str(item_no))
        if source is None:
            continue
        substitution_rows.append({
            "품목번호": int(item_no),
            "원발주제품": str(source.get("제품명", "") or ""),
            "실제 입고제품": str(values.get("제품명", source.get("제품명", "")) or ""),
            "대체사유": str(values.get("대체사유", "") or ""),
        })

    if substitution_rows:
        st.markdown("#### 대체입고 품목")
        substitution_editor = st.data_editor(
            pd.DataFrame(substitution_rows),
            use_container_width=True,
            hide_index=True,
            disabled=["품목번호", "원발주제품"],
            column_config={
                "품목번호": None,
                "원발주제품": st.column_config.TextColumn(width="large"),
                "실제 입고제품": st.column_config.SelectboxColumn(
                    options=product_names, required=True, width="large"
                ),
                "대체사유": st.column_config.TextColumn(width="large"),
            },
            key=f"statement_substitution_table_{selected_order}",
        )
        substitution_state = {
            str(int(row["품목번호"])): {
                "제품명": str(row.get("실제 입고제품", "") or ""),
                "대체사유": str(row.get("대체사유", "") or "").strip(),
            }
            for _, row in substitution_editor.iterrows()
        }
        st.session_state[f"statement_substitution_state_{selected_order}"] = substitution_state

    preview_rows = []
    for _, row in edited.iterrows():
        quantity = _to_int(purchase_module, row.get("이번입고수량", 0))
        if quantity <= 0:
            continue
        remaining = _to_int(purchase_module, row.get("남은수량", 0))
        if quantity > remaining:
            st.warning(f'{row.get("제품명", "")}의 이번 입고수량은 남은수량을 초과할 수 없습니다.')
            continue

        item_no = str(int(row["품목번호"]))
        original_name = str(row.get("제품명", "") or "")
        original_code = str(row.get("제품코드", "") or "")
        original_spec = str(row.get("규격", "") or "")
        original_unit = str(row.get("포장단위", "") or "")
        substitution = substitution_state.get(item_no)
        actual_name = str(substitution.get("제품명", "") or "") if substitution else original_name
        reason = str(substitution.get("대체사유", "") or "").strip() if substitution else ""
        actual = product_lookup.get(actual_name)
        if actual is None and actual_name == original_name:
            actual = {
                "제품코드": original_code,
                "정식제품명": original_name,
                "규격": original_spec,
                "단위": original_unit,
            }
        if actual is None:
            continue

        price = _to_int(purchase_module, row.get("매입단가", 0))
        preview_rows.append({
            **actual,
            "발주수량": _to_int(purchase_module, row.get("발주수량", 0)),
            "입고수량": quantity,
            "매입단가": price,
            "상품금액": quantity * price,
            "출고단가": purchase_module.calc_sell_price(price),
            "가격적용여부": "Y" if bool(row.get("현재 가격 적용", True)) else "N",
            "원발주제품코드": original_code,
            "원발주제품명": original_name,
            "원발주규격": original_spec,
            "원발주단위": original_unit,
            "입고유형": "대체입고" if substitution else "정상입고",
            "대체사유": reason,
            "제조번호": str(row.get("제조번호", "") or "").strip(),
            "유통기한": str(row.get("유통기한", "") or "").strip(),
        })

    preview = pd.DataFrame(preview_rows)
    product_total = int(preview["상품금액"].sum()) if not preview.empty else 0
    a, b, c = st.columns(3)
    a.metric("상품 매입금액", f"{product_total:,}원")
    b.metric("운송비", f"{int(freight):,}원")
    c.metric("총 매입금액", f"{product_total + int(freight):,}원")

    if st.button("거래명세서 저장", type="primary", use_container_width=True):
        if preview.empty:
            st.warning("이번 입고수량이 1 이상인 품목을 입력하세요.")
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
            "명세서번호": str(statement_number),
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
        st.success(f"{statement_number}번 거래명세서를 저장했습니다: {sid}")
        st.rerun()
