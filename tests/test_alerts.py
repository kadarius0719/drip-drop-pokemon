import pokedrop.alerts as alerts
from pokedrop.alerts import _applescript_str, dispatch, send_discord, send_email, send_macos
from pokedrop.config import EmailSettings, Settings
from pokedrop.models import AlertEvent

EVENT = AlertEvent(kind="test", title="hi", message="body", url="http://x")


def test_dispatch_nothing_enabled():
    results = dispatch(Settings(), EVENT)  # all channels disabled by default
    assert results == {"(none)": (False, "no alert channels enabled in settings.yaml")}


def test_discord_no_webhook_guarded():
    ok, detail = send_discord("", EVENT)
    assert ok is False and "webhook" in detail


def test_email_not_configured_guarded():
    ok, detail = send_email(EmailSettings(), EVENT)
    assert ok is False and "not fully configured" in detail


def test_applescript_escaping():
    out = _applescript_str('he said "hi"\nline2\\end')
    assert out.startswith('"') and out.endswith('"')
    assert '\\"' in out          # quotes escaped
    assert '\\n' in out          # newline escaped
    assert '\\\\' in out         # backslash escaped


def test_macos_non_darwin(monkeypatch):
    monkeypatch.setattr(alerts.sys, "platform", "linux")
    ok, detail = send_macos(EVENT)
    assert ok is False and "macOS" in detail


def test_macos_darwin_path(monkeypatch):
    monkeypatch.setattr(alerts.sys, "platform", "darwin")
    seen = {}

    class R:
        returncode = 0
        stderr = b""

    def fake_run(args, capture_output, timeout):
        seen["args"] = args
        return R()

    monkeypatch.setattr(alerts.subprocess, "run", fake_run)
    ok, detail = send_macos(AlertEvent(kind="test", title='q"uote', message="l1\nl2", url=""))
    assert ok is True and detail == "ok"
    assert seen["args"][0] == "osascript"
