# Technical requirements

## Business problem

A platform support team needs a small internal workspace to see application releases, track deployment tasks, investigate incidents, and verify whether a service is ready. Every release needs repeatable checks and a recovery procedure.

## Users and scope

- Platform specialists define requirements and release readiness.
- Application engineers implement changes and investigate defects.
- Support operators record incidents and follow the operating runbook.
- Readers inspect the workspace; authenticated operators change it.

This single-service lab models one application per environment. It does not connect to a client account or ingest real company production data.

## Acceptance criteria

| ID | Requirement | Observable acceptance criterion |
|---|---|---|
| R1 | Track work | A task has title, owner, priority, and backlog/in-progress/done status; updates persist after restart. |
| R2 | Track incidents | An incident moves from open to investigating to resolved; resolution time is saved. |
| R3 | Trace releases | Successful deployments/rollbacks are recorded with version, image, environment, and timestamp. |
| R4 | Gate releases | A candidate must pass readiness; a failed candidate triggers restoration of the previous image when available. |
| R5 | Separate environments | Staging/production have distinct ports, projects, storage volumes, and operator tokens. |
| R6 | Observe service health | An external process records readiness results and latencies, including unreachable checks spooled during downtime. |
| R7 | Support operations | JSON logs contain request IDs; metrics can be scraped; backups pass SQLite integrity checks. |
| R8 | Control edits | Missing/invalid tokens and cross-origin writes are rejected; secrets are not served as static files. |
| R9 | Automate delivery | Pull requests run checks; main-branch publication follows successful checks; environment deployment is manually selected. |
| R10 | Document recovery | The runbook explains failures, rollback, backup/restore, and escalation. |

## Non-functional decisions

Python 3.12+ has zero external runtime packages. SQLite transactions/WAL preserve committed data across restarts. Input sizes and metrics label cardinality are bounded. Tokens are environment-specific and never committed. UI values use text nodes rather than HTML interpolation. The monitor retains at most 10,000 observations and discards queued observations older than 47 hours to match the API retention window.

Learning SLO: 99.9% successful sampled readiness checks over 24 hours. This is not time-weighted availability, a contractual SLA, or an externally validated production target. Staging and production are environment names in a learning lab.
