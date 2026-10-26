#!/usr/bin/env bash
# One-command install:  curl -fsSL https://raw.githubusercontent.com/Abdullahalmutairi97/penguin-clicker/main/get.sh | bash
set -euo pipefail
REPO="Abdullahalmutairi97/penguin-clicker"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "==> Downloading Penguin Clicker"
if command -v curl >/dev/null; then
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.tar.gz" -o "$TMP/src.tar.gz"
else
  wget -qO "$TMP/src.tar.gz" "https://github.com/$REPO/archive/refs/heads/main.tar.gz"
fi
tar -xzf "$TMP/src.tar.gz" -C "$TMP" --strip-components=1
bash "$TMP/install.sh" "$@" </dev/tty
