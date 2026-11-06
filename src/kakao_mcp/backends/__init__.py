"""OS-specific UI adapters. Import Windows modules only on Windows."""
import sys


class UnsupportedDesktop:
    def __getattr__(self, name):
        raise RuntimeError(
            "Native KakaoTalk automation is implemented only for Windows. "
            "macOS adapter is not implemented; common services and diagnostics are available."
        )


def create_desktop():
    if sys.platform == "win32":
        from .windows_board import Win32BoardDesktop
        return Win32BoardDesktop()
    return UnsupportedDesktop()


class ControllerProxy:
    """Keep legacy chat tools loadable without importing Win32 during startup."""
    def __getattr__(self, name):
        if sys.platform != "win32":
            return getattr(UnsupportedDesktop(), name)
        from .. import controller
        return getattr(controller, name)
