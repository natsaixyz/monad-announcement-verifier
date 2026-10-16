"""Independent Monad announcement watcher: local GPG verification -> notifications.

Standard library + GnuPG. No HTTP-server dependency, wallet, or validator access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import signal
import tempfile
import time
import zipfile
import io
from pathlib import Path
from typing import Callable

from notifiers import DiscordNotifier, DeliveryError, Event
from verifier import (
    VerificationError, download_archive, load_config,
    verify_announcement, MAX_ANNOUNCEMENT, MAX_SIGNATURE,
)

LOG = logging.getLogger("monad-watcher")
ROOT = Path(__file__).resolve().parent
STATE_VERSION = 1
PREFIX = "mf-nodeops-comms-main/announcements/"
ITEM_RE = re.compile(r"mf-(0|[1-9][0-9]{0,5})/(announcement\.(?:txt|sig))\Z")


def discover(archive_data: bytes) -> dict[int, str]:
    """Return SHA256 of signed bytes, by MF number. Incomplete folders are ignored.

    A new or edited file triggers re-verification; no GitHub commits are executed.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            if len(archive.infolist()) > 20000:
                raise VerificationError("Repository archive has too many entries")
            names: dict[int, dict[str, str]] = {}
            for info in archive.infolist():
                if not info.filename.startswith(PREFIX):
                    continue
                match = ITEM_RE.fullmatch(info.filename[len(PREFIX):])
                if match and not info.is_dir():
                    number = int(match.group(1))
                    kind = match.group(2)
                    limit = MAX_ANNOUNCEMENT if kind == "announcement.txt" else MAX_SIGNATURE
                    if not (0 < info.file_size <= limit):
                        raise VerificationError(f"MF #{number} contains an invalid {kind} size")
                    names.setdefault(number, {})[kind] = info.filename
            hashes = {}
            for number, files in sorted(names.items()):
                if "announcement.txt" not in files or "announcement.sig" not in files:
                    continue
                h = hashlib.sha256()
                for kind in ("announcement.txt", "announcement.sig"):
                    limit = MAX_ANNOUNCEMENT if kind.endswith(".txt") else MAX_SIGNATURE
                    with archive.open(files[kind]) as f:
                        data = f.read(limit + 1)
                    if len(data) > limit:
                        raise VerificationError(f"MF #{number} exceeds size limit")
                    h.update(len(data).to_bytes(8, "big"))
                    h.update(data)
                hashes[number] = h.hexdigest()
            if not hashes:
                raise VerificationError("No complete MF announcements found")
            return hashes
    except (zipfile.BadZipFile, EOFError, OSError, RuntimeError) as exc:
        raise VerificationError("Malformed GitHub archive") from exc


def initial_state() -> dict:
    return {"version": STATE_VERSION, "initialized": False, "seen": {}}


def load_state(path: Path) -> dict:
    if not path.exists():
        return initial_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != STATE_VERSION or type(data.get("initialized")) is not bool:
            raise ValueError("invalid schema/version")
        seen = data.get("seen")
        if not isinstance(seen, dict):
            raise ValueError("missing records")
        for num, record in seen.items():
            if not re.fullmatch(r"(0|[1-9][0-9]{0,5})", num):
                raise ValueError("bad MF number in state")
            if not isinstance(record, dict) or not re.fullmatch(r"[0-9a-f]{64}", record.get("digest", "")) or record.get("status") not in ("VERIFIED", "FAILED"):
                raise ValueError("corrupted state record")
        return data
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        # Never silently reset state: would cause unexpected duplicate notifications.
        raise RuntimeError(f"Watcher state could not be read. Resolve or restore {path}: {exc}") from None


def save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, sort_keys=True, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def run_cycle(state: dict, archive_bytes: bytes, config: dict, send: Callable[[Event], None], persist: Callable[[], None], start_mode: str = "latest") -> int:
    """Poll one immutable snapshot; do not acknowledge an event until delivered."""
    announcements = discover(archive_bytes)
    first = not state["initialized"]
    newest = max(announcements)
    processed = 0
    delivery_errors: list[DeliveryError] = []
    for number, digest in sorted(announcements.items()):
        key = str(number)
        previous = state["seen"].get(key)
        if previous and previous["digest"] == digest and previous["status"] == "VERIFIED":
            continue
        status = "VERIFIED"
        result = None
        error = ""
        try:
            result = verify_announcement(number, config, archive_bytes=archive_bytes)
        except VerificationError as exc:
            status = "FAILED"
            error = str(exc)
        # If the failed result has not changed, retry verification but don't repeat alerts.
        if previous and previous["digest"] == digest and previous["status"] == status:
            continue
        kind = "NEW" if not previous else ("CHANGED" if previous["digest"] != digest else "RECOVERED")
        if first and status == "VERIFIED" and (start_mode == "silent" or number != newest):
            # First deployment should not spam old valid announcements.
            pass
        else:
            event = Event(number=number, status=status, kind=kind,
                          severity=result["severity"] if result else "UNCLASSIFIED",
                          created=result["created"] if result else "",
                          signers=tuple(result["signers"]) if result else (), reason=error)
            try:
                send(event)
            except DeliveryError as exc:
                delivery_errors.append(exc)  # Not acknowledged; retry on next poll.
                continue  # Still check newer announcements, including urgent CODE RED.
        state["seen"][key] = {"digest": digest, "status": status}
        persist()
        processed += 1
        LOG.info("MF #%d %s (%s)", number, status, kind)
    if not state["initialized"] and not delivery_errors:
        state["initialized"] = True
        persist()
    if delivery_errors:
        raise DeliveryError(f"{len(delivery_errors)} announcement alert(s) could not be delivered; pending retry")
    return processed


def get_args():
    p = argparse.ArgumentParser(description="Independent Monad GPG announcement watcher")
    p.add_argument("--once", action="store_true", help="Poll once and exit")
    p.add_argument("--test-webhook", action="store_true", help="Send a clearly marked test alert, without altering state")
    return p.parse_args()


def main() -> int:
    args = get_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not url:
        LOG.error("DISCORD_WEBHOOK_URL is required; see .env.watcher.example")
        return 2
    try:
        notify = DiscordNotifier(url)
    except ValueError as exc:
        LOG.error("%s", exc)
        return 2
    if args.test_webhook:
        try:
            notify.send(Event(number=0, status="TEST", kind="TEST"))
        except DeliveryError as exc:
            LOG.error("%s", exc)
            return 1
        LOG.info("Discord test delivered; no announcement verified")
        return 0
    try:
        config = load_config(Path(os.environ.get("VERIFIER_CONFIG", ROOT / "config.json")))
        interval = int(os.environ.get("CHECK_INTERVAL_SECONDS", "300"))
        if not 60 <= interval <= 86400:
            raise ValueError("CHECK_INTERVAL_SECONDS must be 60..86400")
        start_mode = os.environ.get("START_MODE", "latest").lower()
        if start_mode not in ("latest", "silent"):
            raise ValueError("START_MODE must be latest or silent")
        state_path = Path(os.environ.get("WATCHER_STATE", "/state/watcher.json"))
        state = load_state(state_path)
        # Check writable durable storage before sending any alert.
        save_state(state_path, state)
    except (VerificationError, ValueError, RuntimeError) as exc:
        LOG.error("Configuration/state error: %s", exc)
        return 2

    stopped = False

    def stop(_signal, _frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    LOG.info("Polling public Monad announcements every %ds; GPG verification is local", interval)
    failures = 0
    while not stopped:
        try:
            archive = download_archive()
            count = run_cycle(state, archive, config, notify.send, lambda: save_state(state_path, state), start_mode)
            failures = 0
            LOG.info("Poll OK, %d new/changed results processed", count)
        except (VerificationError, DeliveryError, OSError) as exc:
            failures += 1
            LOG.warning("Poll failed (%d consecutive): %s", failures, exc)
            # Keep state unchanged for unsent events. No false GPG failure on network outages.
            if args.once:
                return 1
        if args.once:
            return 0
        # Respond promptly to SIGTERM, no external scheduler or cron required.
        for _ in range(interval):
            if stopped:
                break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
