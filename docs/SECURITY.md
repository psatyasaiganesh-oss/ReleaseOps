# Security decisions and operating limits

- Writes require an environment-specific bearer token of at least 24 characters; generated tokens use Python `secrets`. Tokens are ignored by Git and not logged.
- Read endpoints expose the workspace inside a private lab. There are no individual user accounts, roles, permissions, session cookies, or audit-grade identity claims. All token holders have equal write access.
- Browser tokens live only in memory. Cross-origin writes are rejected; the application does not enable CORS. Dynamic user content uses text nodes.
- Static serving has a fixed allowlist. Database, token, and repository files are outside it. CSP, nosniff, no-referrer, no-store, and anti-framing policy are included.
- SQLite statements use parameters for user values. Table/field identifiers come from fixed application choices. Bodies, text inputs, metrics labels, and probe batches have bounds.
- Containers run as UID/GID 10001 with dropped capabilities, a read-only root filesystem, resource limits, and persistent application data. Ports bind to loopback by default.
- AWS permits SSH only from a supplied trusted IPv4 CIDR, encrypts the root disk, and requires IMDSv2. Terraform does not contain credentials or private keys.
- A GitHub deployment runner has Docker/host access. Restrict it to your trusted private repository and deployment jobs. Environment protection rules must be configured in GitHub; a YAML `environment` field alone does not enforce reviewers.
- Image publication uses job-scoped permissions. Docker login/build actions are pinned to SHAs from GitHub’s official publishing example; other actions use supported major tags. Review and update action pins/base-image digests before adapting this lab for regulated or long-lived production use.

The standard-library HTTP server is for this learning lab and must remain private. It is not a hardened public production serving stack. No TLS endpoint, rate limiter, per-user identity, comprehensive vulnerability scanner, automatic alerts, high availability, or distributed database is included. A shared token can submit release/observation records, so those records require operator trust. Production-labeled environments do not create enterprise production readiness by themselves.
