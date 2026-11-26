# Security contract changes, 24 October 2026

Deploy the updated clients with this backend. Pre-update staff tokens from before the session migration are rejected.

## Security audit follow-up, 23 November 2026

- Staff startup no longer creates demo accounts. It revokes existing sessions while an account still has a legacy demo password. Set `EMR_BOOTSTRAP_ADMIN_PASSWORD` to a unique password of 16–72 UTF-8 bytes to provision a new admin or replace an existing demo admin password. Once provisioned, remove this variable from the deployment environment. Other demo accounts require a password reset through an administrator.
- Patient OTPs always go through the configured provider. Phone formats share one cooldown and verification record. The first OTP issued under the new code is required for patients whose previous in-flight OTP was stored under a noncanonical number. A staff edit to a patient's registered phone invalidates access from a patient token issued for another number.
- The updated patient app revokes its current token on sign-out when the server is reachable. Apply the revocation-table migration before serving patient requests with this backend.
- Deploy the web frontend with the backend for staff messaging. Its WebSocket passes authentication in the handshake header. Configure any upstream proxies to redact the signed media URL paths in their logs.
- Patient and authenticated API responses are marked `no-store`. Provider logs omit response bodies, patient identifiers, and device token fragments. Document uploads must identify the correct patient and match their declared type. Linked vitals and mobile invoice cancellation enforce patient ownership.
- The local EMR database and patient-app environment file are ignored by Git. Their working copies remain available. Check prior repository history and existing production logs under your data-retention and credential-rotation procedures.

## Authentication

- Login rejects disabled accounts with HTTP 401 and creates a revocable session with a seven-day absolute deadline.
- `POST /api/auth/refresh` accepts only refresh tokens, rotates them once and never extends the absolute session deadline. Reusing an old refresh token returns 401 and revokes that session, including its access tokens.
- Shared HTTP/WebSocket authentication accepts only access tokens linked to an active, unexpired session and active account. Changed password hashes invalidate issued tokens.
- Disabling an account or updating its password through the user-management API revokes its sessions. WebSocket messages check session validity before delivery; idle connections revalidate every 15 seconds.
- API clients must serialize refresh requests. The included native and web clients do this; the web client also uses Web Locks across tabs on supported secure origins.

## Clinic and uploads

- Clinic responses retain public profile fields and `is_messaging_authenticated`; `notification_settings.messaging_api_key` is never serialized. Only the messaging authentication flow sets the server's provider key.
- Mutation request bodies are limited to 6 MiB and 30 seconds before parsing. Individual document/signature/logo reads are capped at 5 MiB plus one byte for overflow detection. Logos require PNG/JPEG extension, MIME and content signatures.
- Media URLs require signed, expiring media-purpose tokens and resolve only within the PDF directory.

## Runtime

Install the complete `requirements.lock` runtime, including PyJWT instead of python-jose. The `auth_sessions` table is registered with the existing startup metadata creation; do not bypass that startup bootstrap on a deployment without first creating the new table.

The image runs as UID/GID 10001:10001. Host-mounted upload directories must be writable by it. Redis no longer publishes a host port. The Compose backend port defaults to loopback; set `EMR_BACKEND_BIND_IP` explicitly for trusted private-LAN native demos, or use the web proxy.
