"""별칭 수정 저장 시 체크된 행이 삭제되는 문제를 수정하는 실행 런처."""

import pandas as pd
import streamlit as st

import app_pdf_png_flow as flow

base_app = flow.base_app


def normalize_alias_table(df):
    """별칭 편집 데이터를 저장 가능한 형태로 정리합니다."""
    columns = ["거래처명", "별칭", "제품코드"]
    clean = df.copy()

    for col in columns:
        if col not in clean.columns:
            clean[col] = ""

    clean = clean[columns].fillna("")
    for col in columns:
        clean[col] = clean[col].astype(str).str.strip()

    clean = clean[
        clean[columns].apply(lambda row: any(str(value).strip() for value in row), axis=1)
    ]
    clean = clean[(clean["별칭"] != "") & (clean["제품코드"] != "")]
    return clean.reset_index(drop=True)


def page_alias_manage(vendors, products, aliases):
    st.markdown("## 별칭 관리")
    st.caption("거래처가 말하는 약칭/별칭을 정식 제품에 연결합니다.")

    vendor_options = ["전체"] + vendors["거래처명"].drop_duplicates().tolist()

    with st.container(border=True):
        st.markdown("### 신규 별칭 추가")

        selected_vendor = st.selectbox("거래처", vendor_options, key="alias_new_vendor")
        new_alias = st.text_input("별칭", key="alias_new_name")

        product_options = products["제품코드"].tolist()
        selected_product_code = st.selectbox(
            "연결 제품",
            product_options,
            format_func=lambda code: (
                f'{products.loc[products["제품코드"] == code, "정식제품명"].iloc[0]} ({code})'
                if code in products["제품코드"].tolist()
                else code
            ),
            key="alias_new_product",
        ) if product_options else None

        if st.button("별칭 추가", type="primary", use_container_width=True):
            if not new_alias.strip():
                st.warning("별칭을 입력하세요.")
            elif not selected_product_code:
                st.warning("연결할 제품을 선택하세요.")
            else:
                new_row = pd.DataFrame([{
                    "거래처명": selected_vendor,
                    "별칭": new_alias.strip(),
                    "제품코드": selected_product_code,
                }])
                aliases = pd.concat([aliases, new_row], ignore_index=True)
                base_app.save_aliases(normalize_alias_table(aliases))
                st.success("별칭을 추가했습니다.")
                st.rerun()

    st.markdown("### 별칭 목록 수정")

    if aliases.empty:
        st.info("등록된 별칭이 없습니다.")
        return

    merged = aliases.merge(
        products[["제품코드", "정식제품명", "규격", "단위"]],
        on="제품코드",
        how="left",
    )

    view = merged[["거래처명", "별칭", "제품코드", "정식제품명", "규격", "단위"]].copy()
    view["삭제"] = False
    view = view[["삭제", "거래처명", "별칭", "제품코드", "정식제품명", "규격", "단위"]]

    edited = st.data_editor(
        view,
        use_container_width=True,
        hide_index=True,
        disabled=["정식제품명", "규격", "단위"],
        column_config={
            "삭제": st.column_config.CheckboxColumn("삭제"),
            "거래처명": st.column_config.SelectboxColumn("거래처명", options=vendor_options),
            "제품코드": st.column_config.TextColumn("제품코드"),
        },
        key="alias_editor",
    )

    c1, c2 = st.columns(2)

    with c1:
        if st.button("별칭 수정 저장", use_container_width=True):
            # 수정 저장은 삭제 체크 여부를 무시하고 모든 편집 행을 유지합니다.
            clean = normalize_alias_table(edited[["거래처명", "별칭", "제품코드"]])
            base_app.save_aliases(clean)
            st.success("별칭 정보를 저장했습니다.")
            st.rerun()

    with c2:
        if st.button("선택 별칭 삭제", use_container_width=True):
            # 실제 삭제는 이 버튼을 눌렀을 때만 수행합니다.
            remaining = edited[edited["삭제"] != True]
            clean = normalize_alias_table(remaining[["거래처명", "별칭", "제품코드"]])
            base_app.save_aliases(clean)
            st.success("선택한 별칭을 삭제했습니다.")
            st.rerun()


base_app.page_alias_manage = page_alias_manage


if __name__ == "__main__":
    base_app.main()
