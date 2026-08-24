# Operations

## Routine checks and logs

Use the production Compose pair and request `/healthz` through HTTPS:

```sh
docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml ps
docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml logs --since 30m api miniapp bot db
```

Do not paste secrets, raw answers, or Telegram initialization data into tickets.
Compose rotates each service's local JSON logs at 10 MiB and retains five files.
Monitor the database/backup filesystem separately and alert before it fills.

Run exactly **one polling** bot copy for the `maxi.kirtarget.ru` token. Its production
`.env` sets `BOT_POLLING_ENABLED=true`. Before starting or moving the bot, stop the
old polling service and verify it has exited.
If another controlled deployment must remain the single polling owner while this
installation processes its own PDF queue, set `BOT_POLLING_ENABLED=false`. The bot
service then runs only the bounded delivery scheduler and does not call
`getUpdates`. Do not use this mode unless the polling owner points users to this
installation's Mini App.

## Update

1. Create a backup with the platform-specific command in the next section.
2. Fetch the reviewed revision and run the validation/isolation/tests used by CI.
3. Run the production Compose pair with `up -d --build`, then check its status with
   `ps`.
4. Check API health, Mini App load, admin authentication, and bot commands.

## Backup and guarded restore

The backup script writes a binary custom archive plus `.sha256` and
`.manifest.json` sidecars beneath repository `backups/`. Keep all three files
together in protected off-server storage and test a restore drill regularly.

On Windows, the scripts support Windows PowerShell 5.1:

```powershell
powershell -File scripts/backup_db.ps1
powershell -File scripts/restore_db.ps1 -BackupPath .\backups\diagnostic-YYYYMMDD-HHMMSS.dump -ConfirmRestore
```

Linux and macOS require PowerShell 7. Install it through the operating system's
trusted package source, then invoke the same scripts with `pwsh`:

```sh
pwsh -File scripts/backup_db.ps1
pwsh -File scripts/restore_db.ps1 -BackupPath ./backups/diagnostic-YYYYMMDD-HHMMSS.dump -ConfirmRestore
```

Restore is destructive to matching database objects and therefore requires both a
contained archive, matching checksum/database manifest, and the explicit
`-ConfirmRestore` switch. These are verified before the maintenance window. The
script stops only the `api` and `bot` services that were running, then starts only
those services again; API health is awaited before the polling bot. The same
`finally` path performs that recovery after a restore failure. Do not perform a
manual `pg_restore` while application writers are running.

The restore generates a complete schema-reset plus archive SQL script and executes
that script in one transaction, so a failed restore rolls back to the previous schema
and data. It never
deletes the named database volume. Never add the volume-removal flag to the down
command; ordinary maintenance uses `docker compose down`, which preserves the
project volume.

## Rollback and queues

For an application rollback, keep the database volume, check out the last reviewed
revision, rebuild, and re-run health checks. Restore a database backup only when a
schema/data rollback is explicitly required and approved.

The worker retries failed PDF and notification deliveries with persisted leases.
Inspect the protected admin issue lists for `abandoned` work. Correct the underlying
configuration or Telegram problem and keep error details out of user messages.
After eight failures the PDF's delivery-only answers/snapshot are erased; abandonment
is therefore terminal and the learner must retake the diagnostic. Do not reset such a
row to pending or fall back to current catalog content.

Telegram has no idempotency key. Returned message IDs are reconciled and cleaned up
when a database lease is lost, but a timeout after Telegram accepted a send and before
it returned an ID remains an unavoidable bounded at-least-once case. Monitor abandoned
rows and investigate duplicate reports/reminders; automatic retries stop after eight
attempts.

## Retention and backup lifecycle

By default, drafts untouched for 30 days are superseded and their answers erased.
Completed and superseded attempts, unused engagements, and unreferenced report-asset
bundles expire after 365 days. Configure `IN_PROGRESS_RETENTION_DAYS` from 1 to 365
and `DIAGNOSTIC_RETENTION_DAYS` from 31 to 3,650; the latter must remain longer than
the 30-day follow-up window. The worker applies this policy in bounded user batches.

Database dumps retain the data present when they were created even after live-row
purges. Keep backup directories private, copy complete dump/checksum/manifest sets to
protected off-server storage, and delete expired sets according to the school's
approved retention policy. A practical default is 30 daily copies plus 12 monthly
copies, subject to the school's legal and recovery requirements.
