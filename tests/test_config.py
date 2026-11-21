import json

from config import config_manager as cm


def load_with(tmp_path, monkeypatch, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(cm, "CONF_PATH", str(path))
    monkeypatch.setattr(cm, "CONF_DIR", str(tmp_path))
    return cm.ConfigManager.load()


def test_config_from_previous_version_keeps_markdown_off(tmp_path, monkeypatch):
    # A config written by the previous release has no "markdown" section.
    cfg = load_with(tmp_path, monkeypatch, {"language": "ru", "formatting": {"bold": False}})
    assert cfg["markdown"]["enabled"] is False
    assert cfg["formatting"]["bold"] is False
    assert cfg["markdown"]["buttons"]["bold"] is True


def test_markdown_section_merges_with_defaults(tmp_path, monkeypatch):
    cfg = load_with(tmp_path, monkeypatch,
                    {"markdown": {"enabled": True, "buttons": {"hr": True, "bogus": True, "bold": False}}})
    buttons = cfg["markdown"]["buttons"]
    assert buttons["hr"] is True and buttons["bold"] is False
    assert "bogus" not in buttons
    assert buttons["heading"] is True  # missing key -> default
