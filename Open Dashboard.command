#!/bin/zsh
# Run from this folder even when opened by double-clicking in Finder.
cd -- "$(dirname -- "$0")" || exit 1
exec .venv/bin/python -m streamlit run dashboard.py --server.address 127.0.0.1 --server.headless false
