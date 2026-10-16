# Monad Announcement Verifier

**Live Verifier:** https://monad-verify.natsai.xyz

A minimal, read-only GPG verification page for [Monad Foundation node-operator announcements](https://docs.monad.xyz/node-ops/announcements).

The latest public `mf-N` is preselected automatically (or paste an official GitHub URL) → verify **two distinct authorized signatures** → read the signed message. No login, database, wallet, validator access, or external Python packages.

## Run it

**Requirements:** Docker + Docker Compose.

```bash
docker compose up -d --build
```

Open **http://localhost:8080** on the server. It binds to `127.0.0.1` by default; for public access use an HTTPS reverse proxy (Nginx/Caddy/Cloudflare). Put rate limiting on `/api/verify` if public.

To stop: `docker compose down`.

## Automatic Discord alerts (optional)

The watcher runs **independently of the website**, with the same local GnuPG verifier. No exposed ports or Nginx configuration.

```bash
cp .env.watcher.example .env.watcher
# Set DISCORD_WEBHOOK_URL in .env.watcher
chmod 600 .env.watcher
docker compose -f compose.watcher.yaml up -d --build
```

By default it polls every 5 minutes, verifies new/edited signed files, and sends one Discord alert per change. On first install it sends one verification alert for the latest announcement; older valid announcements are silently recorded. Failed verification always alerts. To test delivery without simulating a signature check:

```bash
docker compose -f compose.watcher.yaml run --rm watcher python watcher.py --test-webhook
```

View status: `docker compose -f compose.watcher.yaml logs -f --tail=30`.

**Watcher-only use:** Clone this repository and run only `compose.watcher.yaml`. The web UI and server are **not** started. See [watcher details](WATCHER.md) for state, recovery, and notification policy. Never commit `.env.watcher`.

## Configuration

Only **`config.json`** matters for normal operation:

```json
{
  "trusted_fingerprints": [
    "B26F10A7157EA66528FD21381CD1328B3352B251",
    "EE7A445EC4643BCEC07E76982E22B777D5136DBD",
    "53E38FB05A545B69C2C284EA27C4446634EC4967",
    "9B5C1110910EF0ECEBEB86DF1E8F69044F1A9A65",
    "C63CAE08321029D52ACCD85CF8AEB590EB6069FB"
  ],
  "required_signatures": 2
}
```

Those fingerprints match Monad's [published authorized signer list](https://docs.monad.xyz/node-ops/gpg-keys.json), checked October 16, 2026. **Verify them independently before relying on this tool.** These are locally pinned trust anchors. New or replacement keys downloaded from GitHub **never automatically become trusted**. To approve a rotation, verify new full primary-key fingerprints out of band, edit `config.json`, then `docker compose up -d --build`.

For non-Docker use: install Python 3.11+ and `gpg`, then `python app.py` (default port 8080). The Docker image runs as an unprivileged user with a read-only filesystem.

## Security model

- The latest announcement number is discovered from Monad's GitHub repository and cached for 5 minutes. Discovery **does not** authenticate an announcement; click **Verify** to perform GPG verification. If GitHub is unavailable, enter an MF number manually.

- Only GitHub links to `monad-crypto/mf-nodeops-comms` (and `mf-N` numbers) are accepted; users cannot choose a remote fetch URL. The server downloads one bounded GitHub ZIP snapshot for each request.
- Files are extracted **in memory by exact path**; nothing from the repository is executed.
- Official public keys are inspected, and *only keys matching locally pinned full primary fingerprints* are imported into an isolated temporary GPG home.
- GnuPG validates the detached signatures against the exact `announcement.txt` bytes. Verification requires the configured minimum number of **different** authorized primary keys; any invalid, expired, revoked, or unknown signature fails closed.
- The signed announcement index, UTC creation timestamp, optional explicit `Expires:` field, and conflicting severity codes are checked. Read the message yourself for **other expiry/effective instructions expressed in prose**.
- No commands run on validators, and no automatic upgrades are performed.
- Each website verification is independent; no result is stored by the website. The optional watcher stores only hashes and delivery status for deduplication. Temporary keys/files are deleted after verification. The app never asks users for private GPG keys.

**Important:** This is a community project by **Natsai**, not an official Monad Foundation verifier. A hosted verification result is an assertion by **the hosting operator**. Open source makes the verifier auditable, not trustless. For critical action, run it yourself or independently verify locally using [Monad's instructions](https://github.com/monad-crypto/mf-nodeops-comms).

**Scope:** public GitHub announcements only. Restricted email-only emergency messages are not covered. Automatic alerts require deploying the separate optional watcher.

## Tests

Install `gpg`, then:

```bash
python -m unittest discover -s tests -v
```

Tests generate temporary GPG signing keys and local signed fixtures; no network access is needed. GitHub Actions runs them on pull requests and pushes. The app still needs a live end-to-end verification on the deployed host, since CI does not fetch Monad's repository.

## License

MIT — © 2026 Natsai OÜ.
