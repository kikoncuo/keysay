"""System-wide text insertion using macOS Accessibility API.

Primary path: AX insertion via AXSelectedText (works for native + many web fields).
Fallback: clipboard + Cmd+V (only when AX fails, target app must be focused).

Returns status: "pasted", "clipboard", or "failed".
"""

import logging
import os
import time

logger = logging.getLogger(__name__)

_DBG_PATH = os.path.expanduser("~/Library/Application Support/keysay/debug.log")


def _dbg(msg: str):
    """Write directly to debug log (survives PyInstaller stderr redirect)."""
    try:
        with open(_DBG_PATH, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} [paster] {msg}\n")
            f.flush()
    except Exception:
        pass


def _import_ax():
    """Import AX functions from the correct module."""
    try:
        from ApplicationServices import (
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
            AXUIElementSetAttributeValue,
        )
        return AXUIElementCreateApplication, AXUIElementCopyAttributeValue, AXUIElementSetAttributeValue
    except ImportError:
        from Quartz import (
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
            AXUIElementSetAttributeValue,
        )
        return AXUIElementCreateApplication, AXUIElementCopyAttributeValue, AXUIElementSetAttributeValue


def _activate_app(app) -> None:
    """Bring a saved NSRunningApplication back to the foreground."""
    if app is None:
        return
    try:
        app.activateWithOptions_(1 << 1)  # NSApplicationActivateIgnoringOtherApps
        time.sleep(0.15)  # Wait for focus to settle
    except Exception as e:
        logger.debug("Failed to activate app: %s", e)


def _get_clipboard() -> str | None:
    """Read the current clipboard text."""
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString
        pb = NSPasteboard.generalPasteboard()
        return pb.stringForType_(NSPasteboardTypeString)
    except Exception:
        return None


def _copy_to_clipboard(text: str):
    """Copy text to the system clipboard."""
    from AppKit import NSPasteboard, NSPasteboardTypeString

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def _insert_via_accessibility(text: str, target_app=None) -> bool:
    """Try to insert text at the cursor using the Accessibility API.

    Uses the target app's PID (captured at hotkey press time) to find the
    focused element, regardless of which app is currently frontmost.
    """
    try:
        from AppKit import NSWorkspace
        AXCreate, AXCopy, AXSet = _import_ax()

        # Use target app if provided, otherwise try frontmost
        if target_app is not None:
            pid = target_app.processIdentifier()
            app_name = target_app.localizedName() or "unknown"
        else:
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                return False
            pid = app.processIdentifier()
            app_name = app.localizedName() or "unknown"

        _dbg(f"AX: targeting {app_name} (pid={pid})")

        ax_app = AXCreate(pid)

        err, focused = AXCopy(ax_app, "AXFocusedUIElement", None)
        if err != 0 or focused is None:
            _dbg(f"AX: no focused element in {app_name} (err={err})")
            return False

        # Log the role for debugging (but don't skip any type)
        err, role = AXCopy(focused, "AXRole", None)
        role_str = str(role) if err == 0 and role is not None else "unknown"
        _dbg(f"AX: focused role={role_str} in {app_name}")

        # Try AXSelectedText insertion (works for most text fields)
        err, sel_range = AXCopy(focused, "AXSelectedTextRange", None)
        _dbg(f"AX: AXSelectedTextRange err={err}, has_range={sel_range is not None}")
        if err == 0 and sel_range is not None:
            err = AXSet(focused, "AXSelectedText", text)
            _dbg(f"AX: AXSelectedText set err={err}")
            if err == 0 or err is None:
                _dbg(f"AX: insertion OK via AXSelectedText in {app_name}")
                return True

        # Try setting AXValue directly as alternative (some fields support this)
        err, current_val = AXCopy(focused, "AXValue", None)
        _dbg(f"AX: AXValue read err={err}, has_val={current_val is not None}")
        if err == 0 and current_val is not None:
            new_val = str(current_val) + text
            err = AXSet(focused, "AXValue", new_val)
            _dbg(f"AX: AXValue set err={err}")
            if err == 0 or err is None:
                _dbg(f"AX: insertion OK via AXValue in {app_name}")
                return True

        _dbg(f"AX: all methods failed for {app_name} (role={role_str})")
        return False

    except Exception as e:
        logger.debug("AX insertion exception: %s", e)
        return False


def _simulate_cmd_v():
    """Simulate Cmd+V keystroke via CGEvent (hardware-level tap)."""
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventPost,
        CGEventSetFlags,
        kCGHIDEventTap,
        kCGEventFlagMaskCommand,
    )

    logger.debug("Sending Cmd+V via kCGHIDEventTap")

    down = CGEventCreateKeyboardEvent(None, 0x09, True)
    CGEventSetFlags(down, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, down)

    time.sleep(0.05)

    up = CGEventCreateKeyboardEvent(None, 0x09, False)
    CGEventSetFlags(up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, up)


def paste_text(
    text: str,
    clipboard_fallback: bool = True,
    preserve_clipboard: bool = False,
    target_app=None,
) -> str:
    """Insert text at the current cursor position.

    Args:
        text: Text to insert.
        clipboard_fallback: If True, fall back to Cmd+V when AX fails.
        preserve_clipboard: If True, don't touch the system clipboard.
            The text is inserted via AX only. If AX fails, the text is
            stored internally and the user can paste with Fn+V.
        target_app: NSRunningApplication captured at hotkey press time.

    Returns:
        "pasted"    — text was inserted via Cmd+V
        "clipboard" — text copied to clipboard only (preserve mode)
        "failed"    — nothing worked
    """
    if not text:
        return "failed"

    app_name = target_app.localizedName() if target_app else "none"
    _dbg(f"activating target: {app_name}")
    _activate_app(target_app)

    if preserve_clipboard:
        # Don't touch the real clipboard — try AX insertion only
        _dbg("preserve_clipboard: trying AX insertion")
        if _insert_via_accessibility(text, target_app):
            _dbg("AX insertion succeeded")
            return "pasted"
        _dbg("AX failed — text stored for Fn+V")
        return "clipboard"  # caller shows "Fn+V to paste"

    # Normal flow: put on clipboard + Cmd+V
    _copy_to_clipboard(text)

    if clipboard_fallback:
        _dbg(f"pasting via Cmd+V into {app_name}")
        time.sleep(0.05)
        _simulate_cmd_v()
        _dbg("Cmd+V sent")
        return "pasted"

    return "clipboard"


def paste_from_buffer(text: str, target_app=None) -> str:
    """Paste stored text via Fn+V — briefly uses clipboard then restores.

    Called when user presses Fn+V to paste from keysay's internal buffer.
    Saves clipboard, pastes, restores after a delay.
    """
    if not text:
        return "failed"

    saved = _get_clipboard()
    _dbg(f"Fn+V: saved clipboard ({len(saved or '')} chars)")

    _activate_app(target_app)
    _copy_to_clipboard(text)
    time.sleep(0.05)
    _simulate_cmd_v()
    _dbg("Fn+V: Cmd+V sent")

    # Restore after generous delay
    import threading

    def _restore():
        time.sleep(1.5)
        if saved is not None:
            _copy_to_clipboard(saved)
        _dbg("Fn+V: clipboard restored")

    threading.Thread(target=_restore, daemon=True).start()
    return "pasted"
