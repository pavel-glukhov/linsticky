"""
"New note" type chooser shared by the main window and the sticker header.
"""
import builtins

from gi.repository import Gtk

if not hasattr(builtins, "_"):
    builtins._ = lambda s: s

NOTE_TYPE_TEXT = "text"
NOTE_TYPE_MARKDOWN = "markdown"


def build_new_note_popover(on_choose) -> Gtk.Popover:
    """
    Returns a popover with "Text Note" / "Markdown Note" items.

    Args:
        on_choose: Called with True for a Markdown note, False for a text note.
    """
    popover = Gtk.Popover()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    for markdown, label in ((False, builtins._("Text Note")), (True, builtins._("Markdown Note"))):
        button = Gtk.Button(label=label, has_frame=False)
        button.get_child().set_xalign(0)
        button.connect("clicked", (lambda md: lambda _b: (popover.popdown(), on_choose(md)))(markdown))
        box.append(button)
    popover.set_child(box)
    return popover
