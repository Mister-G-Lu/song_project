#!/usr/bin/env bash
# One-time setup: install git hooks from .githooks/
# Run: bash scripts/setup-hooks.sh

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

git config core.hooksPath "$REPO_ROOT/.githooks"

echo "✅ Git hooks installed from .githooks/"
echo "   pre-commit: JS unit tests (~2s)"
echo "   pre-push:   JS + Python critical tests (~2min)"
