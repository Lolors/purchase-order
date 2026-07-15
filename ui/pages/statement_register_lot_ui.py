"""거래명세서 LOT 분할 입력 UI 보정 레이어."""
from __future__ import annotations

import inspect

import pandas as pd

from ui.pages import statement_register_substitution as base


def _blank_or_int(purchase_module, value):
    if value is None or str(value).strip() == "":
        return ""
    return base._to_int(purchase_module, value)


def _sync_receipt_rows(st, purchase_module, selected_order, selected_lookup, substitution_state):
    rows = base._receipt_rows_state(st, selected_order)
    selected_item_nos = set(selected_lookup)
    rows = [dict(row) for row in rows if str(row.get("품목번호", "")) in selected_item_nos]

    existing_item_nos = {str(row.get("품목번호", "")) for row in rows}
    for item_no, original in selected_lookup.items():
        if item_no not in existing_item_nos:
            rows.append({
                "행번호": base._next_receipt_row_id(st, selected_order),
                "품목번호": int(item_no),
                "입고수량": base._to_int(purchase_module, original.get("남은수량", 0)),
                "매입단가": "",
                "제조번호": "",
                "유통기한": "",
                "현재 가격 적용": True,
            })

    for row in rows:
        item_no = str(row.get("품목번호", ""))
        original = selected_lookup.get(item_no)
        if original is None:
            continue
        actual = base._actual_for_item(original, substitution_state.get(item_no))
        row["제품명"] = str(actual.get("정식제품명", "") or original.get("제품명", ""))
        row["규격"] = str(actual.get("규격", "") or original.get("규격", ""))
        row["복사/삭제"] = False
        row["입고수량"] = base._to_int(purchase_module, row.get("입고수량", 0))
        row["매입단가"] = _blank_or_int(purchase_module, row.get("매입단가", ""))
        row["제조번호"] = str(row.get("제조번호", "") or "")
        row["유통기한"] = str(row.get("유통기한", "") or "")
        row["현재 가격 적용"] = base._normalise_bool(row.get("현재 가격 적용", True))

    st.session_state[f"statement_receipt_rows_{selected_order}"] = rows
    return rows


def _store_entered_rows(st, selected_order: str, entered: pd.DataFrame) -> list[dict]:
    rows = []
    if entered is not None and not entered.empty:
        for _, row in entered.iterrows():
            price_value = row.get("매입단가", "")
            rows.append({
                "행번호": int(row.get("행번호", 0)),
                "품목번호": int(row.get("품목번호", 0)),
                "입고수량": int(float(row.get("입고수량", 0) or 0)),
                "매입단가": "" if price_value is None or str(price_value).strip() == "" else int(float(price_value)),
                "제조번호": str(row.get("제조번호", "") or "").strip(),
                "유통기한": str(row.get("유통기한", "") or "").strip(),
                "현재 가격 적용": base._normalise_bool(row.get("현재 가격 적용", True)),
            })
    st.session_state[f"statement_receipt_rows_{selected_order}"] = rows
    return rows


base._sync_receipt_rows = _sync_receipt_rows
base._store_entered_rows = _store_entered_rows


_render_source = inspect.getsource(base.render)
_render_source = _render_source.replace(
    '"매입단가": _to_int(purchase_module, row.get("매입단가", 0)),',
    '"매입단가": row.get("매입단가", ""),',
)
_render_source = _render_source.replace(
    '''            for row in list(stored_rows):
                if int(row.get("행번호", 0)) not in selected_row_ids:
                    continue
                copied = dict(row)
                copied["행번호"] = _next_receipt_row_id(st, selected_order)
                copied["입고수량"] = 0
                copied["제조번호"] = ""
                copied["유통기한"] = ""
                stored_rows.append(copied)''',
    '''            next_rows = []
            for row in stored_rows:
                next_rows.append(row)
                if int(row.get("행번호", 0)) not in selected_row_ids:
                    continue
                copied = dict(row)
                copied["행번호"] = _next_receipt_row_id(st, selected_order)
                copied["입고수량"] = 0
                copied["제조번호"] = ""
                copied["유통기한"] = ""
                next_rows.append(copied)
            stored_rows = next_rows''',
)

_namespace = dict(base.__dict__)
exec(_render_source, _namespace)
render = _namespace["render"]
item_key = base.item_key
