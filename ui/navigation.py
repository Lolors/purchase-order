"""Sidebar navigation for the 1.0 application."""
from __future__ import annotations

from config.version import APP_TITLE


MENU_GROUPS = [
    (None, ["발주 작성", "임시저장 목록", "발주서 목록"]),
    ("매입 관리", ["거래명세서 등록", "거래명세서 내역", "월별 매입 현황"]),
    ("기초 관리", ["거래처 관리", "제품 관리", "별칭 관리"]),
]


def render_sidebar(st) -> str:
    """Render the sidebar and return the selected page name."""
    st.sidebar.markdown(
        '<div class="sidebar-title">발주관리 시스템</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.caption(APP_TITLE)

    if st.session_state.current_page == "최근 발주 내역":
        st.session_state.current_page = "발주서 목록"

    def menu(name: str) -> None:
        active = st.session_state.current_page == name
        if st.sidebar.button(
            name,
            key=f"menu_{name}",
            use_container_width=True,
            type="primary" if active else "secondary",
        ):
            st.session_state.current_page = name
            st.rerun()

    for heading, pages in MENU_GROUPS:
        if heading:
            st.sidebar.markdown("---")
            st.sidebar.markdown(f"**{heading}**")
        for page in pages:
            menu(page)

    return st.session_state.current_page
