# Deployment

## Prerequisites

- A Linux server with current Docker Engine and the Compose plugin.
- The controlled production domain `maxi.kirtarget.ru`.
- Access to DNS, the school-owned BotFather account, and a protected secret manager.
- Inbound TCP 80 and 443. Database and application ports stay private.

## DNS and HTTPS

Create an `A`/`AAAA` DNS record for `maxi.kirtarget.ru` and wait until it resolves to
the server. Provision an HTTPS certificate with the host's normal ACME client. TLS
provisioning is intentionally provider-neutral; use the school infrastructure
policy and enable renewal monitoring.

Create `/var/www/certbot` for the ACME webroot. Use
`deploy/nginx/maxi.kirtarget.ru.http.conf` only while obtaining the first
certificate. It serves only `/.well-known/acme-challenge/` from that webroot and
redirects every other request to HTTPS. Then install
`deploy/nginx/maxi.kirtarget.ru.conf`, validate with `nginx -t`, and reload Nginx.
The HTTPS file serves only `maxi.kirtarget.ru` and same-origin routes.
`deploy/nginx/diagnostic.conf.example` is the matching single-installation reference
configuration.

- `/` goes to the Mini App at `127.0.0.1:13002`;
- `/api/`, `/admin/`, `/admin/static/`, and `/healthz` go to the API at
  `127.0.0.1:18082`.

Do not publish either loopback port or PostgreSQL directly to the internet.
The example allows a classroom-sized burst behind one shared Wi-Fi address, returns
`429` with `Retry-After` above the public API and admin limits, and the Mini App backs
off before retrying. Adjust the documented rates only after measuring real school
traffic; keep the stricter admin limit to slow Basic-auth guessing. It also sends one-year HSTS on the HTTPS
host. Verify TLS and renewal before enabling it in production. The example deliberately
omits `includeSubDomains` and `preload`; add those only when every school subdomain is
permanently HTTPS-ready.

## Environment and containers

This repository already contains MAXIMUM public configuration. Do not run
`scripts/init_school.py` or use `--force` during deployment. Copy `.env.example` to
`.env`, replace the all-zero `INSTALLATION_ID` with a generated UUID, and retain it
across updates and restore drills. Keep `IMAGE_NAMESPACE` Docker-daemon-unique. It
must differ between production, staging, and another school on the same Docker daemon.

Generate the installation UUID with `python -c "import uuid; print(uuid.uuid4())"`.
Generate URL-safe secrets with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`. Use different output
for `POSTGRES_PASSWORD`, `APPLICATION_SECRET`, and `ADMIN_PASSWORD`. Set
`POSTGRES_PASSWORD` and `ADMIN_PASSWORD`,
then set `DATABASE_URL` with the same database/user/password and the Compose host
`db`. Because the generated password is URL-safe, it can be used unchanged in the
database URL. Set `BOT_TOKEN`, the public `MINIAPP_URL`, and exact `MINIAPP_ORIGIN`.
A typical
shape is:

```text
POSTGRES_DB=diagnostic
POSTGRES_USER=diagnostic
POSTGRES_PASSWORD=<generated-secret>
DATABASE_URL=postgresql://diagnostic:<generated-secret>@db:5432/diagnostic
IMAGE_NAMESPACE=maximum-diagnostic
INSTALLATION_ID=<initializer-generated-uuid>
BOT_TOKEN=<BotFather-token>
BOT_POLLING_ENABLED=true
APPLICATION_SECRET=<different-stable-generated-secret>
MINIAPP_URL=https://maxi.kirtarget.ru
MINIAPP_ORIGIN=https://maxi.kirtarget.ru
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<different-generated-secret>
DIAGNOSTIC_RETENTION_DAYS=365
IN_PROGRESS_RETENTION_DAYS=30
```

Keep `.env` mode-restricted and outside Git. Back up `APPLICATION_SECRET` with the
deployment secrets: changing it invalidates browser session namespaces and active
diagnostic content versions. Rotate it only as a planned security operation.
Preserve `INSTALLATION_ID` with backups: restore rejects an archive created by a
different installation even when both use the default database name. Start the stack:

```sh
docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml config --quiet
docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml up -d --build
docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml ps
```

The four services are `db`, `api`, `bot`, and `miniapp`. The API initializes the
idempotent schema after PostgreSQL becomes healthy. Check locally:

```sh
curl --fail http://127.0.0.1:18082/healthz
curl --fail http://127.0.0.1:13002/
```

Then check `https://maxi.kirtarget.ru/healthz` through Nginx.

## Updating a running installation

The production directory `/opt/maxi_diagnostics` is a source snapshot, not a Git
checkout. Never run `git pull` there. Update it from a reviewed commit that has a
green CI run:

1. Create a backup (see operations).
2. On the server, download the commit archive, unpack it into a fresh directory
   and swap it in. Unpacking over the old directory leaves files the release
   deleted in place, and the catalog refuses to start with unreferenced assets:

   ```sh
   SHA=<full-commit-sha>
   cd /root && wget -q "https://github.com/kirtarget/maxi_diagnostics/archive/${SHA}.tar.gz"
   rm -rf /opt/maxi_diagnostics.next && mkdir /opt/maxi_diagnostics.next
   tar -xzf "${SHA}.tar.gz" --strip-components=1 -C /opt/maxi_diagnostics.next
   cp -p /opt/maxi_diagnostics/.env /opt/maxi_diagnostics.next/.env
   mv /opt/maxi_diagnostics /opt/maxi_diagnostics.prev && mv /opt/maxi_diagnostics.next /opt/maxi_diagnostics
   ```

   Remove `/opt/maxi_diagnostics.prev` after the health checks pass.

3. Record the release in `/opt/maxi_diagnostics/.release-revision` with `commit=`,
   `branch=` and `archive_sha256=` lines. The checksum comes from
   `sha256sum "${SHA}.tar.gz"`.
4. Rebuild and restart the production Compose pair:

   ```sh
   cd /opt/maxi_diagnostics
   docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml up -d --build
   ```

5. Check `curl --fail http://127.0.0.1:18082/healthz`, `curl --fail http://127.0.0.1:13002/`,
   then the public `/healthz`, admin sign-in and `/start` in the bot.

Rollback is the same procedure with the previous commit SHA from `.release-revision`.

## BotFather Mini App

Prefer creating the bot from a school-owned BotFather account. Configure the menu
button or Mini App with the exact HTTPS URL from `MINIAPP_URL`. Confirm `/start` and
the Mini App from a separate user account. Telegram must see a valid public
certificate; HTTP and private hosts are not production URLs.
