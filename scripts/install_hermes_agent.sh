#!/usr/bin/env bash
set -euo pipefail

if [[ "${OSTYPE:-}" == "msys" || "${OSTYPE:-}" == "win32" || "${OS:-}" == "Windows_NT" ]]; then
  echo "Hermes Agent is documented for Linux/macOS/WSL2. Run this inside WSL2, not native Windows." >&2
  exit 1
fi

if ! grep -qiE "linux|darwin" <<<"$(uname -s)"; then
  echo "Unsupported platform for this bootstrap helper: $(uname -s)" >&2
  exit 1
fi

if command -v hermes >/dev/null 2>&1; then
  echo "Hermes Agent already appears to be installed:"
  hermes --version || true
  echo ""
  echo "Next steps:"
  echo "  python scripts/bootstrap_hermes_profiles.py bootstrap"
  echo "  python scripts/bootstrap_hermes_profiles.py status"
  exit 0
fi

echo "Installing Hermes Agent with the official installer for Linux/macOS/WSL2..."
echo "Source: https://hermes-agent.nousresearch.com/docs/getting-started/installation/"
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

echo ""
echo "Reload your shell, then run:"
echo "  hermes doctor"
echo "  python scripts/bootstrap_hermes_profiles.py bootstrap"
