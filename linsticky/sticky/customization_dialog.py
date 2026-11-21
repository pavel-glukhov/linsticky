import builtins
from gi.repository import Gtk, Adw
from config.config_manager import ConfigManager
from content.markdown_edit import MD_TOOLBAR

# Ensure fallback for translation
if not hasattr(builtins, "_"):
    builtins._ = lambda s: s

class CustomizationDialog(Gtk.Window):
    """
    A modal dialog allowing the user to toggle visibility of formatting buttons
    (for regular and Markdown notes) and to turn the Markdown mode on/off.
    """
    def __init__(self, parent_window):
        super().__init__()
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_title(builtins._("Customization"))
        self.set_default_size(320, 520)
        self.set_resizable(False)

        # Use Adw.Window styling if available via CSS classes,
        # but Gtk.Window is safer for simple modals inside the app structure.
        self.add_css_class("dialog")

        self.parent_window = parent_window
        self.config = ConfigManager.load()
        self.formatting_config = self.config.get("formatting", {}).copy()
        md_config = self.config.get("markdown", {})
        # Markdown mode only decides how NEW notes are created.
        self.md_enabled = md_config.get("enabled", False)
        self.md_buttons = {b.key: md_config.get("buttons", {}).get(b.key, b.default) for b in MD_TOOLBAR}

        # Main layout: scrollable options above a fixed Save button.
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_bottom(16)
        self.set_child(outer)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer.append(scrolled)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_top(16)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        scrolled.set_child(vbox)

        # --- Mode: decides how NEW notes are created ---
        md_mode_box = self._list()
        self._switch_row(md_mode_box, builtins._("Markdown mode"), self.md_enabled, self._on_md_enabled,
                         subtitle=builtins._("New notes are created in Markdown; existing notes are not changed"))
        vbox.append(md_mode_box)

        # --- Regular toolbar (shown in the regular mode) ---
        options = [
            ("bold", builtins._("Bold")),
            ("italic", builtins._("Italic")),
            ("underline", builtins._("Underline")),
            ("strikethrough", builtins._("Strikethrough")),
            ("list", builtins._("Bullet List")),
            ("text_color", builtins._("Text Color")),
            ("font_size", builtins._("Font Size")),
        ]
        self.regular_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.regular_section.append(self._title(builtins._("Toolbar Options")))
        self.switches = {}
        list_box = self._list()
        for key, label_text in options:
            self.switches[key] = self._switch_row(
                list_box, label_text, self.formatting_config.get(key, True),
                lambda state, k=key: self.formatting_config.__setitem__(k, state))
        self.regular_section.append(list_box)
        vbox.append(self.regular_section)

        # --- Markdown toolbar (shown in the Markdown mode) ---
        self.md_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.md_section.append(self._title(builtins._("Markdown Toolbar")))
        md_list = self._list()
        self.md_switches = {}
        for button in MD_TOOLBAR:
            self.md_switches[button.key] = self._switch_row(
                md_list, builtins._(button.tooltip), self.md_buttons[button.key],
                lambda state, k=button.key: self.md_buttons.__setitem__(k, state))
        self.md_section.append(md_list)
        vbox.append(self.md_section)
        self._sync_sections()

        # Save Button
        btn_save = Gtk.Button(label=builtins._("Save & Apply"))
        btn_save.add_css_class("suggested-action")
        btn_save.add_css_class("pill")
        btn_save.set_margin_start(16)
        btn_save.set_margin_end(16)
        btn_save.connect("clicked", self._on_save_clicked)
        outer.append(btn_save)

    @staticmethod
    def _title(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.add_css_class("title-4")
        label.set_halign(Gtk.Align.START)
        return label

    @staticmethod
    def _list() -> Gtk.ListBox:
        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.add_css_class("boxed-list")
        return list_box

    @staticmethod
    def _switch_row(list_box: Gtk.ListBox, title: str, active: bool, on_change,
                    subtitle: str = None) -> Gtk.Switch:
        row = Adw.ActionRow()
        row.set_title(title)
        if subtitle:
            row.set_subtitle(subtitle)
        switch = Gtk.Switch()
        switch.set_active(active)
        switch.set_valign(Gtk.Align.CENTER)
        # Update local config immediately on toggle; returning False lets the switch flip.
        switch.connect("state-set", lambda _s, state: (on_change(state), False)[1])
        row.add_suffix(switch)
        list_box.append(row)
        return switch

    def _on_md_enabled(self, state: bool):
        self.md_enabled = state
        self._sync_sections()

    def _sync_sections(self):
        """Shows the toolbar options of the selected mode only."""
        self.regular_section.set_visible(not self.md_enabled)
        self.md_section.set_visible(self.md_enabled)

    def _on_save_clicked(self, button):
        """Saves configuration and triggers update in the main application."""
        # Update the main config dictionary
        self.config["formatting"] = self.formatting_config
        self.config["markdown"] = {"enabled": self.md_enabled, "buttons": dict(self.md_buttons)}

        # Save to disk
        ConfigManager.save(self.config)

        # Trigger update in the main window to refresh all open notes
        if self.parent_window.main_window:
            self.parent_window.main_window.reload_configuration()

        self.close()
