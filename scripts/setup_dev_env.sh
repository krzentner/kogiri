#!/usr/bin/env bash
uv venv
uv pip install -e '.[recommended]'
uv pip install -r dev-requirements.txt
./scripts/install_torch_cpu.sh
