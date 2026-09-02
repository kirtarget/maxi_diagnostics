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

`LOG_LEVEL` sets the root log level for both the API and the bot, default `INFO`.
Accepted values are `CRITICAL`, `ERROR`, `WARNING`, `INFO` and `DEBUG`. Uvicorn keeps
its own access log configuration. Raise the level only for a bounded investigation;
`DEBUG` increases log volume and rotation pressure.

## Operator alerts

Set `ALERT_CHAT_ID` to a Telegram chat id to receive alerts from the bot process.
An empty value disables alerting, which is the default. Use a private operator chat:
anyone in that chat sees the alerts.

Alerts are sent for four conditions.

- `pdf_abandoned` - a report was abandoned after eight delivery attempts.
- `followup_abandoned` - a follow-up was abandoned after eight attempts.
- `worker_tick_failed` - the one-minute worker tick raised an unhandled exception.
- `pdf_queue_backlog` - more than 50 reports were waiting at the start of a tick.

A message carries the kind, counts, and the attempt or notification id already visible
in the protected admin lists. It never carries `initData`, Telegram profile data,
answers, payloads, or a stack trace with values. Only the exception type and message
are reported for a failed tick.

Dedupe is in-memory inside the bot process: at most one message per kind per hour.
Restarting the bot clears that window. Alerting is best effort, so a failed send is
logged and dropped rather than retried. Treat the admin issue lists and `/healthz` as
the authoritative state, and the alert as a prompt to look.

## Funnel

The protected `/admin/funnel` page shows how many students opened the Mini App,
started, completed, viewed their result, came back, answered in the trainer, and
clicked an offer. Both a 7 and a 30 day window are shown with conversion percentages,
plus a breakdown by exam and subject.

Counts are unique students per step, identified by the same installation-local
pseudonymous subject hash the offer events use. No Telegram identifier, name, answer,
or payload is stored. Days are counted in UTC. "Next day" means any event on the day
after a day with activity; "returned within a week" means any event two to seven days
after such a day. Events are purged after 90 days by the same worker step as the offer
events, and user erasure removes that subject's rows.

Recording is best effort. A failed write is logged and never affects the student's
request, so treat small gaps as expected and do not reconcile the funnel against
attempt counts.

## Update

1. Create a backup with the platform-specific command in the next section.
2. Fetch the reviewed revision as described in the deployment guide's
   "Updating a running installation" section and confirm CI is green for it.
3. Run the production Compose pair with `up -d --build`, then check its status with
   `ps`.
4. Check API health, Mini App load, admin authentication, and bot commands.

## Question authoring

The protected `/admin/content` page stores private authoring drafts in PostgreSQL.
Saving a draft does not change the catalog used by the API or bot. Correct answers,
explanations, and other private authoring fields remain confined to authenticated
admin responses and the database backup.

Use this publication sequence:

1. Open an existing question or add a numeric question inside the required
   diagnostic.
2. Save the draft. If another editor changed the same diagnostic, reload after the
   revision-conflict warning and reconcile the changes.
3. Run **Проверить диагностику**. The server validates the complete catalog, including
   the global question and payload limits.
4. Download the UTF-8 JSON file. It has no byte-order mark.
5. Replace the matching file under `school/diagnostics/` in a reviewed Git change.
6. Run `python scripts/validate_school.py` and
   `python scripts/check_brand_isolation.py`, followed by the affected tests.
7. Publish only through the normal image build and deployment procedure above.

Do not copy admin API responses, draft rows, database dumps, or exported files into
public tickets. The audit table stores actions, actor names, revisions, and hashes,
but does not store a second copy of question content. New image assets cannot be
uploaded through this first version of the editor. Add reviewed assets through Git
and the existing content validation workflow.

## Backup and guarded restore

The backup script writes a binary custom archive plus `.sha256` and
`.manifest.json` sidecars beneath repository `backups/`. Keep all three files
together in protected off-server storage and test a restore drill regularly.
Local automated checks prove the scripts' guarded workflow, not that protected
storage is reachable or that an off-server archive restores in the receiving
school's environment. The school operator must perform and record that drill in
an approved maintenance window.

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

Offer telemetry is a bounded, best-effort internal signal. The Mini App sends only a
client event identifier, a configured placement, an offer identifier, and one of
`impression`, `click`, or `dismiss`. The API validates the offer against the current
`school/links.json`, timestamps the event on the server, and never stores `initData`,
Telegram profile data, URLs, answers, correct answers, reports, or arbitrary metadata.
Event identifiers are idempotent. Reusing one with different content is rejected.
Events are rate-limited per installation-local pseudonymous subject and purged after
90 days. User erasure removes events for that subject hash in the same transaction.
Delivery is best effort and no business decision may depend on an event arriving.
