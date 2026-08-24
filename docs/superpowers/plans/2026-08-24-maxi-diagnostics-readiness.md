# MAXIMUM Diagnostics Readiness Plan

## Goal

Prepare the current MAXIMUM Diagnostics working tree for a verified release at
`maxi.kirtarget.ru` and for owner-operated recovery.

## Constraints

- Preserve UTF-8 text and never expose server-only answers or secrets.
- Keep source assets separate from generated test and browser artifacts.
- Do not deploy, modify DNS, change TLS, or update BotFather without a final
  explicit production confirmation.

## Tasks

1. Classify the untracked tree. Keep release source files and remove only
   owner-approved generated logs, reports, temporary test directories, and
   local archives.
2. Review and verify the current release candidate. Commit only the intended
   source, tests, content, licenses, and documentation.
3. Make every tracked configuration and deployment document use
   `maxi.kirtarget.ru`. Verify the production Compose and Nginx configuration
   without applying it to infrastructure.
4. Verify owner-operated readiness through the applicable local operational
   checks, document the remaining external release gate, and update Linear.

## Verification

- `python scripts/validate_school.py`
- `python scripts/check_brand_isolation.py --history`
- `python -m pytest -q`
- `npm run test:unit`, `npm run build`, and `npm test` in `miniapp`
- `docker compose config --quiet`

## External Release Gate

After all local checks pass, obtain a final confirmation immediately before
changing production services, DNS, TLS, or BotFather settings.
