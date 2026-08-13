# Third-party notices

Garden of Jihan is distributed with third-party software. The corresponding
copyright and license terms remain those of their respective authors.

## FFmpeg

The Windows package bundles `ffmpeg.exe` and `ffprobe.exe` from the Gyan FFmpeg
8.1 full build. That build is licensed under the GNU General Public License,
version 3, and includes GPL components used by Garden of Jihan for H.264 video
encoding and styled caption rendering.

- Binary release: https://github.com/GyanD/codexffmpeg/releases/tag/8.1
- Pinned archive SHA256:
  `587B1C37DE29C5003D01CF65DA10001BAC43A58B88E61AF0FC77C61DAFF04761`
- Corresponding FFmpeg source revision, as identified by the binary distributor:
  https://github.com/FFmpeg/FFmpeg/commit/9047fa1b08
- FFmpeg project and source downloads: https://ffmpeg.org/

The Windows ZIP also contains `FFMPEG-LICENSE.txt` and
`FFMPEG-BUILD-INFO.txt`, copied unchanged from the checksum-verified binary
archive.

The Mac packages bundle native `ffmpeg` and `ffprobe` 8.1.2 binaries from the
Shaka Project static FFmpeg release `n8.1.2-1`. Each architecture is downloaded
from its immutable release URL and verified against a pinned SHA256 before it
is included.

- Binary release: https://github.com/shaka-project/static-ffmpeg-binaries/releases/tag/n8.1.2-1
- FFmpeg Apple Silicon SHA256: `e7b9fcd97f95f333512d6e8b8ac24d9dbc08f189f36047695499bd7b57214b22`
- FFprobe Apple Silicon SHA256: `ded4c698b8ff38d0bc1fd30fcc5e768dc46f58bc15a8dfd61f98615ba49cde5c`
- FFmpeg Intel SHA256: `62c87854d851f202fc4a29bdda0fe7b6ebcddd37b863482ce1bdc81151b03fe4`
- FFprobe Intel SHA256: `d530823f480a3c7eb6334f18a00197d1e9f1070e86172b9aa89c4bf4022bd879`

## Python embedded runtime

The private portable browser bundle contains the official CPython 3.12.10
64-bit Windows embedded distribution from the Python Software Foundation.
The build verifies both the pinned archive SHA256 and the Authenticode signer
on `python.exe` and `pythonw.exe` before packaging.

- Official archive: https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip
- Pinned archive SHA256:
  `4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3`
- Python license: https://docs.python.org/3/license.html

The unchanged Python `LICENSE.txt` remains inside the portable `runtime`
folder. Installed Python packages retain their wheel metadata and license files
inside `app/vendor`; their exact versions and distribution hashes are locked in
`requirements-portable-windows.txt`.
