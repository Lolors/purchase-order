"""Streamlit UI entrypoint."""
from pathlib import Path

from services.bootstrap import run


def main() -> None:
    run(Path(__file__).resolve().parents[1])
