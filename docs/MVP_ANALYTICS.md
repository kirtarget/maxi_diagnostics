# MVP analytics contract

Product events use the existing `diagnostic_funnel_events` table. Each row contains
an installation-specific HMAC subject identifier and a server timestamp. Answers,
names, Telegram identifiers and notification text are not copied into this table.
The optional external webhook remains independent and does not send user identifiers.

The admin funnel API includes `events`, with event and unique-user counts by action.
Existing `opened`, `started`, `completed`, `result_viewed`, `trainer_answered` and
`offer_clicked` aggregates remain available.

| Event | Observed boundary |
| --- | --- |
| registration_started / registration_completed | First authenticated Mini App bootstrap. Both represent the same boundary, not a registration conversion funnel. |
| onboarding_started | First persisted transition from welcome to selection. |
| onboarding_completed | First diagnostic completion recorded after instrumentation. |
| diagnostic_started / diagnostic_completed | Persisted diagnostic transitions. |
| question_answered | First structurally complete saved answer per attempt and question, or an accepted trainer answer. Answer corrections do not add events. |
| diagnostic_abandoned | Inferred after 24 hours without saved progress while still in progress. Timestamp is detection time. Returning later does not remove the event. |
| result_viewed | Existing explicit result-view action. |
| daily_started / daily_completed | Starting a plan and finishing its trainer session. |
| life_lost | Accepted trainer answer with a negative life delta. |
| streak_updated | Qualifying gameplay activity, once per school-local day. |
| notification_sent | Confirmed reminder delivery. PDF delivery remains in the existing delivery analytics. |
| notification_opened | Authenticated bootstrap with a signed link token for the user's delivered reminder, once per reminder cycle. |
| user_returned | Subsequent authenticated bootstrap, at most once per UTC day. Includes same-day returns. |

Reminder Mini App links carry an `n` query token. The client forwards it as
`notification_token` during bootstrap. The server verifies the HMAC bound to the
authenticated recipient, notification ID and scheduled delivery timestamp, then
checks ownership and delivered state. This measures clicking the Mini App link,
not reading the Telegram message. Bot callback buttons are outside this metric.
Reopening the same link is deduplicated. A lives reminder rearmed for a newer cycle
invalidates attribution from the previous cycle's link.

Events are best effort after the product transaction. Unique subject, action and
dedupe-hash keys prevent duplicate question, daily-start, activity and reminder
events on retries. A process failure between saving product state and writing an
event can lose analytics. Product answers and results are not affected. This is
not an accounting ledger and cannot support exact delivery or billing totals.

No historical backfill is performed. Legacy users' first observed completion can
appear as onboarding completion. Compare cohorts only after instrumentation starts.
Retention in the existing report uses any observed active day, not registration
cohorts. Funnel events are retained for 90 days.
