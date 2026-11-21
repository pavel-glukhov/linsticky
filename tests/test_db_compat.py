"""Databases written by the previous release must keep working unchanged."""
import sqlite3

from content import codec
from db.db_controller import NotesDB

# Schema of the previous release (no is_markdown column).
OLD_SCHEMA = """
CREATE TABLE notes (
    id INTEGER PRIMARY KEY, title TEXT, content TEXT,
    x INTEGER DEFAULT 0, y INTEGER DEFAULT 0, w INTEGER DEFAULT 300, h INTEGER DEFAULT 300,
    color TEXT DEFAULT '#FFF59D', deleted INTEGER DEFAULT 0, deleted_at TEXT,
    always_on_top INTEGER DEFAULT 0, is_open INTEGER DEFAULT 0, is_pinned INTEGER DEFAULT 0
)"""

RICH = codec.encode([{"text": "**not markdown** ", "tags": []},
                     {"text": "bold", "tags": ["bold"]}])


def make_old_db(path):
    conn = sqlite3.connect(path)
    conn.execute(OLD_SCHEMA)
    conn.execute("INSERT INTO notes(title, content, always_on_top, is_pinned) VALUES ('Old', ?, 1, 1)", (RICH,))
    conn.commit()
    conn.close()


def test_old_notes_stay_rich_text_and_untouched(tmp_path):
    path = str(tmp_path / "notes.db")
    make_old_db(path)
    db = NotesDB(path)
    row = db.get(1)
    assert row["is_markdown"] == 0
    assert row["content"] == RICH
    assert row["always_on_top"] == 1 and row["is_pinned"] == 1
    # Saving geometry/text does not touch always_on_top or the mode.
    db.update(1, RICH, 10, 20, 300, 200, "#FFF59D")
    row = db.get(1)
    assert row["always_on_top"] == 1 and row["is_markdown"] == 0


def test_mode_is_fixed_at_creation(tmp_path):
    db = NotesDB(str(tmp_path / "notes.db"))
    assert db.get(db.add())["is_markdown"] == 0
    assert db.get(db.add(is_markdown=True))["is_markdown"] == 1


def test_previous_release_can_still_insert(tmp_path):
    path = str(tmp_path / "notes.db")
    make_old_db(path)
    NotesDB(path).conn.close()  # migrate
    conn = sqlite3.connect(path)
    # The previous release's INSERT (without is_markdown) keeps working.
    conn.execute("INSERT INTO notes(title, content, x, y, w, h, color, always_on_top) "
                 "VALUES ('n', '', 1, 2, 3, 4, '#FFF', 0)")
    assert conn.execute("SELECT is_markdown FROM notes WHERE title='n'").fetchone()[0] == 0
