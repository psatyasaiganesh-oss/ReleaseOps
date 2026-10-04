# Interview walkthrough

## Five-minute demonstration

1. Explain the business requirement: make releases repeatable and failures recoverable, with clear support handoffs.
2. Start the app and observer. Create a deployment task and move it across the Kanban board. Report an incident, investigate, and resolve it.
3. Show the pipeline: checks, image publication, manual environment selection, environment protection, and a digest-based deployment.
4. Run the local rehearsal. Explain why liveness can pass while readiness fails, how downtime observations survive in a spool, and why rollback preserves the database.
5. Show the Docker deployment script, image state files, a backup, and the incident/restore runbook. State which parts you personally ran and which remain templates.

## Questions to prepare for

- Why separate build/test/publish/deploy? A failed check blocks later jobs; publishing does not immediately change the running environment.
- Why an immutable image digest? A digest identifies the exact image bytes; tags can be reassigned.
- What happens on a failed first release? No previous image exists, so the script stops the failed initial application and returns an error.
- Is rollback zero downtime? No. This is a single-host replacement strategy. A load balancer and separate candidate capacity would be needed for a more available strategy.
- Does rollback restore data? No. It restores an image while keeping the database. Incompatible schema migrations require a separate recovery plan.
- Why SQLite WAL/online backup? Separate connections support concurrent requests; the online backup API includes committed WAL writes consistently.
- Is 99.9% a demonstrated SLA? No. It is a learning target and sampled readiness success. Observation coverage, monitoring interval, downtime, and a contractual measurement method matter.
- Why does the monitor keep a spool? The application may be unreachable exactly when a failure occurs. The observer stores those checks locally and uploads them after recovery.
- Why are production approvals a setting? The workflow references an environment, but repository environment policies enforce the review gate.
- How would you improve it? Add individual identities, a supported production HTTP stack, TLS, migration tooling, off-host backups, alerting, deployment promotion, and stronger availability.

## Resume wording after you run and understand it

**ReleaseOps — CI/CD and application deployment lab**

Built a Python/SQLite release and incident dashboard with a GitHub Actions pipeline, Docker deployment automation, readiness checks, rollback procedures, external health observations, and operational runbooks.

Use only the parts you have actually run and can explain. Mention an AWS deployment only after provisioning and testing it in your own account. This project does not establish client production experience, commercial SLA ownership, or measured delivery improvements.
