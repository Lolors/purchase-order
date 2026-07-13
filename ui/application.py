"""Streamlit UI entrypoint."""
from pathlib import Path

import streamlit as st

from config import APP_TITLE
from services.bootstrap import run


def main() -> None:
    """기존 핵심 앱의 페이지 설정을 유지하면서 제목만 현재 버전으로 통일합니다."""
    original_set_page_config = st.set_page_config

    def set_versioned_page_config(*args, **kwargs):
        kwargs["page_title"] = APP_TITLE
        return original_set_page_config(*args, **kwargs)

    st.set_page_config = set_versioned_page_config
    try:
        run(Path(__file__).resolve().parents[1])
    finally:
        st.set_page_config = original_set_page_config
