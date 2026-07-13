"""제품과 별칭을 SQLite에서 읽고 저장하는 저장소 모듈."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

import pandas as pd

from db_migration import normalize_product_code

PRODUCT_COLUMNS = ["제품유형", "제품코드", "제품명", "규격", "포장단위"]
ALIAS_COLUMNS = ["거래처명", "별칭", "제품코드"]


def _db_path(data_dir: Path) -> Path:
    return Path(data_dir) / "purchase_order.db"


def _connect(data_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(data_dir), timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def load_products(data_dir: Path) -> pd.DataFrame:
    with _connect(data_dir) as conn:
        rows = conn.execute(
            """
            SELECT product_type, product_code, product_name, specification, packaging_unit
            FROM products
            ORDER BY product_name, product_code
            """
        ).fetchall()

    result = pd.DataFrame(rows, columns=PRODUCT_COLUMNS)
    if result.empty:
        return pd.DataFrame(columns=PRODUCT_COLUMNS)
    result["제품코드"] = result["제품코드"].map(normalize_product_code)
    return result.fillna("")


def save_products(data_dir: Path, products: pd.DataFrame) -> None:
    clean = products.copy().fillna("")
    if "제품명" not in clean.columns:
        clean["제품명"] = clean.get("정식제품명", "")
    if "포장단위" not in clean.columns:
        clean["포장단위"] = clean.get("단위", "")
    if "제품유형" not in clean.columns:
        clean["제품유형"] = ""
    for col in PRODUCT_COLUMNS:
        if col not in clean.columns:
            clean[col] = ""
        clean[col] = clean[col].astype(str).str.strip()
    clean["제품코드"] = clean["제품코드"].map(normalize_product_code)
    clean = clean[(clean["제품코드"] != "") & (clean["제품명"] != "")]
    clean = clean.drop_duplicates("제품코드", keep="last")

    rows = [
        tuple(row[col] for col in PRODUCT_COLUMNS)
        for _, row in clean.iterrows()
    ]

    with _connect(data_dir) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM products")
        conn.executemany(
            """
            INSERT INTO products(product_type, product_code, product_name, specification, packaging_unit)
            VALUES(?,?,?,?,?)
            """,
            rows,
        )
        conn.commit()


def load_aliases(data_dir: Path) -> pd.DataFrame:
    with _connect(data_dir) as conn:
        rows = conn.execute(
            """
            SELECT vendor_name, alias, product_code
            FROM aliases
            ORDER BY vendor_name, alias, product_code
            """
        ).fetchall()

    result = pd.DataFrame(rows, columns=ALIAS_COLUMNS)
    if result.empty:
        return pd.DataFrame(columns=ALIAS_COLUMNS)
    result["제품코드"] = result["제품코드"].map(normalize_product_code)
    return result.fillna("")


def save_aliases(data_dir: Path, aliases: pd.DataFrame) -> None:
    clean = aliases.copy().fillna("")
    for col in ALIAS_COLUMNS:
        if col not in clean.columns:
            clean[col] = ""
        clean[col] = clean[col].astype(str).str.strip()
    clean["제품코드"] = clean["제품코드"].map(normalize_product_code)
    clean = clean[(clean["별칭"] != "") & (clean["제품코드"] != "")]
    clean.loc[clean["거래처명"] == "", "거래처명"] = "전체"
    clean = clean.drop_duplicates(ALIAS_COLUMNS, keep="last")

    rows = [tuple(row[col] for col in ALIAS_COLUMNS) for _, row in clean.iterrows()]
    with _connect(data_dir) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM aliases")
        conn.executemany(
            "INSERT INTO aliases(vendor_name, alias, product_code) VALUES(?,?,?)",
            rows,
        )
        conn.commit()


def activate(base_app) -> None:
    """기존 앱의 제품·별칭 읽기/저장을 SQLite 방식으로 교체합니다."""
    original_load_data: Callable = base_app.load_data

    def load_data_from_db():
        vendors, _, _, drafts, draft_items, orders, order_items = original_load_data()
        products = load_products(base_app.DATA)
        products["정식제품명"] = products["제품명"]
        products["단위"] = products["포장단위"]
        aliases = load_aliases(base_app.DATA)
        return vendors, products, aliases, drafts, draft_items, orders, order_items

    def save_products_to_db(df: pd.DataFrame) -> None:
        save_products(base_app.DATA, df)

    def save_aliases_to_db(df: pd.DataFrame) -> None:
        save_aliases(base_app.DATA, df)

    base_app.load_data = load_data_from_db
    base_app.save_products = save_products_to_db
    base_app.save_aliases = save_aliases_to_db
