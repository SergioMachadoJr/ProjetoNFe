#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$BASE_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r "$BASE_DIR/requirements.txt" >/dev/null

python "$BASE_DIR/src/captura_nfe_distribuicao.py" --config "$BASE_DIR/config/config.exemplo.yaml"
