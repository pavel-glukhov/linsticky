import builtins
from gi.repository import Gtk, Adw, Gio, GLib
from views.main_view.note_card import NoteCard
from sticky.sticky_window import StickyWindow
from views.settings_view import SettingsView
from views.trash_view import TrashView
import theme

_ = builtins._

class MainWindow(Adw.ApplicationWindow):
    """
    The main application window, displaying a list of sticky notes and providing access to settings and trash.
    """
    def __init__(self, db, application, **kwargs):
        """
        Initializes the MainWindow.
        Args:
            db: The database controller instance.
            application (Adw.Application): The main application instance.
            **kwargs: Additional keyword arguments for Gtk.ApplicationWindow.
        """
        super().__init__(application=application,
                         title=_("LinSticky"),
                         default_width=200,
                         default_height=600, **kwargs)
        self.set_size_request(100, -1)
        self.app = application
        self.db = db
        self.config = application.config
        self.stickies = {}
        # note_id -> NoteCard, so single cards can be updated without scanning
        # or rebuilding the whole list.
        self.cards = {}
        self._search_query = ""
        # Set while the application shuts down, so notes closed by the quit
        # keep their "open" flag and are restored on the next start.
        self.is_quitting = False

        # flowbox/flowboxchild rules live in the shared stylesheet.
        theme.ensure_static_css()

        self.setup_actions()

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(300)
        self.set_content(self.stack)

        self.main_page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header_bar = Adw.HeaderBar()
        header_bar.set_show_end_title_buttons(True)

        btn_new = Gtk.Button(icon_name="list-add-symbolic")
        btn_new.add_css_class("flat")
        btn_new.connect("clicked", lambda _: self.create_note())
        header_bar.pack_start(btn_new)

        btn_trash = Gtk.Button(icon_name="user-trash-symbolic")
        btn_trash.add_css_class("flat")
        btn_trash.connect("clicked", self.on_show_trash)
        header_bar.pack_end(btn_trash)

        btn_settings = Gtk.Button(icon_name="emblem-system-symbolic")
        btn_settings.add_css_class("flat")
        btn_settings.connect("clicked", self.on_show_settings)
        header_bar.pack_end(btn_settings)

        self.main_page_box.append(header_bar)

        self.search_entry = Gtk.SearchEntry(placeholder_text=_("Search..."))
        self.search_entry.set_margin_start(10)
        self.search_entry.set_margin_end(10)
        self.search_entry.set_margin_top(10)
        self.search_entry.set_margin_bottom(10)
        self.search_entry.connect("search-changed", self.on_search)
        self.main_page_box.append(self.search_entry)

        self.flowbox = Gtk.FlowBox(
            valign=Gtk.Align.START,
            selection_mode=Gtk.SelectionMode.NONE
        )
        self.flowbox.set_homogeneous(False)
        self.flowbox.set_max_children_per_line(1)
        self.flowbox.set_min_children_per_line(1)
        self.flowbox.set_halign(Gtk.Align.FILL)
        self.flowbox.set_column_spacing(0)
        self.flowbox.set_row_spacing(10)
        self.flowbox.set_margin_top(5)
        self.flowbox.set_margin_bottom(10)
        self.flowbox.set_margin_start(10)
        self.flowbox.set_margin_end(10)
        # Same order as the SQL query: pinned first, then newest first.
        self.flowbox.set_sort_func(self._sort_cards)
        self.flowbox.set_filter_func(self._filter_card)

        scrolled = Gtk.ScrolledWindow(child=self.flowbox, vexpand=True)
        scrolled.set_has_frame(False)
        self.main_page_box.append(scrolled)

        self.stack.add_named(self.main_page_box, "main")

        self.trash_view = TrashView(self.db, on_back_callback=self.go_back_to_main)
        self.stack.add_named(self.trash_view, "trash")

        self.settings_view = SettingsView(
            on_back_callback=self.go_back_to_main,
            on_settings_change_callback=self.on_settings_changed
        )
        self.stack.add_named(self.settings_view, "settings")

        self.stack.set_visible_child_name("main")
        self.refresh_list()

    def on_settings_changed(self):
        """
        Callback for when settings are changed in the SettingsView.
        Reloads the configuration and updates all open sticky note windows.
        """
        self.reload_configuration()

    def reload_configuration(self):
        """
        Reloads the configuration from disk and propagates changes to all open sticky notes.
        """
        from config.config_manager import ConfigManager
        self.config = ConfigManager.load()

        for note_id, sticky_window in self.stickies.items():
            if hasattr(sticky_window, 'reload_config'):
                sticky_window.reload_config(self.config)

    def on_show_settings(self, btn: Gtk.Button):
        """
        Callback for the settings button. Switches to the settings view.
        Args:
            btn (Gtk.Button): The clicked button.
        """
        self.settings_view.refresh_ui_from_config()
        self.stack.set_visible_child_name("settings")

    def on_show_trash(self, btn: Gtk.Button):
        """
        Callback for the trash button. Switches to the trash view and refreshes its list.
        Args:
            btn (Gtk.Button): The clicked button.
        """
        self.trash_view.refresh_list()
        self.stack.set_visible_child_name("trash")

    def go_back_to_main(self):
        """Switches back to the main notes list view."""
        # Only the trash view can change the set of visible notes (restore).
        if self.stack.get_visible_child_name() == "trash":
            self.refresh_list()
        self.stack.set_visible_child_name("main")

    def refresh_list(self):
        """Rebuilds the whole list of notes from the database."""
        while child := self.flowbox.get_first_child():
            self.flowbox.remove(child)
        self.cards.clear()

        for note in self.db.all_notes(full=True):
            self._add_card(note)

    def _add_card(self, note):
        """Creates a NoteCard for a database row and inserts it into the list."""
        card = NoteCard(note, self.db, refresh_callback=self.flowbox.invalidate_sort)
        self.flowbox.append(card)
        self.cards[card.note_id] = card

        flow_child = card.get_parent()
        if flow_child:
            flow_child.set_margin_top(0)
            flow_child.set_margin_bottom(0)
            flow_child.set_margin_start(0)
            flow_child.set_margin_end(0)
            flow_child.set_can_focus(False)
            flow_child.set_hexpand(True)
            flow_child.set_halign(Gtk.Align.FILL)
        return card

    def _remove_card(self, note_id: int):
        """Removes a single card from the list, if present."""
        card = self.cards.pop(note_id, None)
        if card and card.get_parent():
            self.flowbox.remove(card.get_parent())

    @staticmethod
    def _sort_cards(child_a, child_b) -> int:
        """Pinned notes first, then newer notes (higher id) first."""
        a, b = child_a.get_child(), child_b.get_child()
        if a.is_pinned != b.is_pinned:
            return -1 if a.is_pinned else 1
        return (b.note_id > a.note_id) - (b.note_id < a.note_id)

    def _filter_card(self, child) -> bool:
        if not self._search_query:
            return True
        return self._search_query in child.get_child().get_search_text()

    def create_note(self):
        """Creates a new sticky note and opens it."""
        palette = self.config.get("palette", [])
        default_color = palette[0] if palette else "#FFF59D"
        # Markdown applies only to notes created while it is enabled; existing
        # (rich text) notes are never converted.
        md_config = self.config.get("markdown")
        use_markdown = isinstance(md_config, dict) and bool(md_config.get("enabled", False))
        note_id = self.db.add(color=default_color, is_markdown=use_markdown)
        note = self.db.get(note_id)
        if note:
            self._add_card(note)
        self.open_note(note_id)

    def open_note(self, note_id: int):
        """
        Opens an existing sticky note or brings it to the foreground if already open.
        Args:
            note_id (int): The ID of the note to open.
        """
        if note_id in self.stickies:
            existing_win = self.stickies[note_id]
            if existing_win.get_native():
                existing_win.present()
                return
            else:
                del self.stickies[note_id]

        new_sticky = StickyWindow(self.db, note_id, self)
        self.stickies[note_id] = new_sticky
        self.db.set_open_state(note_id, 1)
        new_sticky.present()

    def on_sticky_closed(self, note_id: int):
        """
        Callback called by a StickyWindow when it is about to close.
        Removes the reference to the closed window from the tracking dictionary.
        Args:
            note_id (int): The ID of the sticky note that closed.
        """
        if note_id in self.stickies:
            del self.stickies[note_id]
        if not self.is_quitting:
            self.db.set_open_state(note_id, 0)

    def on_search(self, entry: Gtk.SearchEntry):
        """
        Callback for the search entry. Filters the displayed notes based on the query.
        Args:
            entry (Gtk.SearchEntry): The search entry widget.
        """
        self._search_query = entry.get_text().lower()
        self.flowbox.invalidate_filter()

    def update_card_text(self, note_id: int, serialized_content: list[dict]):
        """
        Updates the text content of a specific note card in the main list.
        Args:
            note_id (int): The ID of the note card to update.
            serialized_content (list[dict]): The new serialized content for the note.
        """
        card = self.cards.get(note_id)
        if card:
            card.set_segments(serialized_content)
            if self._search_query:
                self.flowbox.invalidate_filter()

    def update_card_color_live(self, note_id: int, color: str):
        """
        Updates the color of a specific note card in the main list.
        Args:
            note_id (int): The ID of the note card to update.
            color (str): The new color for the card.
        """
        card = self.cards.get(note_id)
        if card:
            card.update_color(color)

    def on_action_delete_manual(self, note_id: int):
        """
        Moves a note to trash and refreshes the list.
        Args:
            note_id (int): The ID of the note to delete.
        """
        self.db.move_to_trash(note_id)
        if note_id in self.stickies: self.stickies[note_id].close()
        self._remove_card(note_id)

    def setup_actions(self):
        """Sets up application-wide actions."""
        action_delete = Gio.SimpleAction.new("delete_note", GLib.VariantType.new("i"))
        action_delete.connect("activate", lambda a, v: self.on_action_delete_manual(v.get_int32()))
        self.add_action(action_delete)

    def create_combined_context_menu(self, note_id: int, target_widget: Gtk.Widget):
        """
        Creates and displays a context menu for a note card.
        Args:
            note_id (int): The ID of the note.
            target_widget (Gtk.Widget): The widget to attach the popover to.
        """
        popover = Gtk.Popover()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        vbox.set_margin_top(8)
        vbox.set_margin_bottom(8)
        vbox.set_margin_start(8)
        vbox.set_margin_end(8)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, halign=Gtk.Align.CENTER)
        
        palette = self.config.get("palette", [])
        
        for i, color in enumerate(palette):
            b = Gtk.Button()
            b.set_size_request(28, 28)
            theme.apply_swatch(b, color, "menu")
            b.connect("clicked", lambda _, c=color: self.update_note_color(note_id, c, target_widget, popover))
            grid.attach(b, i % 4, i // 4, 1, 1)

        vbox.append(grid)
        vbox.append(Gtk.Separator())

        btn_del = Gtk.Button(label=_("Move to Trash"), has_frame=False)
        btn_del.connect("clicked", lambda _: (self.on_action_delete_manual(note_id), popover.popdown()))
        vbox.append(btn_del)

        popover.set_child(vbox)
        popover.set_parent(target_widget)
        popover.popup()

    def update_note_color(self, note_id: int, color: str, widget: Gtk.Widget, popover: Gtk.Popover):
        """
        Updates the color of a note and refreshes its card in the main list.
        Args:
            note_id (int): The ID of the note to update.
            color (str): The new color.
            widget (Gtk.Widget): The widget that triggered the color change (e.g., a color button).
            popover (Gtk.Popover): The popover containing the color selection.
        """
        self.db.update_color(note_id, color)
        self.update_card_color_live(note_id, color)
        if note_id in self.stickies: self.stickies[note_id].apply_color(color)
        popover.popdown()
