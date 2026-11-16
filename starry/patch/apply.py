#!/usr/bin/env python3
"""Apply the starry changes to a fresh checkout.

Upstream main has not compiled since 2026-11-11 - every CI run is red and the
backlog includes a package-qualified callable reference, ambiguous imports and
translated strings AAPT2 refuses - so the build can also check out an older,
known-green commit. Everything here adapts to whichever tree it finds:

1. WMKeyboardService.kt - the floating-window fix (#1347 / #1297), anchored on
   the function signature because GitHub's code search does not index a 65k
   line file and a hunk cannot be verified from a phone.

   Two shapes: where the tree has the fullHeightWindow switch (>= 0.6.7) the
   switch is honoured and showWindow re-tallies the window; where it does not
   (11-10 and earlier) the window is always tall, so only the hide needs the
   short frame.

2. Translated strings - drop the entries whose text carries several unnumbered
   %s placeholders, which AAPT2 rejects in :app:mergeEnDebugResources. Deleting
   the entry falls back to the English text; the other strings in that locale
   stay untouched. Trees whose translations are clean lose nothing.

3. LayoutEditorBoard.kt - `ime.ui::customToolSlot` is a callable reference on a
   package, which Kotlin rejects ("Expression expected, but package name
   found"). Turned into a lambda, when that line is present.

Usage:
    apply.py            apply
    apply.py --check    report what would happen, change nothing
"""

import re
import sys
from pathlib import Path

SERVICE = Path(
    "feature/ime/src/main/java/com/wasimaster/wmkeyboard/ime/WMKeyboardService.kt"
)
ANCHOR = "    private fun fitImeWindowHeight(win: android.view.Window) {"
MARK = "dockWindowBeforeHide"

RES = Path("app/src/main/res")
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

BLOCK_MODERN = '''    /**
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

BLOCK_LEGACY = '''    /**
     * #1297: HarmonyOS animates the IME window's whole frame away when it
     * hides, so a full-height frame turns into a long squeeze. Dropping to the
     * keys' own height the instant before the hide keeps that animation short,
     * while the window stays tall the whole time it is shown so the app above
     * is not squashed (#1347).
     */
    override fun hideWindow() {
        if (huaweiDevice) dockWindowBeforeHide()
        super.hideWindow()
    }

    private fun dockWindowBeforeHide() {
        if (imeWindowPlatformSized) return
        if (windowBlurring) return
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

    modern = "fullHeightWindow" in src
    shape = "modern (fullHeightWindow honoured)" if modern else "legacy (always tall)"

    if check:
        print(f"service: anchor ok, shape {shape}")
        return 0

    SERVICE.write_text(
        src.replace(ANCHOR, (BLOCK_MODERN if modern else BLOCK_LEGACY) + ANCHOR, 1),
        encoding="utf-8",
    )
    print(f"service: applied, shape {shape}")
    return 0


def drop_bad_strings(check):
    if not RES.is_dir():
        return fail(f"missing dir: {RES}")

    total = 0
    detail = []

    for folder in sorted(RES.iterdir()):
        if not folder.is_dir() or not LANG_DIR.match(folder.name):
            continue

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
        detail.append(f"{folder.name}:{len(removed)}")

        if not check:
            strings.write_text(updated, encoding="utf-8")

    if not total:
        print("strings: nothing to drop")
        return 0

    joined = ", ".join(detail[:8])
    verb = "would drop" if check else "dropped"
    print(f"strings: {verb} {total} entries ({joined})")
    return 0


def fix_editor(check):
    if not EDITOR.is_file():
        print("editor: file absent, skipping")
        return 0

    src = EDITOR.read_text(encoding="utf-8")

    if EDITOR_GOOD in src:
        print("editor: already fixed")
        return 0

    if EDITOR_BAD not in src:
        print("editor: nothing to fix")
        return 0

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
    rc |= drop_bad_strings(check)
    rc |= fix_editor(check)
    return rc


if __name__ == "__main__":
    sys.exit(main())
