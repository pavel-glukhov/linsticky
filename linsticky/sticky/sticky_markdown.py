"""
Markdown mode for StickyWindow ("source / preview").

The type is chosen when a note is created ("+" -> Text Note / Markdown Note)
and never changes: text notes (including all notes from earlier versions) are
never converted.

A note in Markdown mode keeps its raw Markdown source as untagged text in the
regular text buffer (so saving, the database format and older app versions are
unaffected). The note can be shown either as editable source or as a rendered,
read-only preview. Formatting buttons and shortcuts insert Markdown markers
instead of applying text tags; the bottom toolbar shows the Markdown buttons
chosen in the settings.
"""
import builtins

from gi.repository import Gtk, Gdk, GLib, Pango

from content import markdown as md
from content import markdown_edit as md_edit

if not hasattr(builtins, "_"):
    builtins._ = lambda s: s


def markdown_buttons(config: dict) -> dict:
    """Returns {button key: visible} for the Markdown toolbar from the app config."""
    section = config.get("markdown") if isinstance(config, dict) else None
    if not isinstance(section, dict):
        section = {}
    buttons = dict(md_edit.MD_TOOLBAR_DEFAULTS)
    if isinstance(section.get("buttons"), dict):
        buttons.update({k: bool(v) for k, v in section["buttons"].items() if k in buttons})
    return buttons


class StickyMarkdown:
    """Mixin implementing the Markdown source/preview mode of a note."""

    # ------------------------------------------------------------------ UI
    def setup_markdown_preview(self):
        """Creates the rendered preview page next to the editor in `content_stack`."""
        self.is_markdown = getattr(self, "is_markdown", False)
        self.md_preview_active = False

        self.preview_label = Gtk.Label(
            xalign=0, yalign=0, wrap=True, use_markup=True,
            valign=Gtk.Align.START, halign=Gtk.Align.FILL,
        )
        self.preview_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.preview_label.add_css_class("sticky-md-preview")

        double_click = Gtk.GestureClick.new()
        double_click.connect("pressed", self._on_preview_pressed)
        self.preview_label.add_controller(double_click)

        preview_scrolled = Gtk.ScrolledWindow(child=self.preview_label, vexpand=True)
        preview_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.content_stack.add_named(preview_scrolled, "preview")

        # Ctrl+E toggles source/preview. Window-level so it also works in preview.
        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_markdown_key_pressed)
        self.add_controller(key_ctrl)

    def create_markdown_toggle_button(self) -> Gtk.Button:
        """Header button switching between source and preview (Markdown notes only)."""
        self.btn_md_toggle = Gtk.Button(has_frame=False, icon_name="view-reveal-symbolic")
        self.btn_md_toggle.add_css_class("header-btn-subtle")
        self.btn_md_toggle.connect("clicked", lambda *_: self.set_markdown_preview(not self.md_preview_active))
        self.btn_md_toggle.set_visible(False)
        return self.btn_md_toggle

    def sync_markdown_ui(self):
        """Brings header button, toolbar and stack page in line with the mode."""
        if getattr(self, "btn_md_toggle", None) is not None:
            self.btn_md_toggle.set_visible(self.is_markdown)
        if not self.is_markdown:
            self.md_preview_active = False
        self.setup_formatting_bar()
        self._apply_markdown_view()

    def set_markdown_preview(self, active: bool):
        """Shows the rendered preview (True) or the editable source (False)."""
        self.md_preview_active = bool(active) and self.is_markdown
        self._apply_markdown_view()
        if not self.md_preview_active:
            self.text_view.grab_focus()

    def _apply_markdown_view(self):
        if self.md_preview_active:
            self._render_markdown_preview()
            self.content_stack.set_visible_child_name("preview")
        else:
            self.content_stack.set_visible_child_name("edit")
        if getattr(self, "btn_md_toggle", None) is not None:
            if self.md_preview_active:
                self.btn_md_toggle.set_icon_name("document-edit-symbolic")
                self.btn_md_toggle.set_tooltip_text(builtins._("Edit (Ctrl+E)"))
            else:
                self.btn_md_toggle.set_icon_name("view-reveal-symbolic")
                self.btn_md_toggle.set_tooltip_text(builtins._("Preview (Ctrl+E)"))

    def _render_markdown_preview(self):
        source = self._get_buffer_text()
        markup = md.to_pango(source)
        try:
            Pango.parse_markup(markup, -1, "\0")
        except GLib.Error as e:
            # The renderer escapes all text, so this should not happen;
            # never show an empty note because of a markup problem.
            print(f"WARNING: Markdown preview fell back to plain text: {e}")
            self.preview_label.set_text(source)
            return
        except Exception:
            pass  # Validation helper unavailable; render anyway.
        self.preview_label.set_markup(markup)

    def _on_preview_pressed(self, gesture, n_press, x, y):
        if n_press == 2:
            self.set_markdown_preview(False)

    def _on_markdown_key_pressed(self, controller, keyval, keycode, state) -> bool:
        if not self.is_markdown or not (state & Gdk.ModifierType.CONTROL_MASK):
            return False
        if keyval in (Gdk.KEY_e, Gdk.KEY_E):
            self.set_markdown_preview(not self.md_preview_active)
            return True
        return False

    # ------------------------------------------------------------------ editing helpers
    def _get_buffer_text(self) -> str:
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, True)

    def build_markdown_toolbar(self, icon_size: int):
        """Fills ``self.format_bar`` with the Markdown buttons enabled in the settings."""
        visible = markdown_buttons(self.config)
        for button in md_edit.MD_TOOLBAR:
            if not visible.get(button.key, button.default):
                continue
            btn = Gtk.Button(has_frame=False)
            if button.icon:
                btn.set_child(Gtk.Image.new_from_icon_name(button.icon))
            else:
                btn.set_child(Gtk.Label(label=button.label, use_markup=True))
            btn.set_tooltip_text(builtins._(button.tooltip))
            btn.add_css_class("format-btn-tiny")
            btn.set_size_request(icon_size, icon_size)
            btn.connect("clicked", (lambda key: lambda _b: self.md_toolbar_action(key))(button.key))
            self.format_bar.append(btn)

    def md_toolbar_action(self, action: str):
        """Applies a Markdown toolbar action to the selection (switching to source first)."""
        if self.md_preview_active:
            self.set_markdown_preview(False)
        buf = self.buffer
        bounds = buf.get_selection_bounds()
        if bounds:
            sel_start, sel_end = bounds[0].get_offset(), bounds[1].get_offset()
        else:
            sel_start = sel_end = buf.get_iter_at_mark(buf.get_insert()).get_offset()

        edit = md_edit.apply(action, self._get_buffer_text(), sel_start, sel_end)
        if edit is None:
            return

        buf.begin_user_action()
        start = buf.get_iter_at_offset(edit.start)
        end = buf.get_iter_at_offset(edit.end)
        buf.delete(start, end)
        buf.insert(buf.get_iter_at_offset(edit.start), edit.text)
        buf.select_range(buf.get_iter_at_offset(edit.sel_start), buf.get_iter_at_offset(edit.sel_end))
        buf.end_user_action()
        self.text_view.grab_focus()

    def md_wrap_selection(self, tag_name: str):
        """Keyboard shortcuts (Ctrl+B/I/S...) in Markdown mode."""
        if tag_name in md_edit.WRAP_MARKERS:
            self.md_toolbar_action(tag_name)
