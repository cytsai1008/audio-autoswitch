# audio-autoswitch

A Windows system-tray app that switches your microphone between two presets in one click.
No console, no window — everything lives in the tray icon and its menu.

A **preset** is a pair of microphones: one for Windows' *Default Device* and one for its
*Default Communication Device*. Switching applies both at once.

## Build

```powershell
uv sync
uv run python build.py           # -> dist\audio-autoswitch.exe
```

`build.py` renders the app icon, then runs PyInstaller. The result is a single ~16 MB file
that needs no Python on the target machine — copy it anywhere and double-click it. Pass
`--clean` to discard PyInstaller's caches first.

To run from source instead: `uv run audio-autoswitch`.

> Windows 11 hides newly-registered tray icons in the overflow area by default. Click the
> chevron next to the clock and drag the icon onto the taskbar to keep it visible.

## Using it

**Left click** the tray icon — switches to the other preset.

**Right click** — the menu:

```
Current: Preset 2         ▸   ( ) Preset 1
                              (•) Preset 2
──────────────
Device 1                  ▸   [every microphone]
Device 1 (Communications) ▸   [every microphone]
Device 2                  ▸   [every microphone]
Device 2 (Communications) ▸   [every microphone]
──────────────
Quit
```

| Item | |
|---|---|
| `Current: Preset N` | Which preset is live, or `neither preset`. Its submenu switches to either one outright. |
| `Device 1` | Preset 1's *Default Device* — the submenu assigns any microphone to it |
| `Device 1 (Communications)` | Preset 1's *Default Communication Device* |
| `Device 2` / `Device 2 (Communications)` | The same two for preset 2 |
| `Quit` | Exit |

Each submenu radio-marks the live choice. The whole menu is rebuilt each time it opens, so
an edit shows up immediately. Editing the preset that is currently live re-applies it, so
what you picked takes effect at once.

On first run the app auto-assigns the first two microphones Windows enumerates, one per
preset and used for both roles. Set your own from the `Device …` submenus.

### Switching is all or nothing

A preset sets both roles, so it is applied only when **both** of its microphones are
connected. If one is missing — unplugged, powered off, or never assigned — nothing moves
at all, and the tray icon becomes a red cross:

| Icon | |
|---|---|
| `1` / `2` | The live preset |
| `–` | Windows is on neither preset |
| red `✕` | The last switch was refused because a microphone was missing |

The cross clears itself as soon as that microphone comes back. A preset that cannot be
applied is also greyed out in the `Current` submenu, so the click is refused before you
make it.

### The tray reflects Windows, not memory

The live preset is read back from Windows every two seconds: it is whichever preset's two
microphones are the current *Default Device* and *Default Communication Device*. Both
roles have to match the same preset.

Change either role somewhere else — Windows' own sound settings, another app — and no
preset matches any more, so the icon becomes a minus and the menu says
`Current: neither preset`. That is a display, not a correction: nothing is put back
behind your back. A left click applies the preset this app used last, which turns the
minus back into a number; picking a preset from the menu works as always.

A half-applied pair counts as neither preset. Move only the *Default Device* to preset
2's microphone and you get the minus, not a `2`.

The tray icon is the MynaUI `one` / `two` glyph, coloured for your light/dark taskbar
theme, and the tooltip names the two microphones Windows is actually on. Connected
microphones are polled on the same tick, so the menu and the cross stay current. The icon
also re-registers itself if Explorer restarts.

## Config

Stored at `%APPDATA%\audio-autoswitch\config.json`, written on every switch and edit:

```json
{
  "presets": [
    {
      "default": { "id": "{0.0.1.00000000}.{...}", "name": "Microphone (fifine Microphone)" },
      "comm":    { "id": "{0.0.1.00000000}.{...}", "name": "Microphone (fifine Microphone)" }
    },
    {
      "default": { "id": "{0.0.1.00000000}.{...}", "name": "Headset Microphone (...)" },
      "comm":    { "id": "{0.0.1.00000000}.{...}", "name": "Headset Microphone (...)" }
    }
  ],
  "current": 0
}
```

`current` is the preset this app applied last. It no longer decides what the icon shows —
that is read from Windows — but it is what a left click falls back to when neither preset
is live. Device names are refreshed automatically if Windows renames an endpoint.

## Start with Windows

```powershell
$exe = Resolve-Path .\dist\audio-autoswitch.exe
$lnk = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\audio-autoswitch.lnk"
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $exe; $s.Save()
```

## How it works

| File | |
|---|---|
| `audio.py` | Endpoint enumeration and default-device changes |
| `config.py` | The two presets, saved in `%APPDATA%` |
| `switching.py` | Which preset is live, whether one can be applied, and applying it |
| `icons.py` | An SVG path renderer, for the tray glyphs and the `.ico` |
| `tray.py` | The tray icon and its menu |

Device enumeration uses the WASAPI `IMMDeviceEnumerator` COM interface via
[pycaw](https://github.com/AndreMiras/pycaw). Setting the default endpoint uses the
undocumented-but-stable `IPolicyConfig` interface — the same thing Windows' own sound
control panel calls. No admin rights needed.

Icons are rasterised at runtime from SVG path data by `icons.py`: the tray uses the stroked
`one` and `two` glyphs from [MynaUI Icons](https://mynaui.com/icons) (MIT), `round-minus`
for neither-preset and `close-rounded` for the blocked state, and the executable uses
`mic-rounded` on an accent badge — the last three from
[Material Symbols / Icons](https://fonts.google.com/icons) (Apache 2.0).

One pystray detail worth knowing if you edit `tray.py`: it decides how to call a menu
callback from `__code__.co_argcount`, which counts defaulted parameters. A
`lambda dev=device: ...` therefore reads as one-argument and gets handed the `Icon` as
`dev`. Menu callbacks are built by closure factories (`_on_assign` and friends) for that
reason — do not inline them as default-argument lambdas.
