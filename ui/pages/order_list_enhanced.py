"""행 클릭으로 발주서를 선택하는 발주서 목록 화면."""
from __future__ import annotations

from pathlib import Path

from ui.pages import orders


def _selected_rows(event) -> list[int]:
    """Streamlit 버전에 따라 다른 선택 이벤트 형태를 안전하게 읽습니다."""
    if event is None:
        return []
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection", {})
    if isinstance(selection, dict):
        return list(selection.get("rows", []) or [])
    return list(getattr(selection, "rows", []) or [])


def render(core_app, data, purchase_module=None) -> None:
    st = core_app.st
    vendors = data["vendors"]
    headers = data["orders"]
    items = data["order_items"]

    st.markdown("## 발주서 목록")
    if headers.empty:
        st.info("발주서가 없습니다.")
        return

    display_headers = headers.copy().reset_index(drop=True)
    if "상태" not in display_headers.columns:
        display_headers["상태"] = "발주완료"

    status_by_order = orders._receipt_status_map(core_app, purchase_module, items)
    if status_by_order:
        display_headers["상태"] = display_headers.apply(
            lambda row: status_by_order.get(
                str(row.get("발주ID", "")),
                str(row.get("상태", "발주완료") or "발주완료"),
            ),
            axis=1,
        )

    st.caption("발주ID가 있는 행을 클릭하면 아래에 해당 발주서 내용이 표시됩니다.")
    event = st.dataframe(
        orders._style_status_column(display_headers),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="order_list_row_selection",
    )

    selected_rows = _selected_rows(event)
    if not selected_rows:
        st.info("내용을 확인할 발주서 행을 선택하세요.")
        return

    row_index = selected_rows[0]
    if row_index < 0 or row_index >= len(display_headers):
        st.warning("선택한 발주서를 확인할 수 없습니다.")
        return

    selected = str(display_headers.iloc[row_index].get("발주ID", ""))
    header_rows = headers[headers["발주ID"].astype(str) == selected]
    if header_rows.empty:
        st.warning("선택한 발주서가 현재 목록에 없습니다.")
        return

    header = header_rows.iloc[0]
    detail = items[items["발주ID"].astype(str) == selected].copy()
    st.markdown(f"### 선택한 발주서 · {selected}")
    if detail.empty:
        st.info("저장된 발주 품목이 없습니다.")
    else:
        cols = [
            column
            for column in ["제품코드", "정식제품명", "규격", "단위", "수량"]
            if column in detail.columns
        ]
        st.dataframe(detail[cols], use_container_width=True, hide_index=True)

    c1, c2, c3 = st.columns(3)
    if c1.button("복사하여 새 발주", use_container_width=True, key=f"copy_order_{selected}"):
        st.session_state.order_items = orders._normalise_items(core_app, detail)
        st.session_state.loaded_vendor_name = str(header.get("거래처명", ""))
        st.session_state.loaded_request_note = str(header.get("요청사항", ""))
        st.session_state.current_page = "발주 작성"
        st.rerun()

    if c2.button("삭제", use_container_width=True, key=f"delete_order_{selected}"):
        core_app.delete_order(selected)
        st.success("발주서와 연결 데이터가 삭제되었습니다.")
        st.rerun()

    vendor_row = vendors[
        vendors["거래처명"].astype(str) == str(header.get("거래처명", ""))
    ]
    if not vendor_row.empty:
        export = core_app.create_excel(
            vendor_row.iloc[0],
            orders._normalise_items(core_app, detail),
            header.get("요청사항", ""),
        )
        with open(export, "rb") as file:
            c3.download_button(
                "엑셀 다운로드",
                file,
                file_name=Path(export).name,
                use_container_width=True,
                key=f"download_order_{selected}",
            )

    if purchase_module is not None:
        orders._receipt_review(core_app, purchase_module, selected, detail)
