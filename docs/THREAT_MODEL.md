# Threat Model

## Assets

- User media and transcripts
- Local filesystem
- Publishing OAuth client and refresh tokens
- CPU/GPU/storage resources
- Integrity of Qur'an and language reference data

## Threats considered

- SSRF / arbitrary URL fetching
- malicious Host/Origin requests against localhost
- CSRF from hostile web pages
- path traversal and malicious filenames
- command injection through media names or URLs
- decompression/media parser abuse
- unbounded files, streams, CPU, memory, or disk use
- poisoned reference datasets
- credential leakage
- dependency compromise

## Controls

- exact-provider host allowlist
- HTTPS-only remote URL policy
- mutation token plus same-origin validation
- UUID job directories and path containment
- streamed upload limits
- ffprobe duration validation
- `subprocess.run([...], shell=False)`
- bounded worker concurrency
- no API secrets in repository or desktop binary
- OAuth loopback state + PKCE, upload-only scope, and Windows DPAPI token encryption
- publishing path containment to rendered MP4 files inside the selected project
- official platform endpoints only; TikTok remains disabled without an audited supported flow
- reference-data hash/version metadata before stable release
- restored Qur'an matches are recomputed from the current verified reference instead of trusted from editable project manifests
- generated ASS caption control codes are constructed internally while transcript/reference text is escaped
- incomplete background renders remain in an unserved staging directory and replace public outputs only after the full export succeeds
- dependency scanning in CI

## Out of scope / not promised

- anonymity from YouTube/TikTok/Instagram
- bypassing platform provenance/originality systems
- making FFmpeg or third-party codecs mathematically exploit-proof
- preventing a user with local administrator access from inspecting their own application files
