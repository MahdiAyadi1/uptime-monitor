# Project decisions and trade-offs

## Local runtime choice

This project keeps the application logic framework-independent and the runtime container intentionally thin. The container image installs the project package and runs only the Python entrypoints defined in the project config, keeping the database model, probe logic, and API responsibilities separate.

## DB and migration approach

PostgreSQL is used for the app state because the project expects a durable, multi-process production-like environment with advisory locking and predictable SQL semantics. Alembic is kept as an explicit migration step instead of running automatically on app boot so schema changes remain reviewable and CI can validate them before deployment.

## Alerting and incidents

Alerts are sent only on transitions (open or resolve) rather than on every failed probe. This keeps the monitoring signal meaningful and avoids noisy webhook spam while preserving the project’s auditability for incident review.

## Security notes

All URL validation is performed server-side before a probe is attempted. That protects the local portfolio app from SSRF-prone targets while keeping the scope of the project limited to the monitor service itself.
