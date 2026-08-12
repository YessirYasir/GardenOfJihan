# Official publishing boundary

Garden of Jihan never uploads a clip automatically. Rendering stays local; a platform receives an exported MP4 and its chosen metadata only after the user explicitly starts a publish operation.

## YouTube

The implemented YouTube path uses Google's OAuth flow for Windows desktop applications:

- loopback `127.0.0.1` callback;
- PKCE and a short-lived, cryptographically random state value;
- only the `https://www.googleapis.com/auth/youtube.upload` scope;
- offline refresh access, stored with Windows Data Protection API encryption for the current user;
- official `videos.insert` resumable sessions with contiguous 256 KB-aligned chunks;
- an explicit title, privacy choice, made-for-kids designation, and altered/synthetic-media disclosure.

Garden of Jihan does not accept a Google password, API key, service account, copied bearer token, or browser cookie. YouTube does not support service-account authorization for normal channel uploads. The OAuth Desktop client must belong to an approved YouTube Data API project. Google notes that public apps using user-data scopes require verification and that uploads from certain unverified API projects are restricted to private viewing.

Official references:

- [OAuth for mobile and desktop apps](https://developers.google.com/youtube/v3/guides/auth/installed-apps)
- [YouTube resumable upload protocol](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol)
- [`videos.insert` reference](https://developers.google.com/youtube/v3/docs/videos/insert)
- [Google OAuth security best practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices)

The open-source repository and unsigned internal builds do not contain production OAuth credentials. A trusted release still needs a Garden of Jihan OAuth Desktop client owned, configured, and verified by the project maintainer. A developer can install their own Desktop client JSON locally for testing; that file and all encrypted token material remain outside Git.

## TikTok

Direct TikTok posting is deliberately unavailable. TikTok's Content Posting API requires a registered app, appropriate scopes, creator information checks, and an audit before unrestricted Direct Post use. Unaudited clients are restricted to private visibility, and a public desktop artifact cannot safely embed a confidential backend client secret.

Garden of Jihan will not imitate publishing with browser automation, copied cookies, passwords, unofficial endpoints, or upload-page scraping. The feature remains gated until the project has an audited TikTok client and a supported secure OAuth backend.

Official references:

- [TikTok Content Posting API get started](https://developers.tiktok.com/doc/content-posting-api-get-started/)
- [TikTok Direct Post reference](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)
- [TikTok content-sharing guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/)
