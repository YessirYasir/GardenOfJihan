# Privacy

Garden of Jihan is local-first.

By default the application does not send usage analytics, crash telemetry, transcripts, generated clips, or local-file names to the project maintainers.

Network access happens only when a user asks the application to acquire remote media, verify/update optional reference data, or connect an official publishing account. Platform services can still observe traffic that is sent to them; the application does not claim anonymity or “non-traceability.”

Completed analyses can be resumed from a versioned project manifest stored beside the isolated local source under the GardenOfJihan app-data directory. The manifest contains transcript segments and local acoustic word timestamps, ranking results, local signal summaries, clip selections, timing edits, and export preferences. It is not synchronized or uploaded. Saved projects remain until the user removes them in the local project library; incomplete temporary jobs are eligible for retention cleanup.

Official publishing is opt-in. When the user explicitly starts a YouTube upload, the chosen exported MP4, title, description, privacy setting, audience designation, and synthetic-media disclosure are sent to Google's official OAuth and YouTube Data API endpoints. OAuth client and token material is encrypted for the current Windows user with DPAPI and is never written to the repository. TikTok Direct Post is disabled until an audited supported integration exists.

Publishing integrations must use official OAuth flows. Account passwords must never be collected by Garden of Jihan.
