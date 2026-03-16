"""Global hotkey listener using CGEventTap via pyobjc-framework-Quartz.

The tap callback ONLY sets self.pressed — zero other work. The main thread
polls this boolean to detect transitions. This eliminates all threading
race conditions.
"""

import ctypes
import ctypes.util
import logging
import threading

from Quartz import (
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventMaskBit,
    CGEventTapCreate,
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CFRunLoopStop,
    kCGEventFlagsChanged,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventTapOptionListenOnly,
    kCGHIDEventTap,
    kCGKeyboardEventAutorepeat,
    kCFRunLoopCommonModes,
)

logger = logging.getLogger(__name__)

_MODIFIER_FLAG_BITS: dict[int, int] = {
    61: 0x00000040,  # Right Option
    58: 0x00000020,  # Left Option
    54: 0x00000010,  # Right Command
    55: 0x00000008,  # Left Command
    60: 0x00000004,  # Right Shift
    56: 0x00000002,  # Left Shift
    62: 0x00002000,  # Right Control
    59: 0x00000001,  # Left Control
    63: 0x00800000,  # Fn / Globe
    57: 0x00010000,  # Caps Lock
}


def check_accessibility() -> bool:
    try:
        path = ctypes.util.find_library("ApplicationServices")
        if path:
            lib = ctypes.cdll.LoadLibrary(path)
            lib.AXIsProcessTrusted.restype = ctypes.c_bool
            return lib.AXIsProcessTrusted()
    except Exception:
        pass
    return True


class HotkeyListener:
    """Listens for a global hotkey. Poll `self.pressed` from the main thread."""

    def __init__(self, keycode: int = 61, is_modifier: bool = True):
        self._keycode = keycode
        self._is_modifier = is_modifier
        self.pressed = False  # Polled by the main thread
        self.fn_v_pressed = False  # Fn+V combo detected
        self._fn_held = False  # Track Fn key state
        self._thread: threading.Thread | None = None
        self._run_loop = None
        self._run_loop_ready = threading.Event()

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._run_loop_ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._run_loop_ready.wait(timeout=5.0)

    def stop(self):
        if self._run_loop is not None:
            CFRunLoopStop(self._run_loop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._run_loop = None
        self.pressed = False

    def update_keycode(self, keycode: int, is_modifier: bool):
        self._keycode = keycode
        self._is_modifier = is_modifier
        self.pressed = False

    def _run(self):
        mask = (
            CGEventMaskBit(kCGEventKeyDown)
            | CGEventMaskBit(kCGEventKeyUp)
            | CGEventMaskBit(kCGEventFlagsChanged)
        )
        tap = CGEventTapCreate(
            kCGHIDEventTap, 0, kCGEventTapOptionListenOnly,
            mask, self._tap_callback, None,
        )
        if tap is None:
            logger.error("CGEventTap creation failed — no accessibility?")
            self._run_loop_ready.set()
            return

        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        self._run_loop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(self._run_loop, source, kCFRunLoopCommonModes)
        self._run_loop_ready.set()
        logger.info("Hotkey listener started.")
        CFRunLoopRun()

    def _tap_callback(self, proxy, event_type, event, refcon):
        """MUST be non-blocking. Only sets flags."""
        try:
            # Track Fn key state for Fn+V detection
            if event_type == kCGEventFlagsChanged:
                flags = CGEventGetFlags(event)
                self._fn_held = bool(flags & 0x00800000)  # Fn/Globe bit

            # Detect Fn+V combo (V = keycode 9)
            if event_type == kCGEventKeyDown and self._fn_held:
                keycode = CGEventGetIntegerValueField(event, 6)
                if keycode == 9 and not CGEventGetIntegerValueField(event, kCGKeyboardEventAutorepeat):
                    self.fn_v_pressed = True

            # Normal hotkey detection
            if self._is_modifier:
                if event_type == kCGEventFlagsChanged:
                    flags = CGEventGetFlags(event)
                    bit = _MODIFIER_FLAG_BITS.get(self._keycode)
                    if bit:
                        new_pressed = bool(flags & bit)
                        if new_pressed != self.pressed:
                            logger.debug("Modifier %d: pressed=%s (flags=0x%08x, bit=0x%08x)",
                                         self._keycode, new_pressed, flags, bit)
                        self.pressed = new_pressed
            else:
                if event_type == kCGEventKeyDown:
                    if not CGEventGetIntegerValueField(event, kCGKeyboardEventAutorepeat):
                        if CGEventGetIntegerValueField(event, 6) == self._keycode:
                            self.pressed = True
                elif event_type == kCGEventKeyUp:
                    if CGEventGetIntegerValueField(event, 6) == self._keycode:
                        self.pressed = False
        except Exception:
            pass
        return event
