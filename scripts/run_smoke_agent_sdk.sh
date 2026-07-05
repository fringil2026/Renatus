#!/usr/bin/env bash
# Phase 2 probe — prove Claude can be driven headlessly via the Agent SDK.
#
# Prerequisite (operator, one-time): authenticate the Claude CLI first —
#     claude            # sign in interactively
#
# Then run this from the repo root:
#     ./scripts/run_smoke_agent_sdk.sh
#
# It installs the optional SDK extra and runs the live one-turn smoke test
# (expects "PONG"). Costs a few tokens. Exit 0 = the AgentSDKDriver path is real.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Installing the Agent SDK extra (.[agent])…"
pip install -e '.[agent]'

echo "==> Running the live Agent SDK smoke test…"
AGENT_SDK_SMOKE=1 python3 tests/smoke_agent_sdk.py
