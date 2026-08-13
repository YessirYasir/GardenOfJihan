# Code signing policy

Garden of Jihan is an MIT-licensed open-source Windows and macOS application maintained in the public `YessirYasir/GardenOfJihan` repository.

## Goal

Public Windows releases must be traceable to this repository, built by the repository's automated GitHub Actions pipeline, scanned before publication, and signed with a trusted code-signing certificate. Until trusted signing is available, public Windows publication remains blocked.

## Planned open-source signing

Garden of Jihan intends to apply for free open-source code signing through SignPath Foundation.

Required acknowledgement once approved:

> Free code signing provided by SignPath.io, certificate by SignPath Foundation.

Until trusted signing is active, the project will not publish or recommend an unsigned Windows executable. Unsigned CI artifacts are internal validation outputs only.

## Apple signing and notarization

Public Mac packages must be built on the matching GitHub-hosted Mac architecture, signed with an Apple-issued Developer ID Application certificate using the hardened runtime, submitted successfully with `notarytool`, stapled with the accepted notarization ticket, and accepted by Gatekeeper. The release workflow builds and smokes both Apple Silicon and Intel packages independently.

The Apple certificate, certificate password, signing identity, account identifier, team identifier, and app-specific notarization password are repository secrets. They must never be committed, printed, embedded in an artifact, or exposed to pull-request builds. If any value is unavailable, the public Mac job fails instead of producing a release. Ad-hoc-signed pull-request and manually dispatched artifacts are private validation outputs only and are retained for two days.

## Private portable browser boundary

The temporary private-testing handoff is not a public executable release. It contains no custom `GardenOfJihan.exe`; a plain launcher script starts checksum-pinned official Python binaries whose Authenticode signature must validate to the Python Software Foundation during the build and verification jobs. The complete portable folder is hash-manifested, smoke-tested from the exact ZIP contents, scanned with Microsoft Defender, and retained as a manually dispatched CI artifact for two days only.

This narrow handoff does not weaken the public release rule. It must not be promoted as the final Windows application, uploaded to GitHub Releases, or substituted for Garden of Jihan’s own trusted publisher identity. Public distribution remains blocked until the normal release package passes the existing trusted Authenticode gate.

## Roles

- Committer and reviewer: `YessirYasir`
- Release approver: `YessirYasir`

Repository and signing accounts used for release work must have multi-factor authentication enabled.

## Release requirements

A public executable release must:

1. Be built from the public repository by GitHub-hosted Actions runners.
2. Pass unit tests, compilation checks, Ruff, Bandit, dependency audit, and CodeQL.
3. Build the Windows distributable from version-controlled scripts.
4. Verify the packaged executable, FFmpeg, and ffprobe are present.
5. Launch the packaged executable on a clean GitHub Windows runner and verify both `/api/health` and the browser UI.
6. Run Microsoft Defender Antivirus against the packaged application before publication.
7. Publish a SHA256 checksum for the release ZIP.
8. Generate GitHub build-provenance attestation for the release artifact.
9. Verify a valid trusted Authenticode signature on both the package-directory executable and the exact executable extracted from the release ZIP.
10. Verify that the two signed executables are byte-for-byte identical before publication.
11. Be manually approved for trusted code signing when SignPath signing is available.

A public Mac application release must additionally:

1. Build separate native Apple Silicon and Intel packages on GitHub-hosted Mac runners.
2. Include checksum-pinned FFmpeg and ffprobe binaries for the matching architecture.
3. Include the verified speech, meaning, and complete reviewed Qur'an resources.
4. Pass package integrity, architecture, captions, vertical framing, local UI, Keychain, Qur'an guide, and clean-shutdown smoke tests.
5. Use a valid Developer ID Application signature with hardened runtime and secure timestamp.
6. Pass Apple notarization, ticket stapling validation, and Gatekeeper assessment.
7. Publish SHA-256 checksums and only attach the notarized artifacts to a trusted tagged release.

## Privacy

See [`PRIVACY.md`](PRIVACY.md).

Garden of Jihan does not transfer usage analytics, crash telemetry, transcripts, generated clips, or local-file names to the project maintainer by default. Network requests occur only for user-requested remote media, local-model/reference downloads, or explicit platform integrations. Garden of Jihan does not claim anonymity from third-party services the user chooses to access.

## System changes

The portable Windows and Mac builds do not require administrator privileges and do not silently modify operating-system security settings, firewall configuration, malware-scanner exclusions, browser settings, or trusted certificate stores. On macOS, publishing credentials use the current user's Keychain.

## Uninstallation

The portable release does not install system services. To remove it, close Garden of Jihan and delete the extracted application folder. User-created clips remain wherever the user saved them. Cached application data may be removed separately from the user's GardenOfJihan application-data directory.
