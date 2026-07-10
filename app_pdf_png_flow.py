"""
PDF/PNG 다운로드 흐름 개선 런처.

기존 app.py를 그대로 불러온 뒤 미리보기 내보내기 함수만 교체합니다.
- PDF/PNG 버튼을 '생성'과 '저장'으로 분리
- 생성 성공 메시지와 저장 폴더 표시
- 발주 내용이 바뀌면 이전 PDF/PNG 다운로드 상태 초기화
- 생성 후 st.rerun() 없이 같은 화면에서 바로 저장 버튼 표시
- 엑셀/PDF/PNG 저장 안내 메시지는 3초 뒤 자동으로 숨김
- 발주서 품목 표 순서는 No. / 제품코드 / 제품명 / 규격 / 수량 / 단위로 표시
- 요청사항이 비어 있으면 발주서 미리보기에서 요청사항 박스를 숨김
"""

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from openpyxl import load_workbook

import app as base_app


EXPORT_MESSAGE_SECONDS = 3
ORIGINAL_CREATE_EXCEL = base_app.create_excel


def hide_empty_request_box(html, request_note):
    """요청사항이 없으면 요청사항 박스를 표시하지 않습니다."""
    if str(request_note or "").strip():
        return html
    return re.sub(
        r"\s*<div class=\"request\">\s*<b>요청사항</b><br>\s*-\s*</div>\s*",
        "\n",
        html,
        flags=re.DOTALL,
    )


def render_order_html(vendor, order_items, request_note, order_id=None, order_date=None):
    """발주서 미리보기 HTML을 수량/단위 순서로 직접 렌더링합니다."""
    template = base_app.TEMPLATE_FILE.read_text(encoding="utf-8") if base_app.TEMPLATE_FILE.exists() else base_app.DEFAULT_TEMPLATE
    logo_b64 = base_app.get_logo_base64()

    order_id = order_id or f"PO-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    order_date = order_date or datetime.now().strftime("%Y-%m-%d")

    template = template.replace(
        "<th>규격</th>\n                <th>단위</th>\n                <th>수량</th>",
        "<th>규격</th>\n                <th>수량</th>\n                <th>단위</th>",
    )

    rows_html = ""
    for idx, item in enumerate(order_items, 1):
        rows_html += f"""
        <tr>
            <td>{idx}</td>
            <td>{item.get("제품코드", "")}</td>
            <td class="left">{item.get("정식제품명", "")}</td>
            <td>{item.get("규격", "")}</td>
            <td>{base_app.fmt_int(item.get("수량", 0))}</td>
            <td>{item.get("단위", "")}</td>
        </tr>
        """

    if not rows_html:
        rows_html = '<tr><td colspan="6" class="empty">발주 품목이 없습니다.</td></tr>'

    total_count, total_qty = base_app.calc_totals(order_items)

    if logo_b64:
        template = template.replace("{% if_logo %}", "").replace("{% else_logo %}", "<!--").replace("{% endif_logo %}", "-->")
    else:
        template = template.replace("{% if_logo %}", "<!--").replace("{% else_logo %}", "-->").replace("{% endif_logo %}", "")

    html = (
        template
        .replace("{{LOGO_BASE64}}", logo_b64)
        .replace("{{ORDER_ID}}", order_id)
        .replace("{{ORDER_DATE}}", order_date)
        .replace("{{COMPANY_NAME}}", base_app.COMPANY["상호"])
        .replace("{{COMPANY_OWNER}}", base_app.COMPANY["대표"])
        .replace("{{COMPANY_ADDRESS}}", base_app.COMPANY["주소"])
        .replace("{{COMPANY_PHONE}}", base_app.COMPANY["연락처"])
        .replace("{{COMPANY_FAX}}", base_app.COMPANY["팩스"])
        .replace("{{COMPANY_REGNO}}", base_app.COMPANY["등록번호"])
        .replace("{{VENDOR_NAME}}", str(vendor.get("거래처명", "")))
        .replace("{{VENDOR_ADDRESS}}", str(vendor.get("배송지", "")))
        .replace("{{VENDOR_PHONE}}", str(vendor.get("연락처", "")))
        .replace("{{ITEM_ROWS}}", rows_html)
        .replace("{{TOTAL_COUNT}}", base_app.fmt_int(total_count))
        .replace("{{TOTAL_QTY}}", base_app.fmt_int(total_qty))
        .replace("{{REQUEST_NOTE}}", request_note or "")
    )
    return hide_empty_request_box(html, request_note)


def create_excel(vendor, order_items, request_note, order_date=None):
    """엑셀 저장 파일도 미리보기와 같은 수량/단위 순서로 맞춥니다."""
    path = ORIGINAL_CREATE_EXCEL(vendor, order_items, request_note, order_date)
    wb = load_workbook(path)
    ws = wb.active

    start_row = 14
    ws.cell(start_row, 5, "수량")
    ws.cell(start_row, 6, "단위")

    for idx, item in enumerate(order_items, 1):
        row_num = start_row + idx
        ws.cell(row_num, 5, base_app.safe_int(item.get("수량", 0)))
        ws.cell(row_num, 6, item.get("단위", ""))

    if not str(request_note or "").strip():
        total_row = start_row + len(order_items) + 2
        ws.cell(total_row + 3, 1, "")
        ws.cell(total_row + 4, 1, "")

    wb.save(path)
    return path


base_app.render_order_html = render_order_html
base_app.create_excel = create_excel


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


def set_export_message(message):
    st.session_state["preview_export_message"] = message
    st.session_state["preview_export_message_time"] = time.time()


def reset_preview_export_state():
    for key in [
        "preview_pdf_path",
        "preview_png_path",
        "preview_capture_error",
        "preview_export_message",
        "preview_export_message_time",
    ]:
        st.session_state.pop(key, None)


def show_temporary_export_message():
    capture_error = st.session_state.get("preview_capture_error")
    export_message = st.session_state.get("preview_export_message")
    message_time = st.session_state.get("preview_export_message_time")

    if capture_error:
        st.error(
            "PDF/PNG 캡쳐 생성에 실패했습니다. 앱을 실행한 Python 환경에서 Playwright와 Chromium이 설치되어 있는지 확인하세요.\n\n"
            "확인 명령:\n"
            "python -c \"from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); print('OK'); b.close(); p.stop()\"\n\n"
            f"오류내용: {capture_error}"
        )
        return

    if not export_message or not message_time:
        return

    elapsed = time.time() - float(message_time)
    if elapsed >= EXPORT_MESSAGE_SECONDS:
        st.session_state.pop("preview_export_message", None)
        st.session_state.pop("preview_export_message_time", None)
        return

    placeholder = st.empty()
    with placeholder.container():
        st.success(export_message)
        st.caption(f"저장 폴더: {base_app.PDF_OUTPUT}")

    time.sleep(max(0, EXPORT_MESSAGE_SECONDS - elapsed))
    placeholder.empty()
    st.session_state.pop("preview_export_message", None)
    st.session_state.pop("preview_export_message_time", None)


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
            on_click=set_export_message,
            args=(f"엑셀 저장 준비 완료: {excel_path}",),
        )

    with top_pdf:
        if st.button("PDF 생성", use_container_width=True, key="preview_pdf_generate", help="PDF 파일 생성"):
            try:
                with st.spinner("PDF 생성 중..."):
                    pdf_path = base_app.create_preview_pdf(vendor, order_items, request_note, order_date)
                st.session_state["preview_pdf_path"] = str(pdf_path)
                set_export_message(f"PDF 생성 완료: {pdf_path}")
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
                on_click=set_export_message,
                args=(f"PDF 저장 준비 완료: {pdf_path}",),
            )

    with top_png:
        if st.button("PNG 생성", use_container_width=True, key="preview_png_generate", help="PNG 파일 생성"):
            try:
                with st.spinner("PNG 생성 중..."):
                    png_path = base_app.create_preview_image(vendor, order_items, request_note, order_date)
                st.session_state["preview_png_path"] = str(png_path)
                set_export_message(f"PNG 생성 완료: {png_path}")
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
                on_click=set_export_message,
                args=(f"PNG 저장 준비 완료: {png_path}",),
            )

    show_temporary_export_message()

    html = base_app.render_order_html(vendor, order_items, request_note, order_date=order_date)
    components.html(html, height=790, scrolling=True)


base_app.render_purchase_preview = render_purchase_preview

if __name__ == "__main__":
    base_app.main()
