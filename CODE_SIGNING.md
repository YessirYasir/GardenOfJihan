# Code signing policy

Garden of Jihan is an MIT-licensed open-source Windows application maintained in the public `YessirYasir/GardenOfJihan` repository.

## Goal

Public Windows releases should be traceable to this repository, built by the repository's automated GitHub Actions pipeline, scanned before publication, and signed with a trusted code-signing certificate when the open-source signing application is approved.

## Planned open-source signing

Garden of Jihan intends to apply for free open-source code signing through SignPath Foundation.

Required acknowledgement once approved:

> Free code signing provided by SignPath.io, certificate by SignPath Foundation.

Until trusted signing is active, the project will not describe unsigned binaries as signed or as guaranteed to bypass Windows SmartScreen.

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
9. Be manually approved for trusted code signing when SignPath signing is available.

## Privacy

See [`PRIVACY.md`](PRIVACY.md).

Garden of Jihan does not transfer usage analytics, crash telemetry, transcripts, generated clips, or local-file names to the project maintainer by default. Network requests occur only for user-requested remote media, local-model/reference downloads, or explicit platform integrations. Garden of Jihan does not claim anonymity from third-party services the user chooses to access.

## System changes

The portable Windows build does not require administrator privileges and does not silently modify Windows security settings, firewall configuration, Defender exclusions, browser settings, or trusted certificate stores.

## Uninstallation

The portable release does not install system services. To remove it, close Garden of Jihan and delete the extracted application folder. User-created clips remain wherever the user saved them. Cached application data may be removed separately from the user's GardenOfJihan application-data directory.
