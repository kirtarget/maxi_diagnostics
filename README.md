# MAXIMUM Education diagnostic bot

This repository is configured for MAXIMUM Education. It contains the school catalog,
brand, domain, and public links for `maxi.kirtarget.ru`.

## Deployment setup

1. Clone a clean reviewed revision of this repository.
2. Do not run `scripts/init_school.py` in this repository. It initializes a pristine
   white-label template. This configured archive would refuse the operation without
   `--force`. Do not use `--force` to repurpose live MAXIMUM public configuration.
3. Create a Python 3.11 environment and install the tooling:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --no-deps -r requirements-dev-lock.txt
   ```

   ```sh
   python3.11 -m venv .venv
   .venv/bin/python -m pip install --no-deps -r requirements-dev-lock.txt
   ```

   `requirements.txt` and `requirements-dev.txt` are the reviewed direct inputs
   used when deliberately regenerating the complete lock files; normal setup,
   CI, and container builds install only from the lock files.

4. Review `school/brand.json` and `school/links.json`. Add or replace files in
   `school/diagnostics/` and `school/assets/`. Content schemas are documented in
   [docs/CONTENT_FORMAT.md](docs/CONTENT_FORMAT.md).
5. Validate content and isolation before adding secrets. Run
   `scripts/validate_school.py` followed by `scripts/check_brand_isolation.py`:

   ```powershell
   .\.venv\Scripts\python.exe scripts\validate_school.py
   .\.venv\Scripts\python.exe scripts\check_brand_isolation.py
   ```

   Use `.venv/bin/python` for the same commands on Linux or macOS.
6. Copy `.env.example` to `.env`. Replace the all-zero `INSTALLATION_ID` with a new
   UUID. Generate unique database and admin passwords and fill every required blank.
   Do not commit `.env`.
7. Create a school-owned bot in **BotFather**, connect the verified HTTPS **domain**
   as its Mini App URL, and place the bot token only in `.env`.
8. Start the installation from the repository root:

   ```text
   docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml up -d --build
   ```

Next, follow [deployment](docs/DEPLOYMENT.md), [operations](docs/OPERATIONS.md), and
[handoff](docs/HANDOFF.md). The admin page is `/admin/diagnostics` and uses the Basic
credentials stored only in `.env`.

## Creating a separate white-label repository

For another school, select **Use this template** in the Git host and create a new
private repository. Run `scripts/init_school.py` once with that school's public
values only while the new repository still has pristine template configuration. Do
not use `--force` against an existing school repository. The initializer rewrites
public brand, links, and `.env.example` configuration.
