#!/usr/bin/env python3
"""Apply the starry patch to a fresh checkout.

One change: the settings app's keyboard test field now closes with the
keyboard on floating and freeform windows too.

- KeyboardPreview.kt reads KeyboardControls.windowShown beside the window's
  own IME inset, so a floating or freeform window, which the system moves
  clear of the keyboard and never hands a keyboard inset, still notices the
  keyboard arriving and leaving. Before this the field stayed open, stuck
  over the screen, after the keyboard had gone.
- KeyboardControls.kt carries that word: a process-local flow the keyboard
  sets as its window shows and hides.
- WMKeyboardService.kt sets it in onShowWindow, onHideWindow and the service
  teardown.

The patch is a real `git diff` against d30445fe (2026-11-10), the commit its
blobs match, and is applied with `git apply` rather than by hand. Nothing here
is tied to a line number, and a tree that already carries the change is left
alone, so re-running this or building a newer tree does not apply it twice.

Usage:
    apply.py            apply
    apply.py --check    report what would happen, change nothing
"""

import subprocess
import sys
from pathlib import Path

PATCH = Path("starry/patch/0001-keyboard-preview-window-shown.patch")

SERVICE = Path(
    "feature/ime/src/main/java/com/wasimaster/wmkeyboard/ime/WMKeyboardService.kt"
)
MARK = "KeyboardControls.setWindowShown"


def already_applied():
    if not SERVICE.is_file():
        return False
    return MARK in SERVICE.read_text(encoding="utf-8")


def run_git_apply(check):
    cmd = ["git", "apply"]
    if check:
        cmd.append("--check")
    cmd.append(str(PATCH))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        print(
            f"patch: git apply {'check ' if check else ''}failed; "
            "the tree no longer matches the diff",
            file=sys.stderr,
        )
    return result.returncode


def main():
    check = "--check" in sys.argv

    if not PATCH.is_file():
        print(f"patch: missing file: {PATCH}", file=sys.stderr)
        return 1

    if not SERVICE.is_file():
        print(f"patch: missing file: {SERVICE}", file=sys.stderr)
        return 1

    if already_applied():
        print("patch: already applied")
        return 0

    print(f"patch: {'checking' if check else 'applying'} {PATCH.name}")
    return run_git_apply(check)


if __name__ == "__main__":
    sys.exit(main())
