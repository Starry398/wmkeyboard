#!/usr/bin/env python3
"""Apply the starry changes by anchor instead of by hunk.

GitHub's code search does not index WMKeyboardService.kt (about 7,700 lines),
so a unified diff cannot be checked from the phone that writes it: the first
attempt missed the comment block above fitImeWindowHeight and git apply refused
the hunk. Both edits therefore anchor on a short, unique line and let the text
around it drift freely.

Two edits, applied in order:

1. WMKeyboardService.kt - the floating-window fix (#1347 / #1297).
2. app/build.gradle.kts - keep only the locales this fork uses. Upstream's
   machine-translated strings carry several unnumbered %s placeholders, which
   AAPT2 refuses with "Multiple substitutions specified in non-positional
   format" and the build dies in :app:mergeEnDebugResources. Dropping those
   directories before the resource compiler sees them fixes the build and
   shrinks the apk.

Usage:
    apply.py            apply
    apply.py --check    verify both anchors, change nothing

Exits non-zero when an anchor is missing, duplicated, or already replaced, so
CI fails loudly instead of producing a build that silently lacks the changes.
"""

import re
import sys
from pathlib import Path

SERVICE = Path(
    "feature/ime/src/main/java/com/wasimaster/wmkeyboard/ime/WMKeyboardService.kt"
)
ANCHOR = "    private fun fitImeWindowHeight(win: android.view.Window) {"
MARK = "dockWindowBeforeHide"

GRADLE = Path("app/build.gradle.kts")
GRADLE_MARK = "starryLocaleFilters"

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
        return fail(
            "service: hideWindow is already overridden here; the fix would define "
            "it twice. Re-anchor on that override instead."
        )

    hits = src.count(ANCHOR)
    if hits != 1:
        return fail(f"service: anchor found {hits} time(s), expected exactly 1")

    if check:
        print("service: anchor ok (1 hit), nothing written")
        return 0

    SERVICE.write_text(src.replace(ANCHOR, BLOCK + ANCHOR, 1), encoding="utf-8")
    print("service: applied")
    return 0


def apply_gradle(check):
    if not GRADLE.is_file():
        return fail(f"missing file: {GRADLE}")

    src = GRADLE.read_text(encoding="utf-8")

    if GRADLE_MARK in src:
        print("gradle: already applied")
        return 0

    if "resourceConfigurations" in src:
        return fail(
            "gradle: resourceConfigurations is already set in app/build.gradle.kts"
        )

    match = re.search(r"(?m)^([ \t]*)defaultConfig[ \t]*\{", src)
    if not match:
        return fail("gradle: no defaultConfig block found in app/build.gradle.kts")

    pad = match.group(1) + "    "
    block = (
        match.group(0)
        + "\n"
        + pad
        + "// "
        + GRADLE_MARK
        + ": only the locales this fork uses. The machine-translated\n"
        + pad
        + "// strings in the other ~100 locales carry several unnumbered %s\n"
        + pad
        + "// placeholders, which AAPT2 rejects in :app:mergeEnDebugResources.\n"
        + pad
        + 'resourceConfigurations += listOf("en", "zh")\n'
    )

    if check:
        print("gradle: anchor ok, nothing written")
        return 0

    GRADLE.write_text(src[: match.start()] + block + src[match.end() :], encoding="utf-8")
    print("gradle: applied")
    return 0


def main():
    check = "--check" in sys.argv
    rc = 0
    rc |= apply_service(check)
    rc |= apply_gradle(check)
    return rc


if __name__ == "__main__":
    sys.exit(main())
