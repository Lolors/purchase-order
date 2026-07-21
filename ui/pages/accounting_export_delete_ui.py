"""월마감 화면에서 중복 거래명세서를 안전하게 삭제할 수 있게 하는 보정 레이어."""
from __future__ import annotations

import pandas as pd

from ui.pages import accounting_export as base
from ui.pages import purchases


def _to_int(purchase_module, value) -> int:
    return purchase_module.to_int(value)


def _statement_options(purchase_module, year: int, month: int):
    statements, statement_items, price_history, _ = purchase_module.load_purchase_data()
    if statements.empty:
        return statements, statement_items, price_history, [], {}

    working = statements.copy()
    working["_date"] = pd.to_datetime(working["명세서일자"], errors="coerce")
    working = working[
        (working["_date"].dt.year == int(year))
        & (working["_date"].dt.month == int(month))
    ].copy()
    if working.empty:
        return statements, statement_items, price_history, [], {}

    labels = []
    lookup = {}
    for _, statement in working.sort_values(["명세서일자", "등록일시"]).iterrows():
        statement_id = str(statement.get("명세서ID", ""))
        items = statement_items[
            statement_items["명세서ID"].astype(str) == statement_id
        ]
        product_amount = int(
            items["상품금액"].apply(lambda value: _to_int(purchase_module, value)).sum()
        ) if not items.empty else 0
        freight = _to_int(purchase_module, statement.get("운송비", 0))
        total = product_amount + freight
        label = (
            f'[{statement.get("거래처명", "")}] '
            f'{statement.get("명세서일자", "")} · '
            f'번호 {statement.get("명세서번호", "")} · '
            f'{total:,}원 · {statement_id}'
        )
        labels.append(label)
        lookup[label] = statement_id

    return statements, statement_items, price_history, labels, lookup


def render(purchase_module, data) -> None:
    st = purchase_module.st
    base.render(purchase_module, data)

    st.markdown("---")
    st.markdown("### 중복 거래명세서 삭제")
    st.caption("잘못 중복 등록된 거래명세서를 선택하면 해당 품목과 가격이력도 함께 삭제됩니다.")

    today = pd.Timestamp.now()
    c1, c2 = st.columns(2)
    year = int(c1.number_input(
        "삭제 대상 연도",
        min_value=2020,
        max_value=2100,
        value=int(st.session_state.get("month_close_delete_year", today.year)),
        step=1,
        key="month_close_delete_year",
    ))
    month = int(c2.number_input(
        "삭제 대상 월",
        min_value=1,
        max_value=12,
        value=int(st.session_state.get("month_close_delete_month", today.month)),
        step=1,
        key="month_close_delete_month",
    ))

    statements, statement_items, price_history, options, lookup = _statement_options(
        purchase_module, year, month
    )
    if not options:
        st.info("선택한 월에 삭제할 거래명세서가 없습니다.")
        return

    selected_label = st.selectbox(
        "삭제할 거래명세서",
        options,
        key="month_close_delete_statement",
    )
    selected_id = lookup[selected_label]

    confirm_col, delete_col = st.columns([3, 1])
    confirmed = confirm_col.checkbox(
        "선택한 거래명세서를 삭제하겠습니다.",
        key=f"month_close_delete_confirm_{selected_id}",
    )
    if delete_col.button(
        "거래명세서 삭제",
        type="primary",
        use_container_width=True,
        disabled=not confirmed,
        key=f"month_close_delete_button_{selected_id}",
    ):
        purchases._delete_statement(
            purchase_module,
            selected_id,
            statements,
            statement_items,
            price_history,
        )
        st.success(f"거래명세서를 삭제했습니다: {selected_id}")
        st.rerun()
