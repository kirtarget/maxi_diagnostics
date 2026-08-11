# School handoff checklist

A handoff is complete only when the school can operate and recover the installation
without a developer-owned account.

- Transfer the private **repository** to the school organization and confirm two
  school administrators can manage it.
- Record ownership of the **domain** and **DNS** account, renewal contacts, and the
  approved recovery path.
- Transfer the **server** or create it directly in the school cloud account. Confirm
  billing, SSH administrators, firewall, monitoring, and certificate renewal.
- Prefer school-owned bot creation in **BotFather**. If an existing bot is involved,
  verify current Telegram transfer capability and policy rather than promising
  transfer. Confirm the school controls the account and recovery method.
- Send tokens, database credentials, the stable `APPLICATION_SECRET`, stable
  `INSTALLATION_ID`, unique `IMAGE_NAMESPACE`, and the admin password only through a
  **protected channel** or secret manager. Never place them in Git or this checklist.
- Preserve `APPLICATION_SECRET` with the installation backup. Do not regenerate it
  during routine deploys: rotation invalidates browser namespaces and resumable progress.
- Preserve `INSTALLATION_ID` with every backup set; changing it prevents the guarded
  restore. Keep `IMAGE_NAMESPACE` unique on the receiving Docker daemon so another
  school or staging installation cannot overwrite its image tags.
- Confirm school staff can sign in to the protected **admin** page and know how to
  rotate both admin and bot credentials.
- Perform a documented **restore drill** from an off-server backup and record its
  date, operator, archive identifier, and result without recording secrets.
- Verify DNS, HTTPS, Mini App, bot, API health, backups, logging, and the one-polling-
  copy rule with the receiving operator.
- After acceptance, **remove developer access** from Git, DNS, server, BotFather,
  monitoring, backup storage, and secret systems unless a separate support agreement
  explicitly requires named least-privilege access.
