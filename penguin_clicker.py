#!/usr/bin/env python3
"""Penguin Clicker - a simple auto clicker / key repeater for Linux.

Works on X11 and Wayland: clicks and key presses go through a virtual
uinput device, and global shortcuts are read straight from /dev/input,
so it doesn't depend on any particular desktop. Needs only Python 3 and
GTK 4 (PyGObject); no pip packages.
"""

import errno
import fcntl
import glob
import json
import os
import select
import shutil
import struct
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

APP_ID = "me.apenguin.PenguinClicker"
VERSION = "1.0.0"
HERE = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(HERE, "penguin-clicker.svg")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "penguin-clicker")
CONFIG_PATH = os.path.join(CONFIG_DIR, "settings.json")
VKBD_NAME = "Penguin Clicker Keyboard"
VMOUSE_NAME = "Penguin Clicker Mouse"

# ---------------------------------------------------------------- strings

T = {
    "app": ("Penguin Clicker", "النقّار التلقائي"),
    "subtitle": ("Auto click & key repeater", "تكرار النقر والأزرار تلقائيًا"),
    "lang_btn": ("عربي", "English"),
    "stopped": ("Stopped", "متوقف"),
    "running": ("Running", "يعمل"),
    "starting": ("Starting in {n}…", "يبدأ بعد {n}…"),
    "move_mouse": ("Move the mouse to where you want to click", "حرّك الفأرة إلى المكان الذي تريد النقر عليه"),
    "focus_target": ("Switch to the window that should get the key", "انتقل إلى النافذة التي تريد الضغط فيها"),
    "done_n": ("Done: {n}", "تم: {n}"),
    "next_in": ("next in {t}", "التالي بعد {t}"),
    "finished": ("Finished ✓  ·  done: {n}", "اكتمل ✓  ·  العدد: {n}"),
    "what": ("What to repeat", "ماذا تكرّر؟"),
    "mouse": ("Mouse click", "نقرة الفأرة"),
    "key": ("Keyboard key", "زر الكيبورد"),
    "button": ("Button", "الزر"),
    "left": ("Left", "يسار"),
    "right": ("Right", "يمين"),
    "middle": ("Middle", "الأوسط"),
    "click_type": ("Click", "النقرة"),
    "single": ("Single", "مفردة"),
    "double": ("Double", "مزدوجة"),
    "key_to_press": ("Key to press", "الزر المطلوب"),
    "press_a_key": ("Press a key…", "اضغط أي زر…"),
    "press_a_key_or_btn": ("Press a key or mouse side button…", "اضغط زرًا أو زر الفأرة الجانبي…"),
    "not_set": ("Click to choose", "اضغط للاختيار"),
    "every": ("How often", "كل كم؟"),
    "custom": ("Custom", "مخصص"),
    "times": ("How many times", "كم مرة؟"),
    "forever": ("Until I stop it", "إلى أن أوقفه"),
    "limited": ("Set number", "عدد محدد"),
    "times_unit": ("times", "مرة"),
    "shortcuts": ("Shortcuts", "الاختصارات"),
    "start_key": ("Start", "زر التشغيل"),
    "stop_key": ("Stop", "زر الإيقاف"),
    "same_key_note": ("Same key for both = on/off toggle.", "نفس الزر للاثنين = تشغيل وإيقاف."),
    "start": ("Start", "تشغيل"),
    "stop": ("Stop", "إيقاف"),
    "cancel": ("Cancel", "إلغاء"),
    "perm_title": ("One-time setup needed", "يلزم إعداد لمرة واحدة"),
    "perm_body": ("Lets it click, type and hear your shortcuts in other apps.",
                  "ليتمكن من النقر والضغط وسماع الاختصارات في البرامج الأخرى."),
    "perm_btn": ("Allow access", "السماح"),
    "perm_wait": ("Waiting for password…", "بانتظار كلمة المرور…"),
    "perm_fail": ("Setup didn't finish. In a terminal run:  bash install.sh --setup",
                  "لم يكتمل الإعداد. شغّل في الطرفية:  bash install.sh --setup"),
    "need_inject": ("Can't click yet: finish the setup above first.", "لا يمكن النقر بعد: أكمل الإعداد بالأعلى أولًا."),
    "key_missing": ("Choose the key to press first.", "اختر الزر المطلوب أولًا."),
    "u_ms": ("milliseconds", "مللي ثانية"),
    "u_s": ("seconds", "ثوانٍ"),
    "u_min": ("minutes", "دقائق"),
    "u_h": ("hours", "ساعات"),
}

UNITS = [("u_ms", 0.001), ("u_s", 1.0), ("u_min", 60.0), ("u_h", 3600.0)]
PRESETS = [
    (0.1, ("0.1 sec", "عُشر ثانية")),
    (0.5, ("½ sec", "نصف ثانية")),
    (1, ("1 sec", "ثانية")),
    (5, ("5 sec", "خمس ثوانٍ")),
    (30, ("30 sec", "نصف دقيقة")),
    (60, ("1 min", "دقيقة")),
    (300, ("5 min", "خمس دقائق")),
]

# ---------------------------------------------------------------- linux input

EV_SYN, EV_KEY, EV_REL = 0x00, 0x01, 0x02
SYN_REPORT = 0
REL_X, REL_Y, REL_WHEEL = 0x00, 0x01, 0x08
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_SIDE, BTN_EXTRA = 0x110, 0x111, 0x112, 0x113, 0x114
BUS_USB = 0x03
EVENT_FMT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FMT)


def _ioc(direction, typ, nr, size):
    return (direction << 30) | (size << 16) | (ord(typ) << 8) | nr


UI_DEV_CREATE = _ioc(0, "U", 1, 0)
UI_DEV_DESTROY = _ioc(0, "U", 2, 0)
UI_DEV_SETUP = _ioc(1, "U", 3, 92)
UI_SET_EVBIT = _ioc(1, "U", 100, 4)
UI_SET_KEYBIT = _ioc(1, "U", 101, 4)
UI_SET_RELBIT = _ioc(1, "U", 102, 4)


def EVIOCGNAME(length):
    return _ioc(2, "E", 0x06, length)


def EVIOCGBIT(ev, length):
    return _ioc(2, "E", 0x20 + ev, length)


KEY_NAMES = {
    1: "Esc", 14: "Backspace", 15: "Tab", 28: "Enter", 57: "Space", 58: "CapsLock",
    12: "-", 13: "=", 26: "[", 27: "]", 39: ";", 40: "'", 41: "`", 43: "\\", 51: ",", 52: ".", 53: "/",
    29: "Ctrl", 97: "Right Ctrl", 42: "Shift", 54: "Right Shift", 56: "Alt", 100: "AltGr",
    125: "Super", 126: "Right Super", 127: "Menu",
    69: "NumLock", 70: "ScrollLock", 99: "PrintScreen", 119: "Pause",
    102: "Home", 103: "↑", 104: "PageUp", 105: "←", 106: "→", 107: "End", 108: "↓",
    109: "PageDown", 110: "Insert", 111: "Delete",
    55: "Num *", 74: "Num -", 78: "Num +", 83: "Num .", 96: "Num Enter", 98: "Num /",
    71: "Num 7", 72: "Num 8", 73: "Num 9", 75: "Num 4", 76: "Num 5", 77: "Num 6",
    79: "Num 1", 80: "Num 2", 81: "Num 3", 82: "Num 0",
    113: "Mute", 114: "Vol-", 115: "Vol+", 163: "Next", 164: "Play/Pause", 165: "Prev",
    BTN_MIDDLE: "Mouse Middle", BTN_SIDE: "Mouse Back", BTN_EXTRA: "Mouse Forward",
    0x115: "Mouse Btn 6", 0x116: "Mouse Btn 7", 0x117: "Mouse Btn 8",
}
for _i, _c in enumerate("1234567890"):
    KEY_NAMES[2 + _i] = _c
for _row, _start in (("QWERTYUIOP", 16), ("ASDFGHJKL", 30), ("ZXCVBNM", 44)):
    for _i, _c in enumerate(_row):
        KEY_NAMES[_start + _i] = _c
for _i in range(10):
    KEY_NAMES[59 + _i] = f"F{_i + 1}"
KEY_NAMES[87], KEY_NAMES[88] = "F11", "F12"
for _i in range(12):
    KEY_NAMES[183 + _i] = f"F{_i + 13}"

MOD_OF_CODE = {29: "ctrl", 97: "ctrl", 42: "shift", 54: "shift", 56: "alt", 100: "alt", 125: "super", 126: "super"}
MOD_CODE = {"ctrl": 29, "shift": 42, "alt": 56, "super": 125}
MOD_LABEL = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "super": "Super"}
MOD_ORDER = ["ctrl", "alt", "shift", "super"]
# Mouse buttons allowed as shortcuts; left/right would fight with normal use.
HOTKEY_MOUSE_BTNS = {BTN_MIDDLE, BTN_SIDE, BTN_EXTRA, 0x115, 0x116, 0x117}


def combo_label(combo):
    if not combo:
        return None
    mods = [MOD_LABEL[m] for m in MOD_ORDER if m in combo.get("mods", [])]
    return " + ".join(mods + [KEY_NAMES.get(combo["code"], f"Key {combo['code']}")])


class Injector:
    """Two virtual uinput devices (keyboard + mouse) used to send events."""

    def __init__(self):
        self.kbd = self.mouse = None
        self.lock = threading.Lock()

    @staticmethod
    def available():
        return os.access("/dev/uinput", os.W_OK)

    def ready(self):
        return self.kbd is not None and self.mouse is not None

    def _make(self, name, product, keys, rels):
        fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_SYN)
            for k in keys:
                fcntl.ioctl(fd, UI_SET_KEYBIT, k)
            if rels:
                fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)
                for r in rels:
                    fcntl.ioctl(fd, UI_SET_RELBIT, r)
            setup = struct.pack("HHHH80sI", BUS_USB, 0x1d6b, product, 1, name.encode(), 0)
            fcntl.ioctl(fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(fd, UI_DEV_CREATE)
        except OSError:
            os.close(fd)
            raise
        return fd

    def open(self):
        if self.ready():
            return True
        try:
            self.kbd = self._make(VKBD_NAME, 0x7101, range(1, 249), None)
            self.mouse = self._make(VMOUSE_NAME, 0x7102, range(BTN_LEFT, BTN_LEFT + 8), (REL_X, REL_Y, REL_WHEEL))
        except OSError:
            self.close()
            return False
        time.sleep(0.3)  # give the compositor a moment to pick up the new devices
        return True

    def close(self):
        for fd in (self.kbd, self.mouse):
            if fd is not None:
                try:
                    fcntl.ioctl(fd, UI_DEV_DESTROY)
                except OSError:
                    pass
                os.close(fd)
        self.kbd = self.mouse = None

    def _emit(self, fd, etype, code, value):
        os.write(fd, struct.pack(EVENT_FMT, 0, 0, etype, code, value))

    def _key(self, fd, code, down):
        self._emit(fd, EV_KEY, code, 1 if down else 0)
        self._emit(fd, EV_SYN, SYN_REPORT, 0)

    def click(self, button, double=False):
        with self.lock:
            for i in range(2 if double else 1):
                if i:
                    time.sleep(0.06)
                self._key(self.mouse, button, True)
                time.sleep(0.02)
                self._key(self.mouse, button, False)

    def press(self, combo):
        mods = [MOD_CODE[m] for m in MOD_ORDER if m in combo.get("mods", [])]
        with self.lock:
            for m in mods:
                self._key(self.kbd, m, True)
            self._key(self.kbd, combo["code"], True)
            time.sleep(0.02)
            self._key(self.kbd, combo["code"], False)
            for m in reversed(mods):
                self._key(self.kbd, m, False)


class Listener(threading.Thread):
    """Reads key/button events from every input device for global shortcuts."""

    def __init__(self, on_event):
        super().__init__(daemon=True)
        self.on_event = on_event  # called from this thread: (code, value, mods)
        self.devices = {}  # fd -> path
        self.held_mods = {}
        self.running = True
        self.lock = threading.Lock()
        self.scan()

    def scan(self):
        with self.lock:
            self._scan()

    def _scan(self):
        known = set(self.devices.values())
        for path in sorted(glob.glob("/dev/input/event*")):
            if path in known:
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            try:
                name = fcntl.ioctl(fd, EVIOCGNAME(256), bytes(256)).split(b"\0", 1)[0].decode(errors="replace")
                evbits = fcntl.ioctl(fd, EVIOCGBIT(0, 4), bytes(4))
                has_keys = evbits[0] & (1 << EV_KEY)
            except OSError:
                name, has_keys = "", 0
            if not has_keys or name in (VKBD_NAME, VMOUSE_NAME):
                os.close(fd)
                continue
            self.devices[fd] = path

    def count(self):
        return len(self.devices)

    def _drop(self, fd):
        with self.lock:
            self.devices.pop(fd, None)
        try:
            os.close(fd)
        except OSError:
            pass

    def run(self):
        last_scan = time.monotonic()
        while self.running:
            if time.monotonic() - last_scan > 2:
                self.scan()
                last_scan = time.monotonic()
            with self.lock:
                fds = list(self.devices)
            if not fds:
                time.sleep(0.5)
                continue
            try:
                ready, _, _ = select.select(fds, [], [], 0.5)
            except (OSError, ValueError):
                for fd in fds:
                    try:
                        os.fstat(fd)
                    except OSError:
                        self._drop(fd)
                continue
            for fd in ready:
                try:
                    data = os.read(fd, EVENT_SIZE * 64)
                except BlockingIOError:
                    continue
                except OSError as e:
                    if e.errno in (errno.ENODEV, errno.EBADF, errno.EIO):
                        self._drop(fd)
                    continue
                for off in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
                    _, _, etype, code, value = struct.unpack_from(EVENT_FMT, data, off)
                    if etype != EV_KEY:
                        continue
                    if code in MOD_OF_CODE:
                        key = (fd, code)
                        if value:
                            self.held_mods[key] = MOD_OF_CODE[code]
                        else:
                            self.held_mods.pop(key, None)
                        continue
                    self.on_event(code, value, set(self.held_mods.values()))


# ---------------------------------------------------------------- setup helper

SETUP_SCRIPT = r"""
set -e
cat > /etc/udev/rules.d/70-penguin-clicker.rules <<'EOF'
# Penguin Clicker: let the logged-in user send clicks/keys and read shortcuts.
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_KEY}=="1", TAG+="uaccess"
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_MOUSE}=="1", TAG+="uaccess"
EOF
echo uinput > /etc/modules-load.d/penguin-clicker.conf
modprobe uinput || true
udevadm control --reload-rules
udevadm trigger --subsystem-match=misc --subsystem-match=input
udevadm settle || true
"""

# ---------------------------------------------------------------- settings

DEFAULTS = {
    "lang": "ar",
    "mode": "mouse",
    "button": "left",
    "double": False,
    "key": {"code": 57, "mods": []},
    "interval": 1.0,
    "custom": False,
    "custom_value": 2.0,
    "custom_unit": 1,
    "limit_on": False,
    "limit": 100,
    "start_hotkey": {"code": 64, "mods": []},  # F6
    "stop_hotkey": {"code": 65, "mods": []},   # F7
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CONFIG_PATH) as f:
            saved = json.load(f)
        cfg.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------- UI

CSS = """
window.pc { background: #f6f1e6; color: #1a1614; }
window.pc label, window.pc button, window.pc text, window.pc entry {
  font-family: "JetBrains Mono", "Noto Naskh Arabic", monospace;
}
window.pc label.pc-title, window.pc label.pc-section, window.pc label.pc-state, window.pc label.pc-banner-title,
window.pc button.pc-pill, window.pc button.pc-seg, window.pc button.pc-go, window.pc button.pc-allow,
window.pc button.pc-pill label, window.pc button.pc-seg label, window.pc button.pc-go label, window.pc button.pc-allow label {
  font-family: "Kalam", "Noto Naskh Arabic", cursive;
}
.pc-title { font-size: 30px; font-weight: 700; }
.pc-sub { font-size: 11.5px; color: #8a807a; }
.pc-card { background: #fbf7ec; border: 1.5px solid #d9d0c0; border-radius: 16px; padding: 8px 14px 12px 14px; }
.pc-section { font-size: 20px; font-weight: 700; }
.pc-field { font-size: 12.5px; color: #4a423d; }
.pc-muted { font-size: 11px; color: #8a807a; }
.pc-error { font-size: 11.5px; color: #c2401f; }

.pc-status { background: #fbf7ec; border: 1.5px solid #d9d0c0; border-radius: 16px; padding: 10px 16px; }
.pc-status.on { background: #fbe3da; border-color: #d94d2a; }
.pc-status.wait { background: #fcf0c8; border-color: #f0c12b; }
.pc-dot { font-size: 16px; color: #c8c1b3; }
.pc-status.on .pc-dot { color: #d94d2a; }
.pc-status.wait .pc-dot { color: #e0a800; }
.pc-state { font-size: 24px; font-weight: 700; }
.pc-count { font-size: 12.5px; color: #4a423d; }

button.pc-pill, button.pc-seg, button.pc-keycap {
  background: transparent; background-image: none; color: #1a1614; border: 1.5px solid #1a1614;
  box-shadow: none; text-shadow: none; min-height: 0; outline-color: #d94d2a;
}
button.pc-pill { border-radius: 999px; padding: 1px 12px; font-size: 16px; }
button.pc-seg { border-radius: 12px; padding: 4px 10px; font-size: 18px; font-weight: 700; }
button.pc-pill:hover, button.pc-seg:hover, button.pc-keycap:hover { background: rgba(26, 22, 20, 0.06); }
button.pc-pill:checked, button.pc-seg:checked { background: #f5cfc0; }
button.pc-keycap {
  background: #fffdf7; border-radius: 9px; border-bottom-width: 3.5px; padding: 3px 14px;
  font-size: 13px; font-weight: 700; min-width: 96px;
}
button.pc-keycap.capturing { background: #fcf0c8; border-color: #e0a800; }

button.pc-go {
  border-radius: 18px; padding: 8px 18px; font-size: 26px; font-weight: 700; border: 1.5px solid #1a1614;
  border-bottom-width: 4px; background: #d94d2a; background-image: none; color: #fffdf7; box-shadow: none; text-shadow: none;
}
button.pc-go:hover { background: #e25a37; }
button.pc-go.stop { background: #1a1614; color: #f6f1e6; }
button.pc-go.wait { background: #f0c12b; color: #1a1614; }

.pc-banner { background: #fcf0c8; border: 1.5px solid #e0a800; border-radius: 14px; padding: 10px 14px; }
.pc-banner-title { font-size: 18px; font-weight: 700; }
.pc-banner label.pc-field { color: #4a423d; }
button.pc-allow {
  background: #f0c12b; background-image: none; color: #1a1614; border: 1.5px solid #1a1614; border-radius: 999px;
  padding: 2px 16px; font-size: 17px; font-weight: 700; box-shadow: none;
}

spinbutton {
  background: #fffdf7; color: #1a1614; border: 1.5px solid #d9d0c0; border-radius: 10px; box-shadow: none;
}
spinbutton > text { color: #1a1614; font-size: 13px; }
spinbutton > button {
  background: transparent; background-image: none; color: #1a1614; border: none; box-shadow: none;
}
spinbutton > button:hover { background: rgba(26, 22, 20, 0.06); }
dropdown > button {
  background: #fffdf7; background-image: none; color: #1a1614; border: 1.5px solid #d9d0c0; border-radius: 10px;
  box-shadow: none;
}
popover > contents { background: #fbf7ec; color: #1a1614; border: 1.5px solid #1a1614; border-radius: 12px; }
popover listview > row:selected, popover listview > row:hover { background: #f5cfc0; color: #1a1614; }
flowboxchild { padding: 0; }
"""


class ClickerWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.add_css_class("pc")
        self.set_default_size(440, -1)
        self.set_resizable(False)

        self.cfg = load_config()
        self.injector = Injector()
        self.listener = None
        self.phase = "stopped"  # stopped | countdown | running
        self.stop_event = threading.Event()
        self.worker = None
        self.done = 0
        self.next_at = 0.0
        self.countdown_end = 0.0
        self.last_finished = None
        self.capturing = None  # None | "key" | "start_hotkey" | "stop_hotkey"
        self.ignore_hotkeys_until = 0.0
        self.setup_state = "idle"  # idle | busy | failed

        self._open_input()

        keyctl = Gtk.EventControllerKey()
        keyctl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keyctl.connect("key-pressed", self._on_gtk_key)
        self.add_controller(keyctl)

        self.connect("close-request", self._on_close)
        GLib.timeout_add(100, self._tick)
        self.build()

    # ------------------------------------------------------------ helpers

    def t(self, key, **kw):
        s = T[key][1 if self.cfg["lang"] == "ar" else 0]
        return s.format(**kw) if kw else s

    def fmt_dur(self, sec):
        ar = self.cfg["lang"] == "ar"
        if sec < 1:
            return f"{sec * 1000:.0f} {'م.ث' if ar else 'ms'}"
        if sec < 60:
            txt = f"{sec:.1f}".rstrip("0").rstrip(".")
            return f"{txt} {'ث' if ar else 's'}"
        m, s = divmod(int(round(sec)), 60)
        if m < 60:
            return f"{m}:{s:02d} {'د' if ar else 'min'}"
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"

    def interval(self):
        if self.cfg["custom"]:
            return max(0.01, float(self.cfg["custom_value"]) * UNITS[self.cfg["custom_unit"]][1])
        return float(self.cfg["interval"])

    def hotkeys_global(self):
        return self.listener is not None and self.listener.count() > 0

    def _open_input(self):
        if Injector.available():
            self.injector.open()
        if self.listener is None:
            self.listener = Listener(self._on_input_thread)
            self.listener.start()
        else:
            self.listener.scan()

    def save(self):
        save_config(self.cfg)

    # ------------------------------------------------------------ building

    def build(self):
        ar = self.cfg["lang"] == "ar"
        Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL if ar else Gtk.TextDirection.LTR)
        self.set_title(self.t("app"))
        self.cards = []

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(14)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        # header
        head = Gtk.Box(spacing=12)
        if os.path.exists(ICON_PATH):
            logo = Gtk.Image.new_from_file(ICON_PATH)
            logo.set_pixel_size(52)
            head.append(logo)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        title = Gtk.Label(label=self.t("app"), xalign=0)
        title.add_css_class("pc-title")
        sub = Gtk.Label(label=self.t("subtitle"), xalign=0)
        sub.add_css_class("pc-sub")
        titles.append(title)
        titles.append(sub)
        lang = Gtk.Button(label=self.t("lang_btn"), valign=Gtk.Align.CENTER)
        lang.add_css_class("pc-pill")
        lang.connect("clicked", self._toggle_lang)
        head.append(titles)
        head.append(lang)
        root.append(head)

        # permission banner
        self.banner = Gtk.Box(spacing=12)
        self.banner.add_css_class("pc-banner")
        btexts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        bt = Gtk.Label(label=self.t("perm_title"), xalign=0)
        bt.add_css_class("pc-banner-title")
        self.banner_body = Gtk.Label(xalign=0, wrap=True, max_width_chars=40)
        self.banner_body.add_css_class("pc-field")
        btexts.append(bt)
        btexts.append(self.banner_body)
        self.allow_btn = Gtk.Button(label=self.t("perm_btn"), valign=Gtk.Align.CENTER)
        self.allow_btn.add_css_class("pc-allow")
        self.allow_btn.connect("clicked", self._run_setup)
        self.banner.append(btexts)
        self.banner.append(self.allow_btn)
        root.append(self.banner)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)

        # what to repeat
        card, body = self._card(self.t("what"))
        body.append(self._segmented([("mouse", self.t("mouse")), ("key", self.t("key"))],
                                    self.cfg["mode"], self._set_mode, "pc-seg"))
        self.mouse_opts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.mouse_opts.append(self._row(self.t("button"), self._segmented(
            [("left", self.t("left")), ("middle", self.t("middle")), ("right", self.t("right"))],
            self.cfg["button"], lambda v: self._set("button", v), "pc-pill")))
        self.mouse_opts.append(self._row(self.t("click_type"), self._segmented(
            [(False, self.t("single")), (True, self.t("double"))],
            self.cfg["double"], lambda v: self._set("double", v), "pc-pill")))
        self.key_opts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.key_btn = self._keycap("key")
        self.key_opts.append(self._row(self.t("key_to_press"), self.key_btn))
        body.append(self.mouse_opts)
        body.append(self.key_opts)
        grid.attach(card, 0, 0, 1, 1)

        # how often
        card, body = self._card(self.t("every"))
        per_line = 3 if ar else 4
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=per_line,
                           min_children_per_line=per_line, column_spacing=6, row_spacing=6, homogeneous=True)
        lang_i = 1 if ar else 0
        group = None
        current = "custom" if self.cfg["custom"] else self.cfg["interval"]
        for value, names in PRESETS + [("custom", T["custom"])]:
            b = Gtk.ToggleButton(label=names[lang_i])
            b.add_css_class("pc-pill")
            if group:
                b.set_group(group)
            else:
                group = b
            b.set_active(value == current)
            b.connect("toggled", self._on_interval_chip, value)
            flow.append(b)
        for child in list(iter_children(flow)):
            child.set_focusable(False)
        body.append(flow)
        self.custom_row = Gtk.Box(spacing=8)
        adj = Gtk.Adjustment(value=self.cfg["custom_value"], lower=0, upper=100000, step_increment=1, page_increment=10)
        self.custom_spin = Gtk.SpinButton(adjustment=adj, digits=2, numeric=True, hexpand=True)
        self.custom_spin.connect("value-changed", self._on_custom_value)
        self.unit_dd = Gtk.DropDown.new_from_strings([self.t(u) for u, _ in UNITS])
        self.unit_dd.set_selected(self.cfg["custom_unit"])
        self.unit_dd.connect("notify::selected", self._on_unit)
        self.custom_row.append(self.custom_spin)
        self.custom_row.append(self.unit_dd)
        body.append(self.custom_row)
        grid.attach(card, 1, 0, 1, 1)

        # how many times
        card, body = self._card(self.t("times"))
        body.append(self._segmented([(False, self.t("forever")), (True, self.t("limited"))],
                                    self.cfg["limit_on"], self._set_limit_on, "pc-pill", fill=True))
        self.limit_box = Gtk.Box(spacing=8)
        ladj = Gtk.Adjustment(value=self.cfg["limit"], lower=1, upper=10_000_000, step_increment=1, page_increment=10)
        self.limit_spin = Gtk.SpinButton(adjustment=ladj, numeric=True, hexpand=True)
        self.limit_spin.connect("value-changed", lambda s: self._set("limit", int(s.get_value())))
        lu = Gtk.Label(label=self.t("times_unit"))
        lu.add_css_class("pc-field")
        self.limit_box.append(self.limit_spin)
        self.limit_box.append(lu)
        body.append(self.limit_box)
        grid.attach(card, 0, 1, 1, 1)

        # shortcuts
        card, body = self._card(self.t("shortcuts"))
        self.start_key_btn = self._keycap("start_hotkey")
        self.stop_key_btn = self._keycap("stop_hotkey")
        body.append(self._row(self.t("start_key"), self.start_key_btn))
        body.append(self._row(self.t("stop_key"), self.stop_key_btn))
        note = Gtk.Label(label=self.t("same_key_note"), xalign=0, wrap=True, max_width_chars=24)
        note.add_css_class("pc-muted")
        body.append(note)
        grid.attach(card, 1, 1, 1, 1)
        root.append(grid)

        # status + go
        bottom = Gtk.Box(spacing=12)
        self.status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self.status.add_css_class("pc-status")
        srow = Gtk.Box(spacing=8)
        dot = Gtk.Label(label="●")
        dot.add_css_class("pc-dot")
        self.state_lbl = Gtk.Label(xalign=0)
        self.state_lbl.add_css_class("pc-state")
        self.count_lbl = Gtk.Label(xalign=1, hexpand=True)
        self.count_lbl.add_css_class("pc-count")
        srow.append(dot)
        srow.append(self.state_lbl)
        srow.append(self.count_lbl)
        self.detail_lbl = Gtk.Label(xalign=0, wrap=True)
        self.detail_lbl.add_css_class("pc-count")
        self.status.append(srow)
        self.status.append(self.detail_lbl)
        self.go_btn = Gtk.Button(width_request=190)
        self.go_btn.add_css_class("pc-go")
        self.go_btn.connect("clicked", self._on_go)
        bottom.append(self.status)
        bottom.append(self.go_btn)
        root.append(bottom)
        self.msg_lbl = Gtk.Label(xalign=0.5, wrap=True)
        self.msg_lbl.add_css_class("pc-error")
        root.append(self.msg_lbl)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      propagate_natural_height=True, propagate_natural_width=True)
        scroller.set_max_content_height(screen_height() - 110)
        scroller.set_child(root)
        self.set_child(scroller)
        self.refresh()

    def _card(self, title):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("pc-card")
        self.cards.append(card)
        lbl = Gtk.Label(label=title, xalign=0)
        lbl.add_css_class("pc-section")
        card.append(lbl)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.append(body)
        return card, body

    def _row(self, label, widget):
        row = Gtk.Box(spacing=10)
        lbl = Gtk.Label(label=label, xalign=0, hexpand=True)
        lbl.add_css_class("pc-field")
        row.append(lbl)
        row.append(widget)
        return row

    def _segmented(self, options, current, on_change, css, fill=None):
        fill = css == "pc-seg" if fill is None else fill
        box = Gtk.Box(spacing=6, homogeneous=fill)
        group = None
        for value, label in options:
            b = Gtk.ToggleButton(label=label, hexpand=fill)
            b.add_css_class(css)
            if group:
                b.set_group(group)
            else:
                group = b
            b.set_active(value == current)
            b.connect("toggled", lambda btn, v=value: btn.get_active() and on_change(v))
            box.append(b)
        return box

    def _keycap(self, which):
        b = Gtk.Button()
        b.add_css_class("pc-keycap")
        b.connect("clicked", lambda _b: self._begin_capture(which))
        return b

    # ------------------------------------------------------------ state -> UI

    def refresh(self):
        cfg = self.cfg
        self.mouse_opts.set_visible(cfg["mode"] == "mouse")
        self.key_opts.set_visible(cfg["mode"] == "key")
        self.custom_row.set_visible(cfg["custom"])
        self.limit_box.set_visible(cfg["limit_on"])

        for which, btn in (("key", self.key_btn), ("start_hotkey", self.start_key_btn), ("stop_hotkey", self.stop_key_btn)):
            if self.capturing == which:
                btn.set_label(self.t("press_a_key") if which == "key" else self.t("press_a_key_or_btn"))
                btn.add_css_class("capturing")
            else:
                btn.set_label(combo_label(cfg[which]) or self.t("not_set"))
                btn.remove_css_class("capturing")

        inject_ok = self.injector.ready()
        global_ok = self.hotkeys_global()
        self.banner.set_visible(not (inject_ok and global_ok))
        self.banner_body.set_label(self.t("perm_fail") if self.setup_state == "failed" else self.t("perm_body"))
        self.allow_btn.set_label(self.t("perm_wait") if self.setup_state == "busy" else self.t("perm_btn"))
        self.allow_btn.set_sensitive(self.setup_state != "busy")

        self._update_status()

    def _update_status(self):
        for card in self.cards:
            card.set_sensitive(self.phase == "stopped")
        for c in ("on", "wait"):
            self.status.remove_css_class(c)
            self.go_btn.remove_css_class(c)
        self.go_btn.remove_css_class("stop")
        self.go_btn.remove_css_class("wait")
        now = time.monotonic()
        limit = f" / {self.cfg['limit']}" if self.cfg["limit_on"] else ""

        if self.phase == "countdown":
            n = max(1, int(self.countdown_end - now + 0.999))
            self.status.add_css_class("wait")
            self.state_lbl.set_label(self.t("starting", n=n))
            self.detail_lbl.set_label(self.t("move_mouse") if self.cfg["mode"] == "mouse" else self.t("focus_target"))
            self.count_lbl.set_label("")
            self.go_btn.set_label(self.t("cancel"))
            self.go_btn.add_css_class("wait")
        elif self.phase == "running":
            self.status.add_css_class("on")
            self.state_lbl.set_label(self.t("running"))
            self.count_lbl.set_label(self.t("done_n", n=f"{self.done}{limit}"))
            left = max(0.0, self.next_at - now)
            what = self.t("mouse") if self.cfg["mode"] == "mouse" else combo_label(self.cfg["key"])
            self.detail_lbl.set_label(f"{what}  ·  {self.t('next_in', t=self.fmt_dur(left))}")
            self.go_btn.set_label(self.t("stop"))
            self.go_btn.add_css_class("stop")
        else:
            self.state_lbl.set_label(self.t("stopped"))
            if self.last_finished is not None:
                self.count_lbl.set_label("")
                self.detail_lbl.set_label(self.t("finished", n=self.last_finished))
            else:
                self.count_lbl.set_label(self.t("done_n", n=self.done) if self.done else "")
                what = self.t("mouse") if self.cfg["mode"] == "mouse" else (combo_label(self.cfg["key"]) or "—")
                every = "every" if self.cfg["lang"] == "en" else "كل"
                self.detail_lbl.set_label(f"{what}  ·  {every} {self.fmt_dur(self.interval())}")
            self.go_btn.set_label(self.t("start"))

    def _tick(self):
        if self.phase != "stopped":
            self._update_status()
        return True

    # ------------------------------------------------------------ handlers

    def _set(self, key, value):
        self.cfg[key] = value
        self.save()
        self.refresh()

    def _set_mode(self, mode):
        self._set("mode", mode)

    def _set_limit_on(self, on):
        self._set("limit_on", on)

    def _on_interval_chip(self, btn, value):
        if not btn.get_active():
            return
        if value == "custom":
            self.cfg["custom"] = True
        else:
            self.cfg["custom"] = False
            self.cfg["interval"] = value
        self.save()
        self.refresh()

    def _on_custom_value(self, spin):
        self.cfg["custom_value"] = spin.get_value()
        self.save()
        self._update_status()

    def _on_unit(self, dd, _pspec):
        self.cfg["custom_unit"] = dd.get_selected()
        self.save()
        self._update_status()

    def _toggle_lang(self, _btn):
        self.capturing = None
        self.cfg["lang"] = "en" if self.cfg["lang"] == "ar" else "ar"
        self.save()
        self.build()

    def _on_close(self, *_):
        self.stop()
        if self.listener:
            self.listener.running = False
        self.injector.close()
        self.save()
        return False

    # ------------------------------------------------------------ capture

    def _begin_capture(self, which):
        self.capturing = None if self.capturing == which else which
        self.msg_lbl.set_label("")
        self.refresh()

    def _finish_capture(self, code, mods):
        which = self.capturing
        self.capturing = None
        self.cfg[which] = {"code": code, "mods": [m for m in MOD_ORDER if m in mods]}
        self.ignore_hotkeys_until = time.monotonic() + 0.4
        self.save()
        self.refresh()

    def _on_gtk_key(self, _ctl, keyval, keycode, state):
        code = keycode - 8  # X/Wayland keycodes are evdev codes + 8
        if self.capturing:
            if keyval == Gdk.KEY_Escape:
                self.capturing = None
                self.refresh()
                return True
            if code in MOD_OF_CODE:
                return True
            mods = set()
            if state & Gdk.ModifierType.CONTROL_MASK:
                mods.add("ctrl")
            if state & Gdk.ModifierType.SHIFT_MASK:
                mods.add("shift")
            if state & Gdk.ModifierType.ALT_MASK:
                mods.add("alt")
            if state & Gdk.ModifierType.SUPER_MASK:
                mods.add("super")
            self._finish_capture(code, mods)
            return True
        if not self.hotkeys_global():
            # fallback: shortcuts only while focused
            self._hotkey(code, set())
        return False

    def _on_input_thread(self, code, value, mods):
        if value == 1:
            GLib.idle_add(self._on_input, code, mods)

    def _on_input(self, code, mods):
        if self.capturing:
            # keyboard keys come through GTK; here we only pick up mouse buttons
            if self.capturing != "key" and code in HOTKEY_MOUSE_BTNS:
                self._finish_capture(code, mods)
            return False
        self._hotkey(code, mods)
        return False

    def _hotkey(self, code, mods):
        if time.monotonic() < self.ignore_hotkeys_until:
            return

        def match(combo):
            return combo and combo["code"] == code and set(combo.get("mods", [])) == set(mods)

        start, stop = match(self.cfg["start_hotkey"]), match(self.cfg["stop_hotkey"])
        if start and stop:
            if self.phase == "stopped":
                self.start(delay=0)
            else:
                self.stop()
        elif stop:
            self.stop()
        elif start and self.phase == "stopped":
            self.start(delay=0)

    # ------------------------------------------------------------ engine

    def _on_go(self, _btn):
        if self.phase == "stopped":
            self.start(delay=3)
        else:
            self.stop()

    def start(self, delay):
        if self.phase != "stopped":
            return
        if not self.injector.ready() and not self.injector.open():
            self.msg_lbl.set_label(self.t("need_inject"))
            return
        if self.cfg["mode"] == "key" and not self.cfg.get("key"):
            self.msg_lbl.set_label(self.t("key_missing"))
            return
        self.msg_lbl.set_label("")
        self.capturing = None
        self.done = 0
        self.last_finished = None
        self.stop_event = threading.Event()
        self.phase = "countdown" if delay else "running"
        self.countdown_end = time.monotonic() + delay
        self.next_at = self.countdown_end
        cfg = dict(self.cfg)
        self.worker = threading.Thread(target=self._run, args=(cfg, delay, self.interval(), self.stop_event), daemon=True)
        self.worker.start()
        self.refresh()

    def stop(self):
        if self.phase == "stopped":
            return
        self.stop_event.set()
        self.phase = "stopped"
        self.refresh()

    def _run(self, cfg, delay, interval, stop_event):
        if delay and stop_event.wait(delay):
            return
        GLib.idle_add(self._set_phase_running, stop_event)
        button = {"left": BTN_LEFT, "right": BTN_RIGHT, "middle": BTN_MIDDLE}[cfg["button"]]
        limit = cfg["limit"] if cfg["limit_on"] else None
        done = 0
        next_at = time.monotonic()
        while not stop_event.is_set():
            try:
                if cfg["mode"] == "mouse":
                    self.injector.click(button, cfg["double"])
                else:
                    self.injector.press(cfg["key"])
            except OSError:
                GLib.idle_add(self._worker_error, stop_event)
                return
            done += 1
            next_at += interval
            if next_at < time.monotonic():  # fell behind (very short interval) - don't burst
                next_at = time.monotonic() + interval
            self.done, self.next_at = done, next_at
            if limit and done >= limit:
                GLib.idle_add(self._worker_finished, stop_event, done)
                return
            if stop_event.wait(max(0.0, next_at - time.monotonic())):
                return

    def _set_phase_running(self, stop_event):
        if stop_event is self.stop_event and not stop_event.is_set():
            self.phase = "running"
            self.refresh()
        return False

    def _worker_finished(self, stop_event, done):
        if stop_event is self.stop_event:
            self.phase = "stopped"
            self.last_finished = done
            self.refresh()
        return False

    def _worker_error(self, stop_event):
        if stop_event is self.stop_event:
            self.phase = "stopped"
            self.injector.close()
            self.msg_lbl.set_label(self.t("need_inject"))
            self.refresh()
        return False

    # ------------------------------------------------------------ permission setup

    def _run_setup(self, _btn):
        if not shutil.which("pkexec"):
            self.setup_state = "failed"
            self.refresh()
            return
        self.setup_state = "busy"
        self.refresh()

        def work():
            try:
                ok = subprocess.run(["pkexec", "sh", "-c", SETUP_SCRIPT]).returncode == 0
            except OSError:
                ok = False
            time.sleep(1.0)
            GLib.idle_add(self._setup_done, ok)

        threading.Thread(target=work, daemon=True).start()

    def _setup_done(self, ok):
        self._open_input()
        works = self.injector.ready() and self.hotkeys_global()
        self.setup_state = "idle" if (ok and works) else "failed"
        self.refresh()
        return False


def screen_height():
    try:
        monitors = Gdk.Display.get_default().get_monitors()
        return min(monitors.get_item(i).get_geometry().height for i in range(monitors.get_n_items()))
    except (AttributeError, TypeError, ValueError):
        return 900


def iter_children(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        child = child.get_next_sibling()


class ClickerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.win = None

    def do_activate(self):
        if self.win is None:
            settings = Gtk.Settings.get_default()
            if settings:
                settings.set_property("gtk-application-prefer-dark-theme", False)
            provider = Gtk.CssProvider()
            provider.load_from_string(CSS) if hasattr(provider, "load_from_string") else provider.load_from_data(CSS.encode())
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            Gtk.Window.set_default_icon_name("penguin-clicker")
            self.win = ClickerWindow(self)
        self.win.present()


def register_fonts():
    """Make the bundled Penguin fonts (Kalam, JetBrains Mono, Noto Naskh Arabic) available to GTK."""
    fonts = os.path.join(HERE, "fonts")
    if not os.path.isdir(fonts):
        return
    try:
        import ctypes
        fc = ctypes.CDLL("libfontconfig.so.1")
        fc.FcConfigAppFontAddDir.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        fc.FcConfigAppFontAddDir(None, fonts.encode())
    except (OSError, AttributeError):
        pass


def main():
    if "--version" in sys.argv:
        print(f"Penguin Clicker {VERSION}")
        return 0
    register_fonts()
    return ClickerApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
