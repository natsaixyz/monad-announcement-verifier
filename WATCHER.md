# Announcement watcher

Standalone, no website dependency: `watcher.py` uses the same `verifier.py` and locally pinned `config.json`. No webhook or site is considered a source of cryptographic trust.

## Install

Docker + Compose required; from the project root:

```bash
cp .env.watcher.example .env.watcher
# Paste your private Discord webhook URL into .env.watcher
chmod 600 .env.watcher
docker compose -f compose.watcher.yaml up -d --build
docker compose -f compose.watcher.yaml logs -f --tail=30
```

**Optional test:** `docker compose -f compose.watcher.yaml run --rm watcher python watcher.py --test-webhook`

The watcher runs alone (separate Compose project), binds **no ports**, runs as an unprivileged user, and uses a read-only filesystem. It keeps deduplication state in a dedicated persistent Docker volume; restarting the container doesn't resend seen alerts. Webhook credentials go in `.env.watcher` (gitignored); anyone with Docker administration rights can inspect container environment variables, so secure host access accordingly.

## Behavior

- Every 5 minutes (configurable from 60 seconds to 24 hours), download Monad's public GitHub announcement snapshot, discover complete `mf-N` entries, and locally verify new or changed announcements using **two distinct authorized GPG signers**.
- The **first run** sends a verified status for the current latest announcement; it silently registers older valid ones. `START_MODE=silent` disables initial success alerts. Invalid announcements are never silently accepted.
- New/changed signed text or signatures produce a fresh alert, including severity. Replacing an earlier announcement also triggers an alert even if the new signatures are valid.
- Invalid signatures, missing trusted keys, and expired announcements are labeled **GPG VERIFICATION FAILED**. No announcement text is executed.
- Webhook delivery failure leaves the alert pending for retry; brief GitHub outages are logged, not falsely classified as signature failure. Exactly-once delivery is not guaranteed if a process crashes after sending but before saving state.
- No keys are automatically trusted on rotation. Update pinned fingerprints only after independently confirming them via official Monad documentation.
- Public GitHub only: confidential email-only announcements are **not** covered. Alerts are **not** a substitute for Monad's official channels.

## Commands

```bash
docker compose -f compose.watcher.yaml ps
docker compose -f compose.watcher.yaml logs -f --tail=30
docker compose -f compose.watcher.yaml down
```

`down` preserves the state volume; don't use `down -v` unless you intentionally want to forget which alerts were sent. To deploy only the watcher, the repository's `Dockerfile.watcher`, `compose.watcher.yaml`, `watcher.py`, `notifiers.py`, `verifier.py`, `config.json`, and `.env.watcher` suffice.

## Adding a notification channel

`watcher.run_cycle()` produces channel-neutral `Event` objects. `notifiers.py` currently supplies `DiscordNotifier`. Adding Telegram later means implementing another `send(event)` adapter, not changing cryptographic verification or the website.
