"""거래명세서 상세 조회와 개별 삭제 기능을 추가하는 실행 런처."""

import pandas as pd

import app_order_id_yy as current

purchase = current.purchase
base_app = current.base_app


def delete_statement(statement_id):
    """선택한 거래명세서와 연결 품목/가격이력을 함께 삭제합니다."""
    statement_id = str(statement_id)
    statements, statement_items, price_history, _ = purchase.load_purchase_data()

    statements = statements[statements["명세서ID"].astype(str) != statement_id]
    statement_items = statement_items[
        statement_items["명세서ID"].astype(str) != statement_id
    ]
    price_history = price_history[
        price_history["명세서ID"].astype(str) != statement_id
    ]

    purchase.save_table(
        purchase.STATEMENTS_FILE,
        statements,
        purchase.STATEMENT_COLUMNS,
    )
    purchase.save_table(
        purchase.STATEMENT_ITEMS_FILE,
        statement_items,
        purchase.STATEMENT_ITEM_COLUMNS,
    )
    purchase.save_table(
        purchase.PRICE_HISTORY_FILE,
        price_history,
        purchase.PRICE_HISTORY_COLUMNS,
    )


def page_statement_list_with_detail():
    """거래명세서 목록, 상세 품목, 삭제 기능을 제공합니다."""
    statements, statement_items, _, _ = purchase.load_purchase_data()
    base_app.st.markdown("## 거래명세서 내역")

    if statements.empty:
        base_app.st.info("등록된 거래명세서가 없습니다.")
        return

    detail = purchase.statement_detail_frame(statements, statement_items)
    detail = detail.sort_values(
        ["명세서일자", "등록일시"],
        ascending=False,
    ).reset_index(drop=True)

    summary = detail[[
        "명세서ID", "발주ID", "거래처명", "명세서번호", "명세서일자",
        "상품매입금액", "운송비", "총매입금액", "운송비상태",
    ]].copy()
    for col in ["상품매입금액", "운송비", "총매입금액"]:
        summary[col] = summary[col].apply(lambda value: f"{purchase.to_int(value):,}")

    base_app.st.dataframe(summary, use_container_width=True, hide_index=True)

    ids = detail["명세서ID"].astype(str).tolist()
    row_map = detail.set_index(detail["명세서ID"].astype(str)).to_dict("index")
    selected_id = base_app.st.selectbox(
        "상세 확인할 거래명세서",
        ids,
        format_func=lambda sid: (
            f'[{row_map[sid].get("거래처명", "")}] '
            f'{row_map[sid].get("명세서번호", "")}번 | '
            f'{row_map[sid].get("명세서일자", "")} | {sid}'
        ),
    )

    header = row_map[selected_id]
    items = statement_items[
        statement_items["명세서ID"].astype(str) == str(selected_id)
    ].copy()

    base_app.st.markdown("### 거래명세서 상세")
    c1, c2, c3, c4 = base_app.st.columns(4)
    c1.metric("거래처", str(header.get("거래처명", "")))
    c2.metric("명세서 번호", f'{header.get("명세서번호", "")}번')
    c3.metric("총 입고수량", f'{purchase.to_int(header.get("총입고수량", 0)):,}개')
    c4.metric("총 매입금액", f'{purchase.to_int(header.get("총매입금액", 0)):,}원')

    if items.empty:
        base_app.st.info("이 거래명세서에 저장된 품목이 없습니다.")
    else:
        for col in ["입고수량", "매입단가", "상품금액", "출고단가"]:
            items[col] = items[col].apply(purchase.to_int)

        item_view = items[[
            "정식제품명", "규격", "단위", "입고수량", "매입단가", "상품금액",
        ]].copy()
        item_view = item_view.rename(columns={
            "입고수량": "수량",
            "매입단가": "단가",
        })
        base_app.st.dataframe(item_view, use_container_width=True, hide_index=True)

    base_app.st.markdown("### 거래명세서 삭제")
    confirm = base_app.st.checkbox(
        "선택한 거래명세서를 삭제합니다.",
        key=f"delete_statement_confirm_{selected_id}",
    )
    if base_app.st.button(
        "선택한 거래명세서 삭제",
        type="primary",
        use_container_width=True,
        disabled=not confirm,
    ):
        delete_statement(selected_id)
        base_app.st.success("거래명세서와 연결된 품목 및 가격이력을 삭제했습니다.")
        base_app.st.rerun()


purchase.page_statement_list = page_statement_list_with_detail


if __name__ == "__main__":
    purchase.main()
