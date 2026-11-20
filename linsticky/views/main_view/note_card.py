from gi.repository import Gtk, Pango
import builtins

import theme
from content import codec, render
from content import markdown as md

_ = builtins._

class NoteCard(Gtk.Box):
    """
    A custom Gtk.Box widget representing a single sticky note card in the main window.
    Displays a preview of the note's content, color, and pin status.
    """
    def __init__(self, note: dict, db, menu_callback=None, refresh_callback=None):
        """
        Initializes a NoteCard.
        Args:
            note (dict): A dictionary containing note data (id, content, color, is_pinned).
            db: The database controller instance.
            menu_callback (callable, optional): Callback for right-click menu. Defaults to None.
            refresh_callback (callable, optional): Callback to refresh the main note list. Defaults to None.
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.note_id = note["id"]
        self.db = db
        self.is_pinned = note['is_pinned'] == 1 if 'is_pinned' in note.keys() else False
        self.is_markdown = bool(note['is_markdown']) if 'is_markdown' in note.keys() else False
        self.menu_callback = menu_callback
        self.refresh_callback = refresh_callback

        self.set_hexpand(True)
        self.set_vexpand(False)

        self.card_canvas = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.card_canvas.add_css_class("sticky-paper-card")
        self.card_canvas.set_size_request(-1, 50)
        self.card_canvas.set_overflow(Gtk.Overflow.HIDDEN)
        self.append(self.card_canvas)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.set_margin_top(4); header.set_margin_end(4)
        self.card_canvas.append(header)

        spacer = Gtk.Box(hexpand=True)
        header.append(spacer)

        # Custom Pin Box (Box + Image) to avoid theme interference
        self.pin_box = Gtk.Box()
        self.pin_box.add_css_class("force-black-pin")
        self.pin_box.set_valign(Gtk.Align.CENTER)
        self.pin_box.set_margin_end(6)
        self.pin_box.set_margin_top(6)
        
        self.pin_image = Gtk.Image()
        self.pin_box.append(self.pin_image)
        
        self._update_pin_icon()
        header.append(self.pin_box)
        
        segments = codec.decode(note["content"])

        self.label = Gtk.Label()
        # Black text color comes from the shared stylesheet (see theme.py).
        self.label.add_css_class("note-card-label")
        self.label.set_use_markup(True)
        self.set_segments(segments)

        self.label.set_wrap(True)
        self.label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.label.set_ellipsize(Pango.EllipsizeMode.END)
        self.label.set_lines(5)
        self.label.set_xalign(0); self.label.set_yalign(0)
        self.label.set_valign(Gtk.Align.START)
        self.label.set_margin_top(0); self.label.set_margin_bottom(12)
        self.label.set_margin_start(15); self.label.set_margin_end(15)
        self.card_canvas.append(self.label)

        self.update_color(note["color"])
        self.setup_gestures()

    def _update_pin_icon(self):
        """Updates the icon and tooltip of the pin button based on the note's pinned status."""
        if self.is_pinned:
            self.pin_image.set_from_icon_name("starred-symbolic")
            self.pin_box.set_tooltip_text(_("Unpin Note"))
            self.pin_box.add_css_class("pinned")
        else:
            self.pin_image.set_from_icon_name("non-starred-symbolic")
            self.pin_box.set_tooltip_text(_("Pin Note"))
            self.pin_box.remove_css_class("pinned")

    def on_pin_clicked(self, gesture, n_press, x, y):
        """
        Callback for when the pin button is clicked. Toggles the note's pinned status.
        Args:
            gesture: The Gtk.GestureClick instance.
            n_press: Number of presses.
            x: X-coordinate of the click.
            y: Y-coordinate of the click.
        """
        self.db.toggle_pin_status(self.note_id)
        self.is_pinned = not self.is_pinned
        self._update_pin_icon()
        if self.refresh_callback:
            self.refresh_callback()
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def get_search_text(self) -> str:
        """Lower-cased full note text used by the main window search filter."""
        return self._search_text

    def set_segments(self, segments: list[dict]):
        """Renders the given content segments into the preview label."""
        if self.is_markdown:
            source = codec.plain_text(segments)
            self._search_text = md.to_plain(source).lower()
            markup_text = md.to_pango(source, max_lines=5, links=False)
        else:
            self._search_text = codec.plain_text(segments).lower()
            markup_text = render.segments_to_pango(segments, max_lines=5)
        self.label.set_markup(f'<span foreground="#000000">{markup_text}</span>')

    def update_color(self, hex_color: str):
        """
        Updates the background color of the note card.
        Args:
            hex_color (str): The new hexadecimal color string.
        """
        theme.apply_note_color(self.card_canvas, hex_color)

    def setup_gestures(self):
        """Sets up gesture recognizers for click and right-click actions on the card."""
        click_open = Gtk.GestureClick()
        click_open.connect("released", lambda gesture, n, x, y: self.get_native().open_note(self.note_id))
        self.card_canvas.add_controller(click_open)

        click_pin = Gtk.GestureClick()
        click_pin.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click_pin.connect("released", self.on_pin_clicked)
        self.pin_box.add_controller(click_pin)

        menu = Gtk.GestureClick(button=3)
        menu.connect("released", self._on_right_click)
        self.add_controller(menu)

    def _on_right_click(self, gesture, n, x, y):
        """
        Callback for right-click gesture. Displays a context menu.
        Args:
            gesture: The Gtk.GestureClick instance.
            n: Number of presses.
            x: X-coordinate of the click.
            y: Y-coordinate of the click.
        """
        if self.menu_callback:
            self.menu_callback(self.note_id, self.card_canvas)
        else:
            self.get_native().create_combined_context_menu(self.note_id, self.card_canvas)
