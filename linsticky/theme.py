"""
Shared CSS management.

Before this module existed, every color change, every new sticky window and
every note card registered a brand new ``Gtk.CssProvider`` that was never
removed. The number of providers grew for the whole lifetime of the process,
and GTK had to walk all of them on every style recalculation.

This module keeps exactly two display-wide providers:

* a static provider with rules that never change (registered once);
* a dynamic provider with one CSS class per color in use. It is reloaded only
  when a color that has not been seen before appears.

Widgets switch colors by swapping CSS classes instead of attaching providers.
"""
import re

from gi.repository import Gtk, Gdk

DEFAULT_NOTE_COLOR = "#FFF59D"
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

# Rules that previously were re-registered for every window / card.
# Kept at APPLICATION priority, exactly as before.
_STATIC_CSS = """
window.background.sticky-window { background-color: transparent; }

.sticky-window textview { color: #000000; caret-color: #000000; }
.sticky-window textview text { color: #000000; }
.sticky-window .compact-header button,
.sticky-window .compact-format-bar button { color: rgba(0, 0, 0, 0.8); }

flowbox { padding: 0px; background: transparent; }
flowboxchild { padding: 0px; margin: 0px; border: none; min-width: 0px; outline: none; }

label.note-card-label { color: #000000; }
"""

# Swatch shapes. These were per-widget providers at USER priority, so they
# live in the USER-priority dynamic provider to keep the same precedence.
_SWATCH_SHAPES_CSS = """
button.swatch-round { border-radius: 50%; border: 1px solid rgba(0,0,0,0.2); }
button.swatch-square { border-radius: 3px; }
button.swatch-menu { border-radius: 14px; min-width: 28px; min-height: 28px; padding: 0; }
"""

_static_provider = None
_dynamic_provider = None
_known_colors = []


def normalize_color(hex_color, fallback=DEFAULT_NOTE_COLOR) -> str:
    """Returns an upper-case ``#RRGGBB`` style string, or ``fallback`` if invalid."""
    if isinstance(hex_color, str):
        value = hex_color.strip()
        if _HEX_RE.match(value):
            return value.upper()
    return fallback


def _token(color: str) -> str:
    return color.lstrip("#")


def _display():
    return Gdk.Display.get_default()


def ensure_static_css():
    """Registers the static stylesheet once per process."""
    global _static_provider
    if _static_provider is not None or _display() is None:
        return
    _static_provider = Gtk.CssProvider()
    _static_provider.load_from_string(_STATIC_CSS)
    Gtk.StyleContext.add_provider_for_display(
        _display(), _static_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def _reload_dynamic():
    global _dynamic_provider
    if _display() is None:
        return
    if _dynamic_provider is None:
        _dynamic_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            _display(), _dynamic_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )
    parts = [_SWATCH_SHAPES_CSS]
    for color in _known_colors:
        t = _token(color)
        parts.append(
            f".sticky-main-area.note-color-{t} {{ background-color: {color}; border-radius: 12px; }}\n"
            f".sticky-paper-card.note-color-{t} {{ background-color: {color}; border-radius: 0px; min-height: 50px; }}\n"
            f"button.swatch-{t} {{ background-color: {color}; }}\n"
        )
    _dynamic_provider.load_from_string("".join(parts))


def _register_color(color: str):
    if color not in _known_colors:
        _known_colors.append(color)
        _reload_dynamic()
    elif _dynamic_provider is None:
        _reload_dynamic()


def _swap_class(widget: Gtk.Widget, prefix: str, new_class: str):
    for css_class in widget.get_css_classes():
        if css_class.startswith(prefix) and css_class != new_class:
            widget.remove_css_class(css_class)
    widget.add_css_class(new_class)


def apply_note_color(widget: Gtk.Widget, hex_color) -> str:
    """
    Paints a sticky main area or a note card with ``hex_color``.
    Returns the normalized color that was applied.
    """
    color = normalize_color(hex_color)
    _register_color(color)
    _swap_class(widget, "note-color-", f"note-color-{_token(color)}")
    return color


def apply_swatch(button: Gtk.Button, hex_color, shape: str = "round"):
    """
    Styles a color swatch button.

    Args:
        button: The button to style.
        hex_color: Fill color.
        shape: "round" (palette circles), "square" (text colors) or "menu"
               (context menu circles).
    """
    color = normalize_color(hex_color, fallback="#FFFFFF")
    _register_color(color)
    for css_class in button.get_css_classes():
        if css_class.startswith("swatch-") and css_class not in (
            f"swatch-{shape}", f"swatch-{_token(color)}"
        ):
            button.remove_css_class(css_class)
    button.add_css_class(f"swatch-{shape}")
    button.add_css_class(f"swatch-{_token(color)}")
