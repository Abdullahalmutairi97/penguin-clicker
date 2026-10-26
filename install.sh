#!/usr/bin/env bash
# Penguin Clicker installer.
#   ./install.sh            install for this user (+ one-time permission setup)
#   ./install.sh --setup    only the one-time permission setup (needs sudo)
#   ./install.sh --uninstall
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE="$HOME/.local/share/penguin-clicker"
BIN="$HOME/.local/bin/penguin-clicker"
DESKTOP="$HOME/.local/share/applications/penguin-clicker.desktop"
ICON="$HOME/.local/share/icons/hicolor/scalable/apps/penguin-clicker.svg"
RULES=/etc/udev/rules.d/70-penguin-clicker.rules
MODLOAD=/etc/modules-load.d/penguin-clicker.conf

setup_permissions() {
  echo "==> One-time setup: allow clicking/typing and global shortcuts (asks for your password)"
  sudo tee "$RULES" >/dev/null <<'EOF'
# Penguin Clicker: let the logged-in user send clicks/keys and read shortcuts.
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_KEY}=="1", TAG+="uaccess"
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_MOUSE}=="1", TAG+="uaccess"
EOF
  echo uinput | sudo tee "$MODLOAD" >/dev/null
  sudo modprobe uinput || true
  sudo udevadm control --reload-rules
  sudo udevadm trigger --subsystem-match=misc --subsystem-match=input
  sudo udevadm settle || true
  echo "    done. (If shortcuts still don't work, log out and back in once.)"
}

check_deps() {
  if python3 - <<'EOF' 2>/dev/null
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
EOF
  then return 0; fi
  if command -v apt-get >/dev/null; then
    echo "==> Installing GTK 4 for Python (asks for your password)"
    sudo apt-get update -qq && sudo apt-get install -y python3-gi gir1.2-gtk-4.0 && return 0
  elif command -v pacman >/dev/null; then
    sudo pacman -S --needed --noconfirm python-gobject gtk4 && return 0
  elif command -v dnf >/dev/null; then
    sudo dnf install -y python3-gobject gtk4 && return 0
  fi
  echo "!! Missing GTK 4 for Python. Install it, then run this again:"
  echo "   Arch / CachyOS / Manjaro : sudo pacman -S python-gobject gtk4"
  echo "   Ubuntu / Debian / Mint   : sudo apt install python3-gi gir1.2-gtk-4.0"
  echo "   Fedora                   : sudo dnf install python3-gobject gtk4"
  echo "   openSUSE                 : sudo zypper install python3-gobject typelib-1_0-Gtk-4_0"
  exit 1
}

case "${1:-}" in
  --setup)
    setup_permissions
    exit 0 ;;
  --uninstall)
    rm -rf "$SHARE" "$BIN" "$DESKTOP" "$ICON"
    if [[ -e $RULES || -e $MODLOAD ]]; then
      sudo rm -f "$RULES" "$MODLOAD"
      sudo udevadm control --reload-rules || true
    fi
    echo "Penguin Clicker removed. (Your settings are in ~/.config/penguin-clicker)"
    exit 0 ;;
esac

check_deps
echo "==> Installing Penguin Clicker"
install -Dm644 "$HERE/penguin_clicker.py" "$SHARE/penguin_clicker.py"
install -Dm644 "$HERE/penguin-clicker.svg" "$SHARE/penguin-clicker.svg"
install -Dm644 -t "$SHARE/fonts" "$HERE"/fonts/*.ttf
install -Dm644 "$HERE/penguin-clicker.svg" "$ICON"
mkdir -p "$(dirname "$BIN")"
cat > "$BIN" <<EOF
#!/bin/sh
exec python3 "$SHARE/penguin_clicker.py" "\$@"
EOF
chmod +x "$BIN"
mkdir -p "$(dirname "$DESKTOP")"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Penguin Clicker
Name[ar]=النقّار التلقائي
Comment=Auto click and key repeater
Comment[ar]=تكرار النقر والأزرار تلقائيًا
Exec=$BIN
Icon=penguin-clicker
Terminal=false
Categories=Utility;
Keywords=autoclicker;clicker;macro;repeat;
StartupWMClass=me.apenguin.PenguinClicker
EOF
update-desktop-database "$(dirname "$DESKTOP")" 2>/dev/null || true

if [[ -w /dev/uinput && -e $RULES ]]; then
  echo "==> Permissions already set up"
else
  setup_permissions
fi
echo
echo "Installed! Open \"Penguin Clicker\" from your app menu, or run: penguin-clicker"
