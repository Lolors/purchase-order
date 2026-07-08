"""
PDF/PNG 다운로드 흐름 개선 런처.

기존 app.py를 그대로 불러온 뒤 미리보기 내보내기 함수만 교체합니다.
- PDF/PNG 버튼을 '생성'과 '저장'으로 분리
- 생성 성공 메시지와 저장 폴더 표시
- 발주 내용이 바뀌면 이전 PDF/PNG 다운로드 상태 초기화
- 생성 후 st.rerun() 없이 같은 화면에서 바로 저장 버튼 표시
"""

import hashlib
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import app as base_app


def make_preview_signature(vendor, order_items, request_note, order_date):
    vendor_payload = {
        "거래처명": str(vendor.get("거래처명", "")),
        "담당자": str(vendor.get("담당자", "")),
        "연락처": str(vendor.get("연락처", "")),
        "배송지": str(vendor.get("배송지", "")),
    }
    payload = {
        "vendor": vendor_payload,
        "items": order_items,
        "request_note": request_note or "",
        "order_date": str(order_date or ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def reset_preview_export_state():
    for key in [
        "preview_pdf_path",
        "preview_png_path",
        "preview_capture_error",
        "preview_export_message",
    ]:
        st.session_state.pop(key, None)


def render_purchase_preview(vendor, order_items, request_note, order_date=None):
    preview_signature = make_preview_signature(vendor, order_items, request_note, order_date)
    if st.session_state.get("preview_export_signature") != preview_signature:
        reset_preview_export_state()
        st.session_state["preview_export_signature"] = preview_signature

    top_left, top_excel, top_pdf, top_png = st.columns([2.25, 0.75, 0.85, 0.85])

    with top_left:
        st.markdown('<div class="preview-title">발주서 미리보기</div>', unsafe_allow_html=True)

    with top_excel:
        excel_path = base_app.create_excel(vendor, order_items, request_note, order_date)
        st.download_button(
            "엑셀 저장",
            excel_path.read_bytes(),
            file_name=excel_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"preview_xls_{len(order_items)}_{order_date}",
            help="엑셀 내려받기",
        )

    with top_pdf:
        if st.button("PDF 생성", use_container_width=True, key="preview_pdf_generate", help="PDF 파일 생성"):
            try:
                with st.spinner("PDF 생성 중..."):
                    pdf_path = base_app.create_preview_pdf(vendor, order_items, request_note, order_date)
                st.session_state["preview_pdf_path"] = str(pdf_path)
                st.session_state["preview_export_message"] = f"PDF 생성 완료: {pdf_path}"
                st.session_state.pop("preview_capture_error", None)
            except Exception as e:
                st.session_state["preview_capture_error"] = str(e)
                st.session_state.pop("preview_pdf_path", None)

        pdf_saved_path = st.session_state.get("preview_pdf_path")
        if pdf_saved_path and Path(pdf_saved_path).exists():
            pdf_path = Path(pdf_saved_path)
            st.download_button(
                "PDF 저장",
                pdf_path.read_bytes(),
                file_name=pdf_path.name,
                mime="application/pdf",
                use_container_width=True,
                key=f"preview_pdf_download_{pdf_path.name}",
                help="생성된 PDF 내려받기",
            )

    with top_png:
        if st.button("PNG 생성", use_container_width=True, key="preview_png_generate", help="PNG 파일 생성"):
            try:
                with st.spinner("PNG 생성 중..."):
                    png_path = base_app.create_preview_image(vendor, order_items, request_note, order_date)
                st.session_state["preview_png_path"] = str(png_path)
                st.session_state["preview_export_message"] = f"PNG 생성 완료: {png_path}"
                st.session_state.pop("preview_capture_error", None)
            except Exception as e:
                st.session_state["preview_capture_error"] = str(e)
                st.session_state.pop("preview_png_path", None)

        png_saved_path = st.session_state.get("preview_png_path")
        if png_saved_path and Path(png_saved_path).exists():
            png_path = Path(png_saved_path)
            st.download_button(
                "PNG 저장",
                png_path.read_bytes(),
                file_name=png_path.name,
                mime="image/png",
                use_container_width=True,
                key=f"preview_png_download_{png_path.name}",
                help="생성된 PNG 내려받기",
            )

    capture_error = st.session_state.get("preview_capture_error")
    export_message = st.session_state.get("preview_export_message")
    if capture_error:
        st.error(
            "PDF/PNG 캡쳐 생성에 실패했습니다. 앱을 실행한 Python 환경에서 Playwright와 Chromium이 설치되어 있는지 확인하세요.\n\n"
            "확인 명령:\n"
            "python -c \"from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); print('OK'); b.close(); p.stop()\"\n\n"
            f"오류내용: {capture_error}"
        )
    elif export_message:
        st.success(export_message)
        st.caption(f"저장 폴더: {base_app.PDF_OUTPUT}")

    html = base_app.render_order_html(vendor, order_items, request_note, order_date=order_date)
    components.html(html, height=790, scrolling=True)


base_app.render_purchase_preview = render_purchase_preview

if __name__ == "__main__":
    base_app.main()
