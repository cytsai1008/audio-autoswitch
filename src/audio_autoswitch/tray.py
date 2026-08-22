"""System tray app: one-click microphone switching between two presets."""

from __future__ import annotations

import threading

import comtypes
import pystray
from _ctypes import COMError
from PIL import Image

from .audio import active_microphone_ids, default_microphone_ids, list_microphones
from .config import Config
from .icons import blocked_icon, tray_icon, unset_icon
from .switching import apply_preset, is_ready, live_preset, other_preset

POLL_SECONDS = 2.0
_ICON_SIZE = 64


class TrayApp:
    def __init__(self) -> None:
        self.config = Config.load()
        self.devices = []
        self.available: set[str] = set()
        # The endpoints Windows is on, and the preset they match -- None for neither.
        self.defaults: tuple[str | None, str | None] = (None, None)
        self.live: int | None = None
        # Preset whose switch was refused for want of a microphone, or None.
        self.blocked: int | None = None
        self._stop = threading.Event()
        self._icon_cache: dict[str, Image.Image] = {}
        self._refresh_state()
        self.icon = pystray.Icon(
            "audio-autoswitch",
            icon=self._image(),
            title=self._tooltip(),
            menu=pystray.Menu(self._menu_items),
        )

    # ---------------------------------------------------------------- state

    def _refresh_state(self) -> bool:
        """Re-read Windows' state. True if anything the tray shows changed."""
        before = (self.available, self.defaults, self.blocked)
        self.available = active_microphone_ids()

        if self.available != before[0]:
            # Endpoints came or went: reread the names the menu is built from.
            self.devices = list_microphones()
            self.config.refresh_names(self.devices)
        # Which preset is live is read back from Windows every tick, so a role moved
        # elsewhere surfaces here instead of being papered over.
        self.defaults = default_microphone_ids()
        self.live = live_preset(self.config, self.defaults)
        # The microphone we were waiting for is back; drop the warning.
        if self.blocked is not None and is_ready(
            self.config, self.blocked, self.available
        ):
            self.blocked = None
        return before != (self.available, self.defaults, self.blocked)

    def _name_of(self, device_id: str | None) -> str:
        """A friendly name for an endpoint id, from whatever we know of it."""
        if not device_id:
            return "none"
        for device in self.devices:
            if device.id == device_id:
                return device.name
        for preset in self.config.presets:
            for slot in preset.slots:
                if slot.id == device_id and slot.name:
                    return slot.name
        return "unknown device"

    # ---------------------------------------------------------------- icon

    def _image(self) -> Image.Image:
        if self.blocked is not None:
            key = "blocked"
        elif self.live is None:
            key = "unset"
        else:
            key = str(self.live)
        if key not in self._icon_cache:
            if key == "blocked":
                image = blocked_icon(_ICON_SIZE)
            elif key == "unset":
                image = unset_icon(_ICON_SIZE)
            else:
                image = tray_icon(self.live, _ICON_SIZE)
            self._icon_cache[key] = image
        return self._icon_cache[key]

    def _tooltip(self) -> str:
        if self.blocked is not None:
            return f"Cannot switch: Preset {self.blocked + 1} is unavailable"
        heading = (
            "Current: neither preset"
            if self.live is None
            else f"Current: Preset {self.live + 1}"
        )
        return (
            f"{heading}\n"
            f"Default: {self._name_of(self.defaults[0])}\n"
            f"Communications: {self._name_of(self.defaults[1])}"
        )[:127]

    # ---------------------------------------------------------------- menu

    def _menu_items(self):
        """Rebuilt each time the menu opens, so it always matches reality."""
        # Hidden default action: left-clicking the tray icon switches presets.
        yield pystray.MenuItem(
            "Switch", lambda: self.switch(), default=True, visible=False
        )
        current = "neither preset" if self.live is None else f"Preset {self.live + 1}"
        yield pystray.MenuItem(
            f"Current: {current}",
            pystray.Menu(self._preset_items()),
        )
        yield pystray.Menu.SEPARATOR
        for index in (0, 1):
            for comm in (False, True):
                role = " (Communications)" if comm else ""
                yield pystray.MenuItem(
                    f"Device {index + 1}{role}",
                    pystray.Menu(self._device_items(index, comm)),
                )
        yield pystray.Menu.SEPARATOR
        yield pystray.MenuItem("Quit", self.quit)

    def _preset_items(self):
        """The `Current` submenu: pick a preset outright."""

        def items():
            for index in (0, 1):
                yield pystray.MenuItem(
                    f"Preset {index + 1}",
                    self._on_pick_preset(index),
                    checked=self._is_current_preset(index),
                    # A preset missing a microphone cannot be applied, so offer it
                    # greyed out rather than letting the click do nothing.
                    enabled=is_ready(self.config, index, self.available),
                    radio=True,
                )

        return items

    def _device_items(self, index: int, comm: bool):
        """Assignment submenu: every microphone Windows can see."""

        def items():
            if not self.devices:
                yield pystray.MenuItem("(no microphones found)", None, enabled=False)
                return
            for device in self.devices:
                yield pystray.MenuItem(
                    device.name,
                    self._on_assign(index, comm, device),
                    checked=self._is_assigned(index, comm, device),
                    radio=True,
                )

        return items

    # pystray inspects a callback's argument count, so these must be built by
    # closure -- a `lambda dev=device:` reads as one-argument and is handed the icon.

    def _on_pick_preset(self, index: int):
        return lambda: self.apply(index)

    def _is_current_preset(self, index: int):
        return lambda _: self.live == index

    def _on_assign(self, index: int, comm: bool, device):
        return lambda: self.assign(index, comm, device)

    def _is_assigned(self, index: int, comm: bool, device):
        return lambda _: self.config.presets[index].slot(comm).id == device.id

    # ------------------------------------------------------------- actions

    def apply(self, index: int) -> None:
        """Switch to a preset, or mark the tray blocked if it cannot be applied."""
        try:
            applied = apply_preset(self.config, index, self.available)
        except OSError:
            applied = False  # the endpoint went away between the check and the call
        self.blocked = None if applied else index
        self._sync()

    def switch(self) -> None:
        """Left click: move to the other preset, setting both roles."""
        self.apply(other_preset(self.config, self.live))

    def assign(self, index: int, comm: bool, device) -> None:
        self.config.assign(index, comm, device)
        if index == self.live and is_ready(self.config, index, self.available):
            self.apply(index)  # keep the live preset honest after an edit
        else:
            self._sync()

    def quit(self) -> None:
        self._stop.set()
        self.icon.stop()

    # --------------------------------------------------------------- loop

    def _sync(self) -> None:
        self._refresh_state()
        self.icon.icon = self._image()
        self.icon.title = self._tooltip()
        self.icon.update_menu()

    def _watch(self) -> None:
        """Notice microphones being plugged in and unplugged."""
        comtypes.CoInitialize()
        try:
            while not self._stop.wait(POLL_SECONDS):
                try:
                    changed = self._refresh_state()
                except (OSError, COMError):
                    continue  # endpoints changed mid-enumeration; retry next tick
                if changed:
                    self.icon.icon = self._image()
                    self.icon.title = self._tooltip()
                    self.icon.update_menu()
        finally:
            comtypes.CoUninitialize()

    def run(self) -> None:
        threading.Thread(target=self._watch, daemon=True).start()
        self.icon.run()


def main() -> None:
    TrayApp().run()


if __name__ == "__main__":
    main()
