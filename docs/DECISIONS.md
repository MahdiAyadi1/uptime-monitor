# Project decisions and trade-offs

## Local runtime choice

This project keeps the application logic framework-independent and the runtime container intentionally thin. The container image installs the project package and runs only the Python entrypoints defined in the project config, keeping the database model, probe logic, and API responsibilities separate.

## DB and migration approach

PostgreSQL is used for the app state because the project expects a durable, multi-process production-like environment with advisory locking and predictable SQL semantics. Alembic is kept as an explicit migration step instead of running automatically on app boot so schema changes remain reviewable and CI can validate them before deployment.

## Alerting and incidents

Alerts are sent only on transitions (open or resolve) rather than on every failed probe. This keeps the monitoring signal meaningful and avoids noisy webhook spam while preserving the project’s auditability for incident review.

## Security notes

All URL validation is performed server-side before a probe is attempted. That protects the local portfolio app from SSRF-prone targets while keeping the scope of the project limited to the monitor service itself.

## API test isolation

The API CRUD contract tests use a per-test in-memory fake database, so they verify routing, validation, serialization, and authorization without requiring PostgreSQL locally or in CI. Existing persistence/domain tests remain unchanged. This keeps the developer workflow lightweight, with the trade-off that these tests do not verify PostgreSQL-specific persistence behavior; PostgreSQL integration coverage can be added if that becomes a project requirement.

## Probe proxy behavior

The checker's HTTPX client sets `trust_env=False` so `HTTP_PROXY`, `HTTPS_PROXY`, and related environment variables cannot redirect probes through a proxy that bypasses the URL validation boundary. The checker connects directly to targets; deployments that require an outbound proxy would need an explicit, separately reviewed proxy design.

## Structured logging

The API, checker, and retention job emit one-line JSON logs to stdout with a UTC timestamp, level, logger name, message, and event-specific context. Operational events include monitor IDs/names, probe outcome and latency, checker totals, or retention counts. Probe URLs and response/error bodies are excluded to avoid leaking query parameters or remote content into logs.

## M4 manual Azure deployment

The M4 runbook uses Azure Container Registry Tasks to build the current repository context remotely, avoiding a local Docker daemon requirement. A user-assigned identity handles private ACR pulls and reads runtime secrets from Key Vault; the API receives only an application database role and API key. PostgreSQL public networking is allowlisted to the current deployment computer and the Container Apps environment's current outbound IPs. This avoids granting access to all Azure IPs, but Container Apps outbound IPs can change and may require firewall-rule updates. Alembic runs explicitly from the local project virtual environment against the remote Azure database, so no local PostgreSQL server is needed. The API has external ingress restricted to the operator's current public IP; the address must be updated if that IP changes.

## Milestone scope adjustment

M3 is considered complete by the project owner, and work proceeds to M4. TLS expiry checks, webhook delivery, and scheduled retention remain deferred; this intentionally differs from the fixed plan's M3 acceptance criteria.
