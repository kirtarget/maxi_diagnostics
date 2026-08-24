# White-label diagnostic bot starter

This repository packages one independent school diagnostic: a Telegram bot, Mini
App, API/admin service, PostgreSQL database, PDF delivery, and scheduled follow-ups.
Each school operates its own repository, bot, domain, database, and secrets.

## First setup

1. Select **Use this template** in the Git host and create a new **private repository**
   owned by the school. Clone that repository.
2. Create a Python 3.11 environment and install the tooling:

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

3. Run `scripts/init_school.py` once with public brand values only:

   ```powershell
   .\.venv\Scripts\python.exe scripts\init_school.py --name "MAXIMUM Education" --short-name "MAXIMUM" --school-id maximum-diagnostic --domain maxi.kirtarget.ru --bot-username maxi_diagnostics_bot --primary-color "#FF7A00" --accent-color "#D4FF35"
   ```

   ```sh
   .venv/bin/python scripts/init_school.py --name "MAXIMUM Education" --short-name "MAXIMUM" --school-id maximum-diagnostic --domain maxi.kirtarget.ru --bot-username maxi_diagnostics_bot --primary-color "#FF7A00" --accent-color "#D4FF35"
   ```

4. Review `school/brand.json` and `school/links.json`, then replace or add files in
   `school/diagnostics/` and `school/assets/`. Content schemas are documented in
   [docs/CONTENT_FORMAT.md](docs/CONTENT_FORMAT.md).
5. Validate content and isolation before adding secrets. Run
   `scripts/validate_school.py` followed by `scripts/check_brand_isolation.py`:

   ```powershell
   .\.venv\Scripts\python.exe scripts\validate_school.py
   .\.venv\Scripts\python.exe scripts\check_brand_isolation.py
   ```

   Use `.venv/bin/python` for the same commands on Linux or macOS.
6. Copy `.env.example` to `.env`, generate unique database and admin passwords, and
   fill every required blank. Do not commit `.env`.
7. Create a school-owned bot in **BotFather**, connect the verified HTTPS **domain**
   as its Mini App URL, and place the bot token only in `.env`.
8. Start the installation from the repository root:

   ```text
   docker compose -f docker-compose.yml -f deploy/docker-compose.production.yml up -d --build
   ```

Next, follow [deployment](docs/DEPLOYMENT.md), [operations](docs/OPERATIONS.md), and
[handoff](docs/HANDOFF.md). The admin page is `/admin/diagnostics` and uses the Basic
credentials stored only in `.env`.
