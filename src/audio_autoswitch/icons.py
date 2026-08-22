"""Icon rendering, straight from SVG path data.

The tray shows MynaUI's stroked `one` / `two` glyphs for the live preset, Material
Icons' `round-remove` when Windows is on neither preset, or Material Symbols'
`close-rounded` in red when a switch is blocked; the executable gets Material Symbols'
`mic-rounded` on an accent badge.
"""

from __future__ import annotations

import re
import winreg

from PIL import Image, ImageDraw

# MynaUI Icons (MIT) -- https://mynaui.com/icons
MYNAUI_ONE = "M12.438 17V7L9 9.5"
MYNAUI_TWO = (
    "M8.75 9.92c0-3.894 5.77-3.894 5.77 0c0 2.94-3.77 5.476-5.77 7.08"
    "c0 0 3.75-.625 6.25 0"
)
GLYPHS = (MYNAUI_ONE, MYNAUI_TWO)

# Material Symbols (Apache 2.0) -- material-symbols:mic-rounded
MATERIAL_MIC = (
    "M9.875 13.125Q9 12.25 9 11V5q0-1.25.875-2.125T12 2t2.125.875T15 5v6"
    "q0 1.25-.875 2.125T12 14t-2.125-.875M11 20v-2.075q-2.3-.325-3.937-1.95"
    "t-1.988-3.95q-.05-.425.225-.725T6 11t.713.288T7.1 12q.35 1.75 1.738 2.875"
    "T12 16q1.8 0 3.175-1.137T16.9 12q.1-.425.388-.712T18 11t.7.3t.225.725"
    "q-.35 2.275-1.975 3.925T13 17.925V20q0 .425-.288.713T12 21t-.712-.288T11 20"
)

# Material Symbols (Apache 2.0) -- material-symbols:close-rounded
MATERIAL_CLOSE = (
    "m12 13.4l-4.9 4.9q-.275.275-.7.275t-.7-.275t-.275-.7t.275-.7l4.9-4.9l-4.9-4.9"
    "q-.275-.275-.275-.7t.275-.7t.7-.275t.7.275l4.9 4.9l4.9-4.9q.275-.275.7-.275"
    "t.7.275t.275.7t-.275.7L13.4 12l4.9 4.9q.275.275.275.7t-.275.7t-.7.275t-.7-.275z"
)
BLOCKED_COLOR = (232, 62, 62, 255)

# Material Icons (Apache 2.0) -- ic:round-minus, i.e. ic:round-remove
MATERIAL_MINUS = "M18 13H6c-.55 0-1-.45-1-1s.45-1 1-1h12c.55 0 1 .45 1 1s-.45 1-1 1z"

VIEWBOX = 24.0
STROKE_WIDTH = 1.5
# The tray glyphs sit small inside their 24x24 box; a uniform zoom (same factor for
# both, so stroke weight matches) makes them legible at 16px tray size.
ZOOM = 1.9
# The cross covers about half its 24x24 box; match the digits' visual weight.
_CLOSE_ZOOM = 1.45
# The minus bar is 2 units thick; zoomed it lands on the digits' 1.5 x ZOOM stroke.
_MINUS_ZOOM = 1.4
_SUPERSAMPLE = 8
_BEZIER_STEPS = 18

_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtZz]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")


def _flatten_path(d: str) -> list[list[tuple[float, float]]]:
    """Turn an SVG path into polylines, one per subpath."""
    tokens = _TOKEN.findall(d)
    subpaths: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    x = y = start_x = start_y = 0.0
    # Last control point, for the smooth variants: S mirrors a cubic's, T a quadratic's.
    prev_cubic: tuple[float, float] | None = None
    prev_quad: tuple[float, float] | None = None
    cmd = ""
    i = 0

    def number() -> float:
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    def reflect(control) -> tuple[float, float]:
        return (2 * x - control[0], 2 * y - control[1]) if control else (x, y)

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                if current:
                    current.append((start_x, start_y))
                    subpaths.append(current)
                    current = []
                x, y = start_x, start_y
                prev_cubic = prev_quad = None
                continue
        rel = cmd.islower()
        head = cmd.upper()

        if head == "M":
            if current:
                subpaths.append(current)
            dx, dy = number(), number()
            x, y = (x + dx, y + dy) if rel else (dx, dy)
            start_x, start_y = x, y
            current = [(x, y)]
            cmd = "l" if rel else "L"  # implicit lineto for extra coordinate pairs
            prev_cubic = prev_quad = None
        elif head in ("L", "H", "V"):
            if head == "L":
                dx, dy = number(), number()
                x, y = (x + dx, y + dy) if rel else (dx, dy)
            elif head == "H":
                dx = number()
                x = x + dx if rel else dx
            else:
                dy = number()
                y = y + dy if rel else dy
            current.append((x, y))
            prev_cubic = prev_quad = None
        elif head in ("C", "S"):
            if head == "C":
                c1 = (number(), number())
                if rel:
                    c1 = (x + c1[0], y + c1[1])
            else:
                c1 = reflect(prev_cubic)
            c2 = (number(), number())
            end = (number(), number())
            if rel:
                c2 = (x + c2[0], y + c2[1])
                end = (x + end[0], y + end[1])
            for step in range(1, _BEZIER_STEPS + 1):
                t = step / _BEZIER_STEPS
                u = 1 - t
                current.append(
                    (
                        u**3 * x
                        + 3 * u * u * t * c1[0]
                        + 3 * u * t * t * c2[0]
                        + t**3 * end[0],
                        u**3 * y
                        + 3 * u * u * t * c1[1]
                        + 3 * u * t * t * c2[1]
                        + t**3 * end[1],
                    )
                )
            prev_cubic, prev_quad = c2, None
            x, y = end
        elif head in ("Q", "T"):
            if head == "Q":
                control = (number(), number())
                if rel:
                    control = (x + control[0], y + control[1])
            else:
                control = reflect(prev_quad)
            end = (number(), number())
            if rel:
                end = (x + end[0], y + end[1])
            for step in range(1, _BEZIER_STEPS + 1):
                t = step / _BEZIER_STEPS
                u = 1 - t
                current.append(
                    (
                        u * u * x + 2 * u * t * control[0] + t * t * end[0],
                        u * u * y + 2 * u * t * control[1] + t * t * end[1],
                    )
                )
            prev_quad, prev_cubic = control, None
            x, y = end
        else:
            raise ValueError(f"unsupported path command: {cmd!r}")

    if current:
        subpaths.append(current)
    return subpaths


def _place(subpaths, hi: float, scale: float):
    """Scale to the canvas and centre the glyph's own bounding box in it."""
    flat = [p for sub in subpaths for p in sub]
    cx = (min(p[0] for p in flat) + max(p[0] for p in flat)) / 2
    cy = (min(p[1] for p in flat) + max(p[1] for p in flat)) / 2
    off_x, off_y = hi / 2 - cx * scale, hi / 2 - cy * scale
    return [
        [(px * scale + off_x, py * scale + off_y) for px, py in sub] for sub in subpaths
    ]


def render_glyph(
    path_data: str, size: int, color: tuple[int, int, int, int]
) -> Image.Image:
    """Render a stroked path, with round caps and joins."""
    hi = size * _SUPERSAMPLE
    scale = hi / VIEWBOX * ZOOM
    img = Image.new("RGBA", (hi, hi), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    width = max(1, round(STROKE_WIDTH * scale))
    radius = width / 2

    for points in _place(_flatten_path(path_data), hi, scale):
        if len(points) > 1:
            draw.line(points, fill=color, width=width, joint="curve")
        for px, py in (points[0], points[-1]):  # round caps
            draw.ellipse(
                (px - radius, py - radius, px + radius, py + radius), fill=color
            )

    return img.resize((size, size), Image.LANCZOS)


def render_filled_glyph(
    path_data: str, size: int, color: tuple[int, int, int, int], zoom: float = 1.0
) -> Image.Image:
    """Render a filled path; each subpath is its own solid region."""
    hi = size * _SUPERSAMPLE
    scale = hi / VIEWBOX * zoom
    img = Image.new("RGBA", (hi, hi), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for points in _place(_flatten_path(path_data), hi, scale):
        if len(points) > 2:
            draw.polygon(points, fill=color)

    return img.resize((size, size), Image.LANCZOS)


def taskbar_is_light() -> bool:
    """Light taskbar wants a dark icon, and vice versa."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        with key:
            return bool(winreg.QueryValueEx(key, "SystemUsesLightTheme")[0])
    except OSError:
        return False


def tray_icon(preset: int, size: int = 64) -> Image.Image:
    """The live preset's number, in whichever shade the taskbar theme needs."""
    shade = 32 if taskbar_is_light() else 255
    return render_glyph(GLYPHS[preset], size, (shade, shade, shade, 255))


def unset_icon(size: int = 64) -> Image.Image:
    """Shown when Windows is on neither preset: a minus, in the taskbar's shade."""
    shade = 32 if taskbar_is_light() else 255
    return render_filled_glyph(
        MATERIAL_MINUS, size, (shade, shade, shade, 255), zoom=_MINUS_ZOOM
    )


def blocked_icon(size: int = 64) -> Image.Image:
    """Shown when a switch cannot happen: a red cross, readable on either theme."""
    return render_filled_glyph(MATERIAL_CLOSE, size, BLOCKED_COLOR, zoom=_CLOSE_ZOOM)


# ---------------------------------------------------------------- app icon

BADGE_FILL = (37, 99, 235, 255)
_ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def app_icon(size: int) -> Image.Image:
    """Executable icon: a microphone on a rounded accent badge."""
    ss = 4
    hi = size * ss
    img = Image.new("RGBA", (hi, hi), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        (0, 0, hi - 1, hi - 1), radius=int(hi * 0.22), fill=BADGE_FILL
    )
    img.alpha_composite(
        render_filled_glyph(MATERIAL_MIC, hi, (255, 255, 255, 255), 0.2)
    )
    return img.resize((size, size), Image.LANCZOS)


def write_ico(path) -> None:
    """Multi-resolution .ico, each size rendered natively rather than downsampled."""
    frames = [app_icon(s) for s in _ICO_SIZES]
    frames[-1].save(
        path,
        format="ICO",
        sizes=[(s, s) for s in _ICO_SIZES],
        append_images=frames[:-1],
    )
