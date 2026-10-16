# Monad Announcement Verifier

**[Live verifier](https://monad-verify.natsai.xyz)** · [Source](https://github.com/natsaixyz/monad-announcement-verifier)

Paste a Monad Foundation `mf-N` announcement link to verify **2 distinct authorized GPG signatures** and read the signed message.

Need automatic alerts instead? **[Monad Announcement Watcher](https://github.com/natsaixyz/monad-announcement-watcher)**.

## Self-host

Requires Docker and Docker Compose.

```bash
git clone https://github.com/natsaixyz/monad-announcement-verifier.git
cd monad-announcement-verifier
docker compose up -d --build
```

Open `http://localhost:8080` on the host. The service binds to `127.0.0.1`; use an HTTPS reverse proxy and rate-limit `/api/verify` if exposing it publicly.

## Trust & scope

- Uses local, pinned public-key fingerprints from [`config.json`](config.json). **Check them against [Monad's official list](https://docs.monad.xyz/node-ops/gpg-keys.json)** before relying on results; review key rotations manually.
- Verifies public GitHub announcements only. No validator access, private keys, or automatic execution.
- The hosted site reports **Natsai's** verification result. Self-host for independent verification. Not an official Monad Foundation tool.

## Tests

Requires Python 3.11+ and GnuPG:

```bash
python3 -m unittest discover -s tests -q
```

MIT · © 2026 Natsai OÜ
