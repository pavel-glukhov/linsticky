"""
Markdown mode for StickyWindow ("source / preview").

A note in Markdown mode keeps its raw Markdown source as untagged text in the
regular text buffer (so saving, the database format and older app versions are
unaffected). The note can be shown either as editable source or as a rendered,
read-only preview. Formatting buttons and shortcuts insert Markdown markers
instead of applying text tags.
"""
import builtins

from gi.repository import Gtk, Gdk, Adw, GLib, Pango

from content import markdown as md

if not hasattr(builtins, "_"):
    builtins._ = lambda s: s

MD_MARKERS = {"bold": "**", "italic": "*", "strikethrough": "~~"}
MD_LIST_PREFIX = "- "


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

    def create_markdown_menu_item(self, popover: Gtk.Popover) -> Gtk.Widget:
        """Check item in the note menu that turns Markdown mode on/off."""
        self._md_syncing = False
        self.chk_markdown = Gtk.CheckButton(label=builtins._("Markdown"),
                                            margin_top=5, margin_bottom=5, margin_start=5, margin_end=5)
        self.chk_markdown.set_active(getattr(self, "is_markdown", False))

        def on_toggled(check):
            if self._md_syncing:
                return
            popover.popdown()
            self.request_markdown_mode(check.get_active())

        self.chk_markdown.connect("toggled", on_toggled)
        return self.chk_markdown

    def sync_markdown_ui(self):
        """Brings header button, menu check, toolbar and stack page in line with the mode."""
        if getattr(self, "chk_markdown", None) is not None:
            self._md_syncing = True
            self.chk_markdown.set_active(self.is_markdown)
            self._md_syncing = False
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
        if hasattr(self, "format_bar"):
            self.format_bar.set_visible(not self.md_preview_active)
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

    # ------------------------------------------------------------------ mode switch
    def request_markdown_mode(self, enabled: bool):
        """Switches the note mode, asking for confirmation if formatting would be lost."""
        if enabled == self.is_markdown:
            return
        if enabled and not md.rich_is_lossless(self._get_buffer_segments()):
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=builtins._("Convert to Markdown?"),
                body=builtins._("Underline, text colors and font sizes have no Markdown "
                                "equivalent and will be removed."),
            )
            dialog.add_response("cancel", builtins._("Cancel"))
            dialog.add_response("convert", builtins._("Convert"))
            dialog.set_response_appearance("convert", Adw.ResponseAppearance.DESTRUCTIVE)

            def on_response(d, response):
                if response == "convert":
                    self._set_markdown_mode(True)
                else:
                    self.sync_markdown_ui()
                d.close()

            dialog.connect("response", on_response)
            dialog.present()
            return
        self._set_markdown_mode(enabled)

    def _set_markdown_mode(self, enabled: bool):
        segments = self._get_buffer_segments()
        self.is_markdown = enabled
        if self.main_window:
            self.main_window.set_card_markdown(self.note_id, enabled)

        self.buffer.begin_user_action()
        if enabled:
            self.buffer.set_text(md.rich_to_markdown(segments))
        else:
            source = "".join(seg["text"] for seg in segments)
            self.buffer.set_text("")
            self._insert_segments(md.markdown_to_rich(source))
        self.buffer.end_user_action()

        if self.note_id:
            self.db.set_markdown(self.note_id, enabled)
        self._dirty = True
        self._on_buffer_changed(self.buffer)

        self.md_preview_active = enabled and bool(self._get_buffer_text().strip())
        self.sync_markdown_ui()

    # ------------------------------------------------------------------ editing helpers
    def _get_buffer_text(self) -> str:
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, True)

    def md_wrap_selection(self, tag_name: str):
        """
        Toggles Markdown markers (e.g. ``**``) around the selection.
        Without a selection, inserts an empty marker pair at the cursor.
        """
        marker = MD_MARKERS.get(tag_name)
        if not marker:
            return
        buf = self.buffer
        size = len(marker)
        bounds = buf.get_selection_bounds()

        buf.begin_user_action()
        if not bounds:
            cursor = buf.get_iter_at_mark(buf.get_insert())
            buf.insert(cursor, marker + marker)
            cursor = buf.get_iter_at_mark(buf.get_insert())
            cursor.backward_chars(size)
            buf.place_cursor(cursor)
            buf.end_user_action()
            self.text_view.grab_focus()
            return

        start, end = bounds
        start_mark = buf.create_mark(None, start, True)
        end_mark = buf.create_mark(None, end, False)
        selected = buf.get_text(start, end, True)

        before, after = start.copy(), end.copy()
        before.backward_chars(size)
        after.forward_chars(size)
        outer_before = buf.get_text(before, start, True)
        outer_after = buf.get_text(end, after, True)

        if len(selected) >= 2 * size and selected.startswith(marker) and selected.endswith(marker):
            # Selection includes the markers: remove them.
            s = buf.get_iter_at_mark(start_mark)
            s_end = s.copy(); s_end.forward_chars(size)
            buf.delete(s, s_end)
            e = buf.get_iter_at_mark(end_mark)
            e_start = e.copy(); e_start.backward_chars(size)
            buf.delete(e_start, e)
        elif outer_before == marker and outer_after == marker:
            # Markers right around the selection: remove them.
            e = buf.get_iter_at_mark(end_mark)
            e_end = e.copy(); e_end.forward_chars(size)
            buf.delete(e, e_end)
            s = buf.get_iter_at_mark(start_mark)
            s_start = s.copy(); s_start.backward_chars(size)
            buf.delete(s_start, s)
        else:
            buf.insert(buf.get_iter_at_mark(end_mark), marker)
            buf.insert(buf.get_iter_at_mark(start_mark), marker)
            s = buf.get_iter_at_mark(start_mark)
            s.forward_chars(size)
            buf.move_mark(start_mark, s)
            e = buf.get_iter_at_mark(end_mark)
            e.backward_chars(size)
            buf.move_mark(end_mark, e)

        buf.select_range(buf.get_iter_at_mark(start_mark), buf.get_iter_at_mark(end_mark))
        buf.delete_mark(start_mark)
        buf.delete_mark(end_mark)
        buf.end_user_action()
        self.text_view.grab_focus()
