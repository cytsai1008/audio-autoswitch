"""Persisted presets, stored in %APPDATA%/audio-autoswitch/config.json.

A preset is a pair of microphones: one for Windows' *Default Device* and one for its
*Default Communication Device*. Switching applies both at once.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .audio import Device, list_microphones


def config_path() -> Path:
    base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
    return Path(base) / "audio-autoswitch" / "config.json"


@dataclass
class Slot:
    id: str = ""
    name: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.id)


@dataclass
class Preset:
    default: Slot = field(default_factory=Slot)
    comm: Slot = field(default_factory=Slot)

    def slot(self, comm: bool) -> Slot:
        return self.comm if comm else self.default

    def assign(self, comm: bool, device: Device) -> None:
        slot = Slot(device.id, device.name)
        if comm:
            self.comm = slot
        else:
            self.default = slot

    @property
    def slots(self):
        return (self.default, self.comm)


@dataclass
class Config:
    presets: list[Preset] = field(default_factory=lambda: [Preset(), Preset()])
    # Preset last applied; drives the fallback icon and the first switch.
    current: int = 0

    @classmethod
    def load(cls) -> "Config":
        path = config_path()
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                presets = [
                    Preset(
                        default=Slot(**entry.get("default", {})),
                        comm=Slot(**entry.get("comm", {})),
                    )
                    for entry in raw["presets"][:2]
                ]
                while len(presets) < 2:
                    presets.append(Preset())
                return cls(presets=presets, current=int(raw.get("current", 0)))
            except (KeyError, ValueError, TypeError):
                pass  # missing, corrupt, or an older layout: start fresh
        cfg = cls()
        cfg.autodetect()
        cfg.save()
        return cfg

    def save(self) -> None:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    def autodetect(self) -> None:
        """Give each empty preset a microphone, used for both of its roles."""
        taken = {s.id for p in self.presets for s in p.slots if s.configured}
        available = [d for d in list_microphones() if d.id not in taken]
        for preset in self.presets:
            if any(s.configured for s in preset.slots) or not available:
                continue
            device = available.pop(0)
            preset.assign(False, device)
            preset.assign(True, device)

    def assign(self, index: int, comm: bool, device: Device) -> None:
        self.presets[index].assign(comm, device)
        self.save()

    def refresh_names(self, devices: list[Device]) -> bool:
        """Keep stored labels in sync when Windows renames an endpoint."""
        by_id = {d.id: d.name for d in devices}
        changed = False
        for preset in self.presets:
            for slot in preset.slots:
                new = by_id.get(slot.id)
                if new and new != slot.name:
                    slot.name, changed = new, True
        if changed:
            self.save()
        return changed
