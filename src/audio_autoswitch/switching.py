"""Applying presets, and reading back which one is live.

The live preset is read from Windows, not remembered: it is whichever preset's two
microphones match the current *Default Device* and *Default Communication Device*.
Change either role elsewhere -- Windows' own sound settings, another app -- and neither
preset matches, so there is no live preset at all until one is applied again.

Switching is all or nothing. A preset sets both the *Default Device* and the *Default
Communication Device*, so unless both of its microphones are connected, nothing moves.
"""

from __future__ import annotations

from .audio import ROLE_COMMUNICATIONS, ROLE_DEFAULT, set_default_microphone
from .config import Config, Preset

Defaults = tuple[str | None, str | None]


def _roles(preset: Preset):
    return ((preset.default, ROLE_DEFAULT), (preset.comm, ROLE_COMMUNICATIONS))


def is_ready(config: Config, index: int, available: set[str]) -> bool:
    """True when both of the preset's microphones are assigned and connected."""
    return all(
        slot.configured and slot.id in available for slot in config.presets[index].slots
    )


def live_preset(config: Config, defaults: Defaults) -> int | None:
    """The preset Windows is actually on, or None when the roles match neither.

    Both roles have to match the same preset: a half-applied pair -- one role moved by
    hand, say -- belongs to no preset.
    """
    for index, preset in enumerate(config.presets):
        if all(slot.configured for slot in preset.slots) and defaults == (
            preset.default.id,
            preset.comm.id,
        ):
            return index
    return None


def apply_preset(config: Config, index: int, available: set[str]) -> bool:
    """Point both roles at the preset's microphones. False if it could not be done."""
    if not is_ready(config, index, available):
        return False
    for slot, roles in _roles(config.presets[index]):
        set_default_microphone(slot.id, roles)
    config.current = index
    config.save()
    return True


def other_preset(config: Config, live: int | None) -> int:
    """The preset a click moves to: the one that is not live.

    With no preset live, a click restores the one this app applied last rather than
    guessing -- so the icon goes from minus back to a number the user recognises.
    """
    return config.current if live is None else 1 - live
