"""Alert channels: Discord webhook, email (SMTP), macOS notifications + dispatcher."""

from __future__ import annotations

import smtplib
import subprocess
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

import requests

from .config import Settings
from .models import AlertEvent

POKEMON_YELLOW = 0xFFCB05


def send_discord(webhook_url: str, event: AlertEvent, mention: str = "") -> tuple[bool, str]:
    if not webhook_url:
        return False, "no webhook configured"
    embed = {
        "title": event.title[:256],
        "description": event.message[:4000],
        "color": POKEMON_YELLOW,
    }
    if event.url:
        embed["url"] = event.url
        embed["fields"] = [{"name": "Link", "value": event.url}]
    payload: dict = {"embeds": [embed]}
    if mention:
        payload["content"] = mention
    try:
        r = requests.post(webhook_url, json=payload, timeout=15)
        if r.status_code in (200, 204):
            return True, "ok"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.RequestException as e:
        return False, str(e)


def _email_html(event: AlertEvent) -> str:
    link = ""
    if event.url:
        link = (
            f'<p><a href="{escape(event.url)}" '
            f'style="background:#FFCB05;color:#222;padding:10px 16px;'
            f'text-decoration:none;border-radius:6px;font-weight:bold;">'
            f'Open product page →</a></p>'
        )
    return (
        f'<div style="font-family:sans-serif;max-width:520px">'
        f'<h2 style="margin-bottom:4px">{escape(event.title)}</h2>'
        f'<p style="white-space:pre-wrap">{escape(event.message)}</p>'
        f'{link}'
        f'<hr><p style="color:#888;font-size:12px">PokeDrop — personal drop alert. '
        f'You still buy manually; this tool never purchases.</p></div>'
    )


def send_email(cfg, event: AlertEvent) -> tuple[bool, str]:
    if not (cfg.username and cfg.from_addr and cfg.to_addrs):
        return False, "email not fully configured (need username, from_addr, to_addrs)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = event.title[:200]
    msg["From"] = cfg.from_addr
    msg["To"] = ", ".join(cfg.to_addrs)
    text = event.message + (f"\n\n{event.url}" if event.url else "")
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(_email_html(event), "html", "utf-8"))

    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as server:
            server.ehlo()
            if cfg.use_tls:
                server.starttls()
                server.ehlo()
            if cfg.password:
                server.login(cfg.username, cfg.password)
            server.sendmail(cfg.from_addr, cfg.to_addrs, msg.as_string())
        return True, "ok"
    except (smtplib.SMTPException, OSError) as e:
        return False, str(e)


def _applescript_str(s: str) -> str:
    """Quote a string as an AppleScript literal (escapes \\, \", and newlines)."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def send_macos(event: AlertEvent) -> tuple[bool, str]:
    """Native macOS Notification Center pop-up via osascript."""
    if sys.platform != "darwin":
        return False, "macos notifications only work on macOS"
    script = (
        f"display notification {_applescript_str(event.message[:180])} "
        f"with title {_applescript_str(event.title[:60])} sound name \"Glass\""
    )
    try:
        proc = subprocess.run(["osascript", "-e", script],
                              capture_output=True, timeout=10)
        if proc.returncode == 0:
            return True, "ok"
        return False, proc.stderr.decode(errors="replace")[:200]
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def dispatch(settings: Settings, event: AlertEvent) -> dict[str, tuple[bool, str]]:
    """Send an event to every enabled channel; return per-channel (ok, detail)."""
    results: dict[str, tuple[bool, str]] = {}
    if settings.discord.enabled:
        results["discord"] = send_discord(
            settings.discord.webhook_url, event, settings.discord.mention
        )
    if settings.email.enabled:
        results["email"] = send_email(settings.email, event)
    if settings.macos.enabled:
        results["macos"] = send_macos(event)
    if not results:
        results["(none)"] = (False, "no alert channels enabled in settings.yaml")
    return results
