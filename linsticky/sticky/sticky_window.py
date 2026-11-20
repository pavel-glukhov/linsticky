"""
The main window for an individual sticky note.

This module defines the `StickyWindow` class, which is the core component for
displaying and interacting with a single note. It integrates multiple mixins
for handling UI, events, actions, and text formatting to keep the code modular.
"""
from gi.repository import Gtk, GLib, Adw

import theme

from .sticky_formatting import StickyFormatting
from .sticky_actions import StickyActions
from .sticky_ui import StickyUI
from .sticky_events import StickyEvents
from .sticky_markdown import StickyMarkdown


class StickyWindow(Adw.Window, StickyFormatting, StickyActions, StickyUI, StickyEvents, StickyMarkdown):
    """
    Represents a single sticky note window.

    This class inherits from `Adw.Window` to ensure proper integration with the
    GNOME desktop environment and its theming, which is crucial for a consistent
    look and feel in both DEB and Snap packages. It combines functionality from
    various mixins to manage its behavior.
    """
    def __init__(self, db, note_id=None, main_window=None):
        """
        Initializes the sticky note window.

        Args:
            db: The database controller instance.
            note_id: The ID of the note to display.
            main_window: A reference to the main application window.
        """
        super().__init__()

        # --- Core State Initialization ---
        self.db = db
        self.note_id = note_id
        self.main_window = main_window
        self.config = getattr(main_window, 'config', {})
        self._loading = True
        self._is_destroying = False
        # Set whenever content, color or geometry changes; the periodic save
        # only touches the database when this flag is raised.
        self._dirty = False
        self._preview_timer_id = None
        self.btn_font_size = None
        self.is_markdown = False
        self.scale = 1.0
        self.current_color = "#FFF59D"
        self.default_font_size = 12
        
        # --- Load Geometry ---
        if self.note_id:
            note_data = self.db.get(self.note_id)
            if note_data:
                self.saved_x = note_data['x'] if note_data['x'] is not None else 300
                self.saved_y = note_data['y'] if note_data['y'] is not None else 300
                self.saved_width = note_data['w'] if note_data['w'] is not None else 300
                self.saved_height = note_data['h'] if note_data['h'] is not None else 380
            else:
                self.saved_x, self.saved_y, self.saved_width, self.saved_height = 300, 300, 300, 380
        else:
            self.saved_x, self.saved_y, self.saved_width, self.saved_height = 300, 300, 300, 380

        # --- UI Construction ---
        self.set_default_size(self.saved_width, self.saved_height)
        self.overlay = Gtk.Overlay()
        self.set_content(self.overlay)
        
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.main_box.add_css_class("sticky-main-area")
        self.overlay.set_child(self.main_box)

        # --- Style and Final UI Setup ---
        self.apply_styles()
        self.setup_header()
        self.setup_text_area() # This now also sets up the key controller
        self.setup_markdown_preview()
        self.setup_tags()
        self.setup_formatting_bar()
        self.setup_resize_handle()

        # --- Data Loading and Signal Connection ---
        self.load_from_db()
        self._loading = False
        self._connect_main_signals()
        if self.is_markdown:
            # Markdown notes open in the rendered preview when they have content.
            self.md_preview_active = bool(self._get_buffer_text().strip())
            self.sync_markdown_ui()

        # --- Event and Persistence Controllers ---
        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("leave", lambda *_: self.save())
        self.add_controller(focus_ctrl)
        
        self.save_timer_id = GLib.timeout_add_seconds(2, self.save)

    def apply_styles(self):
        """
        Registers the shared stylesheet (once per process) and paints the note.
        See `theme.py` for why providers are no longer created per window.
        """
        theme.ensure_static_css()
        self.add_css_class("sticky-window")
        self._update_ui_design()

    def _connect_main_signals(self):
        """Connects core signals for the window and its text buffer."""
        self.connect("close-request", self._on_close_requested)
        self.connect("map", self._on_map)
        self.connect("notify::default-width", self._on_configure_event)
        self.connect("notify::default-height", self._on_configure_event)
        self.buffer.connect("notify::cursor-position", self.on_cursor_moved)

    def _on_configure_event(self, *args):
        """Updates the internal state with the new window dimensions for saving."""
        width, height = self.get_default_size()
        if (width, height) != (self.saved_width, self.saved_height):
            self.saved_width, self.saved_height = width, height
            self._dirty = True

    def _update_ui_design(self, hex_color=None):
        """
        Updates the background color of the note by swapping its color class.
        """
        if hex_color:
            self.current_color = hex_color.strip()
        theme.apply_note_color(self.main_box, self.current_color or theme.DEFAULT_NOTE_COLOR)

    def setup_formatting_bar(self):
        """Constructs or reconstructs the bottom text formatting toolbar."""
        if hasattr(self, 'format_bar') and self.format_bar.get_parent():
            self.main_box.remove(self.format_bar)

        self.btn_font_size = None
        self.format_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.format_bar.add_css_class("compact-format-bar")
        self.main_box.append(self.format_bar)

        scale = self.scale
        icon_size = int(18 * scale)
        fmt_config = self.config.get("formatting", {})
        if not isinstance(fmt_config, dict): fmt_config = {}

        buttons_config = [
            ("bold", "<b>B</b>", self.apply_format, "bold"),
            ("italic", "<i>I</i>", self.apply_format, "italic"),
            ("underline", "<u>U</u>", self.apply_format, "underline"),
            ("strikethrough", "<s>S</s>", self.apply_format, "strikethrough"),
            ("list", "≡", self.toggle_bullet_list, None)
        ]
        if self.is_markdown:
            # Markdown has no underline, text colors or font sizes.
            buttons_config = [b for b in buttons_config if b[0] != "underline"]

        has_any_btn = False
        for key, label, callback, arg in buttons_config:
            if fmt_config.get(key, True):
                btn = Gtk.Button(has_frame=False)
                btn.set_child(Gtk.Label(label=label, use_markup=True))
                btn.add_css_class("format-btn-tiny")
                btn.set_size_request(icon_size, icon_size)
                if arg:
                    btn.connect("clicked", (lambda cb, a: lambda _: cb(a))(callback, arg))
                else:
                    btn.connect("clicked", (lambda cb: lambda _: cb())(callback))
                self.format_bar.append(btn)
                has_any_btn = True

        show_color = fmt_config.get("text_color", True) and not self.is_markdown
        show_font = fmt_config.get("font_size", True) and not self.is_markdown

        if has_any_btn and (show_color or show_font):
            sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin_start=int(3*scale), margin_end=int(3*scale))
            self.format_bar.append(sep)

        if show_color:
            btn_text_color = Gtk.MenuButton(has_frame=False)
            btn_text_color.set_child(Gtk.Label(label='<span foreground="#444">A</span>', use_markup=True))
            btn_text_color.add_css_class("format-btn-tiny")
            btn_text_color.set_size_request(icon_size, icon_size)
            self.setup_text_color_popover(btn_text_color)
            self.format_bar.append(btn_text_color)

        if show_font:
            self.btn_font_size = Gtk.MenuButton(label=str(self.default_font_size), has_frame=False)
            self.btn_font_size.add_css_class("format-btn-tiny")
            self.btn_font_size.set_size_request(int(icon_size * 1.5), icon_size)
            self.setup_font_size_popover(self.btn_font_size)
            self.format_bar.append(self.btn_font_size)

    def on_cursor_moved(self, buffer, pspec):
        """Updates the font size indicator in the UI based on the cursor's position."""
        if self.btn_font_size is None:
            return
        cursor_iter = buffer.get_iter_at_mark(buffer.get_insert())
        tags = cursor_iter.get_tags()
        current_size = self.default_font_size
        for tag in tags:
            name = tag.get_property("name")
            if name and name.startswith("font_size_"):
                try:
                    current_size = int(name.replace("font_size_", ""))
                except ValueError:
                    pass
        self.btn_font_size.set_label(str(current_size))

    def reload_config(self, new_config: dict):
        """
        Reloads the window's configuration and rebuilds UI components accordingly.

        Args:
            new_config: The new configuration dictionary.
        """
        self.config = new_config
        if hasattr(self, 'header_box'):
            self.main_box.remove(self.header_box)
        self.setup_header()
        self.main_box.reorder_child_after(self.header_box, None)
        self.sync_markdown_ui()
