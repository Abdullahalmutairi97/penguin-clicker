# Penguin Clicker · النقّار التلقائي

برنامج بسيط لتكرار نقرة الفأرة أو الضغط على زر في الكيبورد تلقائيًا، على لينكس (X11 و Wayland).

## التثبيت (أمر واحد)

افتح الطرفية (Terminal) والصق:

```
curl -fsSL https://raw.githubusercontent.com/Abdullahalmutairi97/penguin-clicker/main/get.sh | bash
```

سيطلب كلمة المرور مرة واحدة، ثم افتح **النقّار التلقائي** من قائمة البرامج.
يعمل على أوبونتو وغيره (يثبّت ما يحتاجه تلقائيًا).

## الاستخدام

- **ماذا تكرّر؟** نقرة الفأرة (يسار / أوسط / يمين، مفردة أو مزدوجة) أو زر من الكيبورد (يقبل الاختصارات مثل Ctrl + C).
- **كل كم؟** عُشر ثانية، ثانية، 5 ثوانٍ، نصف دقيقة، دقيقة… أو **مخصص** بأي مدة تريدها.
- **كم مرة؟** إلى أن توقفه، أو عدد محدد ثم يتوقف وحده.
- **الاختصارات:** اضغط على زر التشغيل أو الإيقاف ثم اضغط الزر الذي تريده (أو زر الفأرة الجانبي). الافتراضي **F6** للتشغيل و**F7** للإيقاف. إذا اخترت نفس الزر للاثنين يصير زر تشغيل/إيقاف.
- النقر يكون في **مكان مؤشر الفأرة الحالي**.
- عند الضغط على زر «تشغيل» في البرنامج يعطيك 3 ثوانٍ لتحرك الفأرة للمكان المطلوب. أما الاختصار فيبدأ فورًا.
- الإعدادات تُحفظ تلقائيًا.

## الإزالة

```
curl -fsSL https://raw.githubusercontent.com/Abdullahalmutairi97/penguin-clicker/main/get.sh | bash -s -- --uninstall
```

---

## English

A simple auto clicker / key repeater for Linux (X11 and Wayland).

**Install (one command):**

```
curl -fsSL https://raw.githubusercontent.com/Abdullahalmutairi97/penguin-clicker/main/get.sh | bash
```

It installs what it needs (Ubuntu/Debian, Arch, Fedora), asks for your password once, then open **Penguin Clicker** from the app menu. From a clone you can also run `bash install.sh`.

**Features**
- Repeat a mouse click (left / middle / right, single or double) at the cursor position, or a keyboard key / combo (e.g. Ctrl + C).
- Interval presets (0.1 s → 5 min) or any custom interval in ms / seconds / minutes / hours.
- Run until stopped, or a set number of times.
- Your own global start / stop shortcuts (keys, combos, or mouse side buttons). Same key for both = toggle. Defaults: F6 start, F7 stop.
- The Start button gives a 3-second countdown so you can move the mouse into place; the shortcut starts instantly.
- Arabic / English UI toggle, settings saved automatically.

**How it works:** clicks and keys are sent through a virtual input device (`/dev/uinput`), and shortcuts are read from `/dev/input`, so it works on any desktop. The one-time setup adds a udev rule (`/etc/udev/rules.d/70-penguin-clicker.rules`) that gives the logged-in user access to those devices. If it can't be done from the app, run `bash install.sh --setup`.

**Uninstall:** `bash install.sh --uninstall` (or the one-liner with `bash -s -- --uninstall`)

Needs Python 3 and GTK 4 for Python (`python-gobject` + `gtk4`). No pip packages.
