import json

from config import config_manager as cm


def load_with(tmp_path, monkeypatch, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(cm, "CONF_PATH", str(path))
    monkeypatch.setattr(cm, "CONF_DIR", str(tmp_path))
    return cm.ConfigManager.load()


def test_config_from_2_0_creates_text_notes(tmp_path, monkeypatch):
    # A config written by 2.0.x has no Markdown settings at all.
    cfg = load_with(tmp_path, monkeypatch, {"language": "ru", "formatting": {"bold": False}})
    assert cfg["new_note_type"] == "text"
    assert cfg["formatting"]["bold"] is False
    assert cfg["markdown"]["buttons"]["bold"] is True


def test_markdown_switch_from_2_1_becomes_note_type(tmp_path, monkeypatch):
    cfg = load_with(tmp_path, monkeypatch, {"markdown": {"enabled": True, "buttons": {"hr": True}}})
    assert cfg["new_note_type"] == "markdown"
    assert "enabled" not in cfg["markdown"]
    assert cfg["markdown"]["buttons"]["hr"] is True
    cfg = load_with(tmp_path, monkeypatch, {"markdown": {"enabled": False}})
    assert cfg["new_note_type"] == "text"


def test_saved_note_type_wins_over_old_switch(tmp_path, monkeypatch):
    cfg = load_with(tmp_path, monkeypatch, {"new_note_type": "text", "markdown": {"enabled": True}})
    assert cfg["new_note_type"] == "text"


def test_update_keeps_other_keys(tmp_path, monkeypatch):
    load_with(tmp_path, monkeypatch, {"language": "de", "new_note_type": "markdown"})
    cfg = cm.ConfigManager.update({"language": "fr"})
    assert cfg["language"] == "fr" and cfg["new_note_type"] == "markdown"
    assert cm.ConfigManager.load()["new_note_type"] == "markdown"


def test_markdown_section_merges_with_defaults(tmp_path, monkeypatch):
    cfg = load_with(tmp_path, monkeypatch,
                    {"markdown": {"enabled": True, "buttons": {"hr": True, "bogus": True, "bold": False}}})
    buttons = cfg["markdown"]["buttons"]
    assert buttons["hr"] is True and buttons["bold"] is False
    assert "bogus" not in buttons
    assert buttons["heading"] is True  # missing key -> default
