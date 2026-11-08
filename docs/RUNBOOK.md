# Operations and recovery

API, worker, and inference are separate processes. API/worker must share SUPPORTPILOT_DATA. Check DB health and worker heartbeat before diagnosing queued tickets.

Provider timeout is bounded to <=45 seconds. Each ticket has 2 automatic attempts. Unavailable providers fail visibly; no retrieval fallback is silently presented as generated AI. Correct provider settings before manual retry.

A worker claim has a 60-second lease and unique attempt token. Expired work can be reclaimed. Result registration requires the matching token, running status, and live lease. At-least-once inference is possible; no external action is executed.

Use test_expired_lease_recovers and test_stale_result_cannot_overwrite_review_or_lease for deterministic recovery evidence. The failure test verifies that a bad provider exhausts 2 attempts. Review submits expected_version; concurrent changes return 409.

Approval records a local decision, never an email send. Valid citations do not prove factual support. Review/edit every draft.

SQLite WAL requires a supported local filesystem. Back up and restore-test metadata before real use. Ticket/draft/event retention and alert delivery are not implemented. Suggested production alerts: queue age, stale worker, provider failure/timeout rate, disk exhaustion, and HTTP 5xx.

Release checks: integration tests, retrieval evaluation, JS syntax, image build, and environment-specific smoke tests. Use immutable image tags and an appropriate service database/queue before distributed scaling.
