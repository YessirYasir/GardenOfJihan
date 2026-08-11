# Security Policy

Garden of Jihan processes untrusted media and URLs, so security boundaries are part of the product architecture.

## Reporting a vulnerability

Please do not publish a working exploit in a public issue. Use GitHub private vulnerability reporting when enabled for this repository. If private reporting is not available, open an issue that contains **no exploit details** and request a private contact channel.

## Security guarantees we do not make

No software is “unhackable” or “non-traceable.” Garden of Jihan instead aims to minimize attack surface, avoid telemetry, keep processing local, and fail safely.

## Current protections

- Server binds to loopback only.
- Host header is restricted to localhost / 127.0.0.1.
- State-changing API calls require a random per-launch token.
- Browser Origin must match the local application origin.
- Remote media URLs are parsed and allowlisted by provider.
- Credentials in URLs, arbitrary ports, IP-literal hosts, and unsupported schemes are rejected.
- Jobs live inside UUID-named directories and are path-contained.
- FFmpeg/ffprobe are called with argument arrays and `shell=False`.
- Uploads are streamed and bounded.
- Video duration is capped at two hours by default.
- Security response headers include CSP, frame denial, no-sniff, no-referrer, and restrictive permissions policy.
- No analytics or telemetry are included by default.

## Release policy

Before a stable release, CI should pass unit tests, Ruff, Bandit, pip-audit, and CodeQL. Windows artifacts should be built only from tagged commits through GitHub Actions.
