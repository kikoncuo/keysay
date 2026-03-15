"""Screenshot capture utility for keysay."""

import os
import subprocess
import tempfile


def capture_screen() -> str:
    """Capture the main display to a temporary PNG file.

    Returns the path to the PNG. Caller must clean up with os.unlink().
    """
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    subprocess.run(["screencapture", "-x", "-C", path], check=True)
    return path
