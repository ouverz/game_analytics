# Technical Launch: Product Brief

## Recommendation

Continue the controlled technical launch, but treat loading performance and the
two failure points before game entry as release risks. The funnel successfully
reaches the game in **577 of 621 observed launch sessions (92.9%)**. That is a
solid completion rate, but successful players wait **105.4 seconds at the
median** and **156.2 seconds at the 90th percentile**. Broadening the launch
before improving that experience would expose more players to a slow first
impression and make the remaining 7.1% loss more expensive.

## What the launch data says

| Measure | Result | Interpretation |
| --- | ---: | --- |
| Launch sessions started | 621 | Denominator for the sequential loading funnel |
| Sessions reaching the game | 577 | 44 starts did not reach game entry in sequence |
| Start-to-game conversion | 92.9% | Most attempts succeed, but 7.1% are lost |
| Median loading time | 105.4 sec | A typical successful load takes about 1m 45s |
| P90 loading time | 156.2 sec | One in ten measured loads takes over 2m 36s |
| Timing-eligible sessions | 556 | Complete sessions with coherent timestamp order |

The funnel is stable through configuration, localization, and the maintenance
check. The largest loss occurs before data loading starts: **32 sessions (5.2%
of starts)** disappear between the maintenance check and data-load start. A
further **11 sessions (1.9% of those starting data load)** do not complete data
loading. Only one additional session is lost between data-load completion and
login; every sequentially completed login reaches the game.

## Focused FTUE scorecard

The telemetry does not contain explicit tutorial events, so the most defensible
FTUE story is whether a new player enters the game, reaches the first observable
core action, reaches it quickly, and returns the next day.

| FTUE KPI | Result | Interpretation |
| --- | ---: | --- |
| First-session game-entry rate | 86/101 (85.1%) | About one in seven new players does not enter the game successfully on the first observed attempt |
| First-session activation rate | 43/101 (42.6%) | Fewer than half of new players start a battle after entering the game in their first session |
| Activation among game entrants | 43/86 (50.0%) | Half of successful first-session entrants reach the selected core-loop milestone |
| Time to first core action | Median 10.1 min; P90 23.0 min | The path from launch to the first battle is long even for activated players (n=43) |
| D1 retention | 45/93 (48.4%) | Just under half of eligible installs start the client on the exact next UTC calendar day; the dashboard also breaks this out by platform and client version |

These measures reveal a sharper first-time experience than the all-session
technical funnel alone. Later attempts lift session-level game-entry conversion
to 92.9%, but only 85.1% of new players succeed on their first observed launch.
Of those first-session entrants, half reach a battle. The 10.1-minute median
time from launch to that first battle combines technical loading with the
post-entry path and should be treated as a time-to-value baseline, not solely as
a loading-performance measure. D1 retention is an early benchmark; this sample
is too small and short to attribute it to any individual FTUE step.

The conditional events explain where investigation should begin:

- Maintenance blocking appears in 11 sessions; none later reach the game in
  that session.
- Data-load failure appears in 10 sessions; none later reach the game.
- Patch failure appears in 3 sessions; none later reach the game.
- Patch decline is not always terminal: 8 of 16 affected sessions continue to
  game entry. It should not be represented as a mandatory funnel step.
- Privacy decline (63 sessions) and iOS tracking denial (54 sessions) do not
  prevent game entry in this sample; all affected sessions continue.

Platform/version results are directional rather than release gates because the
samples are small. Android 1.0.2 has the strongest observed result: **201 of
211 sessions convert (95.3%)**, with a 95.7-second median load. The three iOS
groups range from 23 to 75 starts and convert at 82.6%–91.0%. Later Android
versions also have slower observed upper-tail loads than 1.0.2. These patterns
justify investigation, but the data cannot separate version effects from
device, network, geography, or player-mix differences.

## Dashboard coverage and future work

The submitted dashboards are sufficient to explain the supplied snapshot without
introducing unsupported metrics. The loading dashboard shows the sequential
funnel, an ordered vertical view of conversion from the first step, drop-off
volume, conditional outcomes, and platform/version context. The separate FTUE
dashboard keeps player entry, activation, time to value, and D1 retention distinct
from technical attempt-level performance.

It is not intended to be a complete production-monitoring system. The highest
value follow-up work is:

1. Add daily and release-level conversion and loading-time trends so regressions
   can be separated from persistent behaviour.
2. Calculate governed median and P90 elapsed time between funnel steps to locate
   where launch time is spent.
3. Measure successful subsequent attempts following a failed or abandoned
   launch, in addition to same-session continuation.
4. Add date, cohort, country, and acquisition-source cuts with minimum sample
   thresholds before drawing segment conclusions.
5. Extend telemetry for crash-free launch, network conditions, device/OS,
   explicit abandonment reasons, and tutorial progression.

These additions require either a new analytical grain or additional telemetry
and are therefore deliberately deferred rather than recreated inside Superset.

## Recommended next actions

1. **Instrument and investigate the pre-data-load loss.** Add or validate a
   terminal reason for every session that passes maintenance but never starts
   data loading. Break out maintenance state, patch offer/decision, patch
   download result, and client exit so the 32-session loss becomes actionable.
2. **Prioritize data-load reliability.** Trace the 10 explicit failures by
   error code, asset/config version, device, and network; alert on failure rate
   and verify that retry behavior is visible.
3. **Set a loading-time launch guardrail.** Track median and P90 daily by
   platform/version, with a target agreed by Product and Engineering. The
   current 105-second median and 156-second P90 should be improved before a
   broad public release.
4. **Keep consent outcomes out of the core conversion funnel.** Monitor them
   with conditional denominators for privacy/compliance decisions, but do not
   count a decline or denial as loading abandonment when the player continues.
5. **Add explicit FTUE instrumentation before optimizing the tutorial.** Record
   tutorial start, step, completion, failure/retry, skip, and a stable milestone
   identifier. The current events can establish entry and first-battle
   activation, but they cannot explain what happens between those points.

## Definitions and limitations

- The primary metric is **session attempts**, not unique players. This measures
  the reliability of each loading attempt; repeated attempts by one player can
  therefore contribute more than once.
- FTUE rates use one row per install/player. The first session is the session
  containing that player's earliest eligible `INIT_CLIENT_START`.
- `BATTLE_STARTED` is the activation milestone because it is the clearest
  available entry into the core gameplay loop. It counts only after sequential
  game entry in the same first session.
- D1 retention requires an eligible `INIT_CLIENT_START` on the exact UTC
  calendar day after install and excludes installs whose D1 is not fully
  observable in the data window.
- The sequential funnel ends at `INIT_GAME_JOINED`. A step counts only if it
  occurs at or after the preceding required step in the same user/session.
- Patch, privacy, and Apple tracking events are conditional branches. Their
  continuation rate is the share with a later game-joined event in the same
  session.
- Loading time runs from client start to game joined. Twenty-one completed
  sessions with a source-order timestamp reversal are excluded, leaving 556
  timing-eligible sessions.
- The source contains 18,479 physical event rows. Metrics use 18,400 rows after
  excluding 3 malformed rows, 70 later exact-duplicate copies, and 6 events
  outside the stated 14-day window.
- This is a small, two-week client-telemetry sample with 101 install records.
  One event user has no install record and one has conflicting install/event
  platform data; affected sessions are excluded from platform/version cuts.
- Client event absence does not prove that a player abandoned or that a backend
  operation failed. Server-side outcome/error telemetry is needed for causal
  diagnosis and revenue-grade reporting.
- Tutorial start/completion, early difficulty or retries, progression state,
  authoritative session duration, and crash-free onboarding cannot be
  calculated because the required events or fields are absent. D3 and D7 are
  deferred because the mature cohorts are smaller and unstable in this sample.

All headline, funnel, conditional-outcome, platform/version, and FTUE figures
were recalculated directly from the raw files by `src/reconcile_metrics.py`.
The dashboard figures match the dbt marts, and the FTUE numerators and timing
statistics match the separate direct SQL cross-check.
