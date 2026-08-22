# Forge One public release checklist

Forge One is local-first software. A public GitHub repository publishes the
source code; it does not turn a personal Windows PC into a permanent hosting
service.

## Safe to publish

- application source under `backend/`, `frontend/src/`, and `scripts/`
- setup and run scripts
- dependency manifests and third-party notices
- documentation

## Never publish

- `.venv*` folders
- `models/` and `third_party/` downloads
- `data/forge-one.sqlite3`
- `uploads/`, `outputs/`, or `logs/`
- access tokens, cookies, passwords, private Cloudflare credentials, or `.env`

The repository `.gitignore` excludes these paths. Before every public push,
run `git status --short` and confirm none of them are staged.

## Public tunnel warning

`trycloudflare.com` Quick Tunnel URLs are temporary. They can change whenever
the tunnel restarts and should not be treated as a permanent production URL.
When sharing a tunnel from a personal PC, set both:

```text
FORGE_PUBLIC_MODE=1
FORGE_ACCESS_TOKEN=<long random secret>
```

Visitors first open `/access?token=<the same secret>`. Public mode also applies
an in-memory, per-IP generation limit. For a permanent public service, use a
dedicated machine, a named Cloudflare Tunnel and domain, HTTPS, backups, disk
quotas, monitoring, and a deliberate privacy policy.

## Licensing

Do not make the repository public until the repository itself has a chosen
license and every bundled model/dependency permits redistribution. Forge One
currently preserves third-party notices, but downloaded model weights are not
committed and may have their own terms.
