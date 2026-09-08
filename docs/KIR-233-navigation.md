# KIR-233 navigation contract

Navigation uses one selection shape:

```text
{ exam, diagnosticId, mode }
```

`diagnosticId` is selected before `mode`. The exam tab is the only navigation preference stored in school-scoped local storage. Active answers remain in the existing session-scoped attempt storage.

Trainer navigation has an explicit `{ kind: "trainer" }` pending intent when no subject can be inferred. Selecting a subject consumes that intent and starts the trainer directly, without showing diagnostic format cards.

Format cards use catalog counts. Duration uses the stable estimate `max(5, round(count × 5 / 3))` minutes, so three questions display `~5 мин` and eighteen display `~30 мин`; other catalog sizes remain factual. The adjacent counter shows selected questions out of the full count, such as `3 из 18`.

The home primary action has one precedence order: resumable attempt, ready daily plan, new diagnostic. The submitting surface lasts at least 300 ms. Its warning appears only after that surface remains pending.

The authenticated home/profile/league browser audit still requires real Telegram `initData`. The deterministic unit coverage verifies the controlled navigation, presentation, persistence, and date-format contracts.
