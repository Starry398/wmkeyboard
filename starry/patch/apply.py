#!/usr/bin/env python3
"""Apply the starry changes to a fresh checkout.

Upstream main has not compiled since 2026-11-11 (every CI run is red), so this
script also carries the two repairs that make it build at all. Everything here
runs on the runner's checkout and never touches the repository.

1. WMKeyboardService.kt - the floating-window fix (#1347 / #1297), anchored on
   the function signature because GitHub's code search does not index a 65k
   line file and a hunk cannot be verified from a phone.
2. app/src/main/res - drop the translated values-* dirs except en and zh, then
   drop the zh entries whose text carries several unnumbered %s placeholders.
   AAPT2 rejects those in :app:mergeEnDebugResources; deleting the entry falls
   back to the English text, which is correct, where deleting the whole locale
   would have cost every other string.
3. LayoutEditorBoard.kt - `ime.ui::customToolSlot` is a callable reference on a
   package, which Kotlin rejects ("Expression expected, but package name
   found"). Turned into a lambda.

Usage:
    apply.py            apply
    apply.py --check    report what would happen, change nothing
"""

import re
import shutil
import sys
from pathlib import Path

SERVICE = Path(
    "feature/ime/src/main/java/com/wasimaster/wmkeyboard/ime/WMKeyboardService.kt"
)
ANCHOR = "    private fun fitImeWindowHeight(win: android.view.Window) {"
MARK = "dockWindowBeforeHide"

RES = Path("app/src/main/res")
KEEP_LANGS = {"en", "zh"}
LANG_DIR = re.compile(r"^values-([a-z]{2,3})(?:-r([A-Z]{2}))?$")
STRING_ENTRY = re.compile(r'<string name="([^"]+)"[^>]*>.*?</string>[ \t]*\n?', re.S)
UNNUMBERED = re.compile(r"%(?!\d+\$)(?=[a-zA-Z])")

EDITOR = Path(
    "feature/ime/src/main/java/com/wasimaster/wmkeyboard/app/LayoutEditorBoard.kt"
)
EDITOR_BAD = "action.custom?.let(com.wasimaster.wmkeyboard.ime.ui::customToolSlot)"
EDITOR_GOOD = (
    "action.custom?.let { com.wasimaster.wmkeyboard.ime.ui.customToolSlot(it) }"
)

BLOCK = '''    /**
     * #1347: a floating app on HarmonyOS is laid out against the IME window's
     * whole frame, and a frame as short as the keys squashed it down to the
     * field being typed in. The tall frame keeps it whole, but that frame is
     * what HarmonyOS animates away as one piece when the keyboard hides
     * (#1297). So the window is tall while it shows, and the keys' own height
     * the instant before it hides.
     */
    override fun showWindow(showInput: Boolean) {
        if (huaweiDevice) window?.window?.let { fitImeWindowHeight(it) }
        super.showWindow(showInput)
    }

    override fun hideWindow() {
        if (huaweiDevice) dockWindowBeforeHide()
        super.hideWindow()
    }

    private fun dockWindowBeforeHide() {
        if (imeWindowPlatformSized) return
        if (!_uiState.value.settings.layoutBehavior.fullHeightWindow) return
        if (windowBlurring && !privacyShade.showing) return
        val win = window?.window ?: return
        try {
            val lp = win.attributes
            if (lp.height != android.view.ViewGroup.LayoutParams.WRAP_CONTENT) {
                lp.height = android.view.ViewGroup.LayoutParams.WRAP_CONTENT
                win.attributes = lp
            }
        } catch (_: Throwable) {
        }
    }

    private val huaweiDevice: Boolean
        get() = Build.MANUFACTURER.orEmpty().equals("HUAWEI", ignoreCase = true)

'''


def fail(message):
    print(message, file=sys.stderr)
    return 1


def apply_service(check):
    if not SERVICE.is_file():
        return fail(f"missing file: {SERVICE}")

    src = SERVICE.read_text(encoding="utf-8")

    if MARK in src:
        print("service: already applied")
        return 0

    if src.count("override fun hideWindow"):
        return fail("service: hideWindow is already overridden here")

    hits = src.count(ANCHOR)
    if hits != 1:
        return fail(f"service: anchor found {hits} time(s), expected exactly 1")

    if check:
        print("service: anchor ok (1 hit)")
        return 0

    SERVICE.write_text(src.replace(ANCHOR, BLOCK + ANCHOR, 1), encoding="utf-8")
    print("service: applied")
    return 0


def locale_dirs():
    if not RES.is_dir():
        return []
    out = []
    for entry in sorted(RES.iterdir()):
        if not entry.is_dir():
            continue
        match = LANG_DIR.match(entry.name)
        if match and match.group(1) in KEEP_LANGS:
            out.append(entry)
    return out


def drop_other_locales(check):
    if not RES.is_dir():
        return fail(f"missing dir: {RES}")

    targets = [
        entry
        for entry in sorted(RES.iterdir())
        if entry.is_dir()
        and LANG_DIR.match(entry.name)
        and LANG_DIR.match(entry.name).group(1) not in KEEP_LANGS
    ]

    if not targets:
        print("locales: nothing to drop")
        return 0

    names = ", ".join(p.name for p in targets[:5])
    if check:
        print(f"locales: would drop {len(targets)} dirs ({names}, ...)")
        return 0

    for entry in targets:
        shutil.rmtree(entry)
    print(f"locales: dropped {len(targets)} dirs ({names}, ...)")
    return 0


def drop_bad_strings(check):
    total = 0
    kept = []
    for folder in locale_dirs():
        strings = folder / "strings.xml"
        if not strings.is_file():
            continue

        text = strings.read_text(encoding="utf-8")
        removed = []

        def replace(match):
            if len(UNNUMBERED.findall(match.group(0))) >= 2:
                removed.append(match.group(1))
                return ""
            return match.group(0)

        updated = STRING_ENTRY.sub(replace, text)

        if not removed:
            continue

        total += len(removed)
        kept.append(f"{folder.name}: {len(removed)}")

        if not check:
            strings.write_text(updated, encoding="utf-8")

    if not total:
        print("strings: nothing to drop")
        return 0

    joined = ", ".join(kept)
    if check:
        print(f"strings: would drop {total} entries ({joined})")
        return 0

    print(f"strings: dropped {total} entries ({joined})")
    return 0


def fix_editor(check):
    if not EDITOR.is_file():
        return fail(f"missing file: {EDITOR}")

    src = EDITOR.read_text(encoding="utf-8")

    if EDITOR_GOOD in src:
        print("editor: already fixed")
        return 0

    if EDITOR_BAD not in src:
        return fail("editor: the package-qualified callable reference is not here")

    if check:
        print("editor: package-qualified reference found, would rewrite it")
        return 0

    EDITOR.write_text(src.replace(EDITOR_BAD, EDITOR_GOOD, 1), encoding="utf-8")
    print("editor: fixed")
    return 0


def main():
    check = "--check" in sys.argv
    rc = 0
    rc |= apply_service(check)
    rc |= drop_other_locales(check)
    rc |= drop_bad_strings(check)
    rc |= fix_editor(check)
    return rc


if __name__ == "__main__":
    sys.exit(main())
