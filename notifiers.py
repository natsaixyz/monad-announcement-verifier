"""Notification adapters. No dependency on the web application."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    number: int
    status: str                   # VERIFIED or FAILED
    kind: str                     # NEW, CHANGED, RECOVERED, TEST
    severity: str = "UNCLASSIFIED"
    created: str = ""
    signers: tuple[str, ...] = ()
    reason: str = ""


class DeliveryError(Exception):
    pass


def webhook_url_valid(url: str) -> bool:
    """Accept only standard Discord webhook endpoints (no arbitrary SSRF target)."""
    try:
        p = urllib.parse.urlsplit(url)
        port = p.port
    except ValueError:
        return False
    return (
        p.scheme == "https" and p.hostname in {"discord.com", "discordapp.com"}
        and port in {None, 443} and p.username is None and p.password is None
        and not p.query and not p.fragment
        and re.fullmatch(r"/api/webhooks/[0-9]+/[A-Za-z0-9_-]+", p.path) is not None
    )


class DiscordNotifier:
    def __init__(self, url: str):
        if not webhook_url_valid(url):
            raise ValueError("DISCORD_WEBHOOK_URL must be a standard HTTPS Discord webhook URL")
        self._url = url

    @staticmethod
    def payload(event: Event) -> dict:
        if event.status == "VERIFIED":
            color = {"GREEN": 0x2E865F, "ORANGE": 0xE29C39, "RED": 0xCC4444}.get(event.severity, 0x477CB5)
            label = f"GPG VERIFIED · CODE {event.severity}" if event.severity != "UNCLASSIFIED" else "GPG VERIFIED"
            desc = "Two or more authorized Monad Foundation signatures verified locally."
        elif event.status == "TEST":
            color = 0x477CB5
            label = "WATCHER TEST — NOT AN ANNOUNCEMENT"
            desc = "Discord delivery is working. No announcement was verified by this test."
        else:
            color = 0xD14949
            label = "GPG VERIFICATION FAILED"
            desc = "Do not act on this announcement until independently verified."
        fields = [{"name": "Event", "value": event.kind, "inline": True}]
        if event.created:
            fields.append({"name": "Created", "value": event.created[:128], "inline": True})
        if event.signers:
            fields.append({"name": "Authorized signers", "value": f"{len(event.signers)} distinct · " + ", ".join(x[:8] + "…" + x[-8:] for x in event.signers), "inline": False})
        if event.reason:
            fields.append({"name": "Reason", "value": event.reason[:350], "inline": False})
        title = f"MF Announcement #{event.number} · {label}" if event.status != "TEST" else label
        url = f"https://github.com/monad-crypto/mf-nodeops-comms/tree/main/announcements/mf-{event.number}"
        embed = {"title": title, "description": desc, "color": color, "fields": fields, "footer": {"text": "Natsai · local GPG verification · no actions executed"}}
        if event.status != "TEST":
            embed["url"] = url
        return {"username": "Monad Announcement Watcher", "allowed_mentions": {"parse": []}, "embeds": [embed]}

    def send(self, event: Event) -> None:
        body = json.dumps(self.payload(event), separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self._url, data=body, headers={"Content-Type": "application/json", "User-Agent": "Natsai-Monad-Watcher/1.0"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                if response.status not in (200, 204):
                    raise DeliveryError(f"Discord webhook returned HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            # Do not log URL, exception repr, or response body: webhook token is secret.
            raise DeliveryError(f"Discord webhook returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise DeliveryError("Discord webhook delivery failed or timed out") from None
