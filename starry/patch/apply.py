#!/usr/bin/env python3
"""Apply the starry changes to a fresh checkout, by anchor.

GitHub's code search does not index WMKeyboardService.kt (65k lines), so a
unified diff cannot be checked from the phone that writes it: the first attempt
missed the comment block above fitImeWindowHeight and git apply refused the
hunk. Anchoring on a short unique line avoids that.

Three edits, applied in order:

1. WMKeyboardService.kt - the floating-window fix (#1347 / #1297).
2. app/src/main/res - drop the translated values-* dirs except en and zh.

   Upstream's machine translations carry several unnumbered %s placeholders
   ("Multiple substitutions specified in non-positional format"), which AAPT2
   rejects inside :app:mergeEnDebugResources, so main cannot build at all.
   localeFilters does not help: it is applied at link time, after the merge
   that fails. Removing the directories before Gradle runs is the only lever;
   it happens on the runner's checkout and never touches the repository.

Usage:
    apply.py            apply
    apply.py --check    report what would happen, change nothing

Exits non-zero when an anchor is missing, duplicated or already replaced, so CI
fails loudly instead of shipping a build that silently lacks the changes.
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


def drop_locales(check):
    if not RES.is_dir():
        return fail(f"missing dir: {RES}")

    targets = []
    for entry in sorted(RES.iterdir()):
        if not entry.is_dir():
            continue
        match = LANG_DIR.match(entry.name)
        if not match:
            continue
        if match.group(1) in KEEP_LANGS:
            continue
        targets.append(entry)

    if not targets:
        print("locales: nothing to drop")
        return 0

    names = ", ".join(p.name for p in targets[:6])
    if check:
        print(f"locales: would drop {len(targets)} dirs ({names}, ...)")
        return 0

    for entry in targets:
        shutil.rmtree(entry)
    print(f"locales: dropped {len(targets)} dirs ({names}, ...)")
    return 0


def main():
    check = "--check" in sys.argv
    rc = 0
    rc |= apply_service(check)
    rc |= drop_locales(check)
    return rc


if __name__ == "__main__":
    sys.exit(main())
