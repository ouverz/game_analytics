# Senior AI Data & Analytics Engineer - Take-home Assessment

We expect Part 1 to take 2-3 hours and Part 2 around 1 hour.

---

# Part 1 - Data Analysis

## Scenario

You have just joined the analytics team of a mobile strategy game. The game entered technical launch two weeks ago - a controlled rollout to real players ahead of the full public release.

You have been handed a raw telemetry dump from the first 14 days. Your job: evaluate how the launch is performing and brief the product team.

## Files

- `events.jsonl` - raw client telemetry, 14 days of data
- `funnel_steps.csv` - ordered list of events that make up the technical loading funnel, from first app open to game entry
- `installs.csv` - one row per user: `user_id`, `install_date`, `platform`, `install_source`, `country`

## Deliverables

1. **Technical funnel dashboard** - a visual breakdown of the loading funnel. This is the primary deliverable.
2. **Stakeholder brief** - written summary a product manager can read without running your code. You decide which metrics tell the story of this launch.
3. **Reproducible code** - someone on our team will run it. Include a README with setup instructions.
4. **Methods section** - brief note on: which parts were AI-assisted, what you verified independently, and one decision you deliberately did not delegate to AI and why.

## On AI use

Use AI tools freely - that is the job. The methods section is not a trap. We want to understand how you work, not catch you out.

---

# Part 2 - Data Architecture Proposal

**Length:** 1-2 pages (diagram encouraged)

## Context

We are building the data platform for the game before launch. The following data sources are available:

- **Client-server wire-log** - Continuous gameplay traffic, Protocol Buffer encoded. Assume production volume reaches 1 TB/day. Data lands in Amazon S3.
- **Payment Hub** - Source of truth for revenue (purchase validation, refunds, bookings). Data arrives every 15 minutes or daily. Data lands in Amazon S3.
- **AppsFlyer** - Install attribution, campaign performance, and acquisition data. Data lands in Amazon S3.
- **Firebase** - Mobile analytics and crash reporting. Available via export.

Everything after ingestion - decoding, transformation, storage, serving, and querying - is yours to design.

## Your architecture should support

1. **Governed KPI Dashboards** - Daily refreshed, stakeholder-facing dashboards (e.g. Revenue, Retention, Reg-to-Pay, FTUE funnel) built on consistent, governed metric definitions. How would you make these shareable and accessible across the company? Consider cost, ease of access, and what tradeoffs you are willing to make.
2. **Live Payments Dashboard** - Revenue visible within 15-20 minutes of purchase. Explain how this differs from the daily reporting pipeline.
3. **Plain-Language Queries** - Business users should be able to ask questions in plain language (e.g. "How many battles happened yesterday?") and receive governed, verifiable answers backed by SQL.
4. **Exploratory Analytics** - Support ad-hoc analysis on raw event data (e.g. fraud or exploit detection) while keeping exploratory work separate from the governed reporting layer.
5. **Scalability** - Design for pre-launch, but explain how the architecture evolves as traffic grows to ~1 TB/day, including the trigger points for change.

## Your proposal should cover

- **End-to-end architecture** - Data flow from ingestion to dashboards using concrete technologies.
- **Two-tier architecture** - Separation between governed reporting and exploratory analytics, including their quality guarantees and intended use.
- **Plain-language query layer** - How an AI assistant accesses governed data while ensuring correctness, governance, and SQL traceability.
- **Live payments** - How the near real-time pipeline differs from the daily reporting pipeline.
- **Data quality** - Validation, monitoring, alerting, and handling of data quality issues.
- **Concurrency** - How multiple users query the same data without duplicating pipelines or datasets.
- **Cost considerations** - Main cost drivers, differences between pre-launch and production scale, and what triggers architectural changes.
- **Deliberate scope** - What you would intentionally not build initially, and why.

## Deliverables

A written proposal (1-2 pages) with a diagram showing the end-to-end data flow. The proposal should be readable by both a technical and a non-technical audience. Use concrete technology choices and explain the reasoning behind them.

---

# What we are looking for

We care about:

- **Pipeline thinking** - can you take messy raw data and make it reliably queryable?
- **Analytical judgement** - do you find the right signal in noisy data? Do you notice when something looks wrong?
- **Architecture judgement** - can you make practical trade-offs between simplicity, cost, and capability at different scales?
- **Communication** - can you explain findings and decisions to a non-technical audience?
- **Honest use of AI** - we expect and welcome AI tool use. We want to understand how you use it and where you apply your own judgement.

We are not looking for:

- A perfect answer - there is no single correct solution
- Exhaustive coverage of every metric or every architectural component
- Production-grade code - clarity matters more than optimisation
- The most complex architecture - simpler and well-reasoned beats over-engineered

This exercise is intentionally open-ended. We are evaluating how you think, not whether you arrive at a specific answer.

---

# Submission

A zip or GitHub repo containing: all code, output files, your stakeholder brief, your architecture proposal, and a README with setup instructions so we can run your analysis.
