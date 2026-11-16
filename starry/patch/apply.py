#!/usr/bin/env python3
"""Apply the floating-window fix by anchor instead of by hunk.

GitHub's code search does not index WMKeyboardService.kt (about 7,700 lines),
so a unified diff cannot be checked from the phone that writes it: the first
attempt missed the comment block above fitImeWindowHeight and git apply refused
the hunk. The function's signature is short, unique, and does not move, so the
edit is anchored there and the comments around it can drift freely.

Usage:
    apply.py            apply
    apply.py --check    verify the anchor, change nothing

Exits non-zero when the anchor is missing or appears more than once, so CI
fails loudly instead of producing a build that silently lacks the fix.
"""

import sys
from pathlib import Path

SERVICE = Path(
    "feature/ime/src/main/java/com/wasimaster/wmkeyboard/ime/WMKeyboardService.kt"
)
ANCHOR = "    private fun fitImeWindowHeight(win: android.view.Window) {"
MARK = "dockWindowBeforeHide"

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


def main():
    check = "--check" in sys.argv

    if not SERVICE.is_file():
        return fail(f"missing file: {SERVICE}")

    src = SERVICE.read_text(encoding="utf-8")

    if MARK in src:
        print("already applied, nothing to do")
        return 0

    existing = src.count("override fun hideWindow")
    if existing:
        return fail(
            "hideWindow is already overridden in this file; the fix would define "
            "it twice. Re-anchor the patch on that override instead."
        )

    hits = src.count(ANCHOR)
    if hits != 1:
        return fail(f"anchor found {hits} time(s), expected exactly 1")

    if check:
        print("anchor ok (1 hit), nothing written")
        return 0

    SERVICE.write_text(src.replace(ANCHOR, BLOCK + ANCHOR, 1), encoding="utf-8")
    print("applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
