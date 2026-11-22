"""System controls: speaker volume and screenshots. LOW risk, so no confirmation is needed."""
from __future__ import annotations

import ctypes
import gc
from datetime import datetime
from pathlib import Path

from app.automation.app_manager import OpenResult

DEFAULT_STEP = 10  # percent per "volume up" / "volume down"


def _volume_interface():
    """The speaker volume interface (written to work with older and newer pycaw versions)."""
    from pycaw.pycaw import AudioUtilities

    device = AudioUtilities.GetSpeakers()
    volume = getattr(device, "EndpointVolume", None)
    if volume is not None:
        return volume
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume

    interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))


def _percent(volume) -> int:
    return round(volume.GetMasterVolumeLevelScalar() * 100)


def _do_volume(action: str, amount: int | None) -> OpenResult:
    volume = _volume_interface()
    current = _percent(volume)

    if action == "get":
        muted = bool(volume.GetMute())
        return OpenResult(True, f"The volume is {current} percent." + (" It is muted." if muted else ""))

    if action in ("mute", "unmute"):
        volume.SetMute(1 if action == "mute" else 0, None)
        muted = bool(volume.GetMute())  # read it back to confirm
        if action == "mute":
            return OpenResult(muted, "Muted." if muted else "I tried to mute, but Windows says it isn't muted.")
        if muted:
            return OpenResult(False, "I tried to unmute, but Windows says it is still muted.")
        return OpenResult(True, f"Unmuted. The volume is {current} percent.")

    if action == "set":
        if amount is None or not 0 <= amount <= 100:
            return OpenResult(False, "I can set the volume to a number from 0 to 100.")
        target = amount
    elif action in ("up", "down"):
        step = amount if amount else DEFAULT_STEP
        target = current + step if action == "up" else current - step
        target = max(0, min(100, target))
        if target == current:
            return OpenResult(True, f"The volume is already at {current} percent.")
    else:
        return OpenResult(False, f"I don't know how to do '{action}' with the volume.")

    volume.SetMasterVolumeLevelScalar(target / 100, None)
    if volume.GetMute() and target > 0:
        volume.SetMute(0, None)  # changing the volume while muted should be audible
    new = _percent(volume)  # read it back before claiming success
    if abs(new - target) <= 1:
        return OpenResult(True, f"The volume is {new} percent.")
    return OpenResult(False, f"I tried to set the volume to {target} percent, but Windows reports {new}.")


def adjust_volume(action: str, amount: int | None = None) -> OpenResult:
    try:
        import comtypes
        import pycaw  # noqa: F401  (checks it is installed)
    except ImportError:
        return OpenResult(False, "Volume control needs the pycaw package. Run: pip install pycaw")
    comtypes.CoInitialize()  # Windows audio needs this in every thread that uses it
    try:
        return _do_volume(action, amount)
    except Exception as exc:
        return OpenResult(False, f"I couldn't control the volume: {exc}")
    finally:
        gc.collect()  # release the audio objects before shutting COM down
        comtypes.CoUninitialize()


def take_screenshot() -> OpenResult:
    try:
        from PIL import ImageGrab
    except ImportError:
        return OpenResult(False, "Screenshots need the Pillow package. Run: pip install Pillow")
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # otherwise display scaling can crop the picture
    except (AttributeError, OSError):
        pass
    folder = Path.home() / "Pictures" / "NOVA Screenshots"
    path = folder / f"nova-{datetime.now():%Y%m%d-%H%M%S}.png"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(all_screens=True).save(path)
    except Exception as exc:
        return OpenResult(False, f"I couldn't take the screenshot: {exc}")
    if path.exists() and path.stat().st_size > 0:
        return OpenResult(True, "Screenshot saved in Pictures, in the NOVA Screenshots folder.")
    return OpenResult(False, "I tried, but the screenshot file wasn't saved.")