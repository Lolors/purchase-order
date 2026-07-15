"""파일 생성과 화면 미리보기를 분리한 발주서 미리보기."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _fingerprint(vendor, order_items, request_note: str, order_date: str) -> str:
    payload = {
        "vendor": {
            "name": str(vendor.get("거래처명", "") or ""),
            "address": str(vendor.get("배송지", "") or ""),
            "phone": str(vendor.get("연락처", "") or ""),
        },
        "items": [
            {
                "code": str(item.get("제품코드", "") or ""),
                "name": str(item.get("정식제품명", item.get("제품명", "")) or ""),
                "spec": str(item.get("규격", "") or ""),
                "unit": str(item.get("포장단위", item.get("단위", "")) or ""),
                "quantity": int(float(item.get("수량", 0) or 0)),
            }
            for item in order_items or []
        ],
        "note": str(request_note or ""),
        "date": str(order_date or ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def render(core_app, vendor, order_items, request_note, order_date=None) -> None:
    """미리보기 변경만으로는 어떤 파일도 생성하지 않습니다."""
    st = core_app.st
    order_date = str(order_date or "")
    fingerprint = _fingerprint(vendor, order_items, request_note, order_date)

    top_left, top_excel, top_pdf, top_png = st.columns([2.6, 0.55, 0.55, 0.55])
    with top_left:
        st.markdown('<div class="preview-title">발주서 미리보기</div>', unsafe_allow_html=True)

    with top_excel:
        excel_state = st.session_state.get("preview_excel_export", {})
        excel_path = Path(str(excel_state.get("path", "")))
        excel_ready = excel_state.get("fingerprint") == fingerprint and excel_path.exists()
        if excel_ready:
            with open(excel_path, "rb") as file:
                st.download_button(
                    "XLS",
                    file,
                    file_name=excel_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="preview_excel_download_ready",
                    help="엑셀 내려받기",
                )
        elif st.button(
            "XLS",
            use_container_width=True,
            key="preview_excel_generate",
            help="엑셀 생성",
        ):
            if not order_items:
                st.warning("엑셀로 저장할 발주 품목이 없습니다.")
            else:
                path = Path(core_app.create_excel(vendor, order_items, request_note, order_date))
                st.session_state["preview_excel_export"] = {
                    "fingerprint": fingerprint,
                    "path": str(path),
                }
                st.rerun()

    with top_pdf:
        pdf_state = st.session_state.get("preview_pdf_export", {})
        pdf_path = Path(str(pdf_state.get("path", "")))
        pdf_ready = pdf_state.get("fingerprint") == fingerprint and pdf_path.exists()
        if pdf_ready:
            with open(pdf_path, "rb") as file:
                st.download_button(
                    "PDF",
                    file,
                    file_name=pdf_path.name,
                    mime="application/pdf",
                    use_container_width=True,
                    key="preview_pdf_download_ready",
                    help="PDF 내려받기",
                )
        elif st.button("PDF", use_container_width=True, key="preview_pdf_generate", help="PDF 생성"):
            try:
                with st.spinner("PDF 생성 중..."):
                    path = Path(core_app.create_preview_pdf(vendor, order_items, request_note, order_date))
                st.session_state["preview_pdf_export"] = {
                    "fingerprint": fingerprint,
                    "path": str(path),
                }
                st.session_state.pop("preview_capture_error", None)
                st.rerun()
            except Exception as exc:
                st.session_state["preview_capture_error"] = str(exc)

    with top_png:
        png_state = st.session_state.get("preview_png_export", {})
        png_path = Path(str(png_state.get("path", "")))
        png_ready = png_state.get("fingerprint") == fingerprint and png_path.exists()
        if png_ready:
            with open(png_path, "rb") as file:
                st.download_button(
                    "PNG",
                    file,
                    file_name=png_path.name,
                    mime="image/png",
                    use_container_width=True,
                    key="preview_png_download_ready",
                    help="PNG 내려받기",
                )
        elif st.button("PNG", use_container_width=True, key="preview_png_generate", help="PNG 생성"):
            try:
                with st.spinner("PNG 생성 중..."):
                    path = Path(core_app.create_preview_image(vendor, order_items, request_note, order_date))
                st.session_state["preview_png_export"] = {
                    "fingerprint": fingerprint,
                    "path": str(path),
                }
                st.session_state.pop("preview_capture_error", None)
                st.rerun()
            except Exception as exc:
                st.session_state["preview_capture_error"] = str(exc)

    capture_error = st.session_state.get("preview_capture_error")
    if capture_error:
        st.error(f"PDF/PNG 캡처 생성에 실패했습니다.\n\n오류내용: {capture_error}")

    html = core_app.render_order_html(
        vendor,
        order_items,
        request_note,
        order_date=order_date,
    )
    core_app.components.html(html, height=790, scrolling=True)
