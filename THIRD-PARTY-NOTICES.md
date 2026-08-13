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

The Mac packages bundle native `ffmpeg` and `ffprobe` binaries from the
eugeneware static FFmpeg release `b6.1.1`, whose Mac builds include libass for
styled subtitle rendering. Each architecture and its accompanying license are
downloaded through HTTPS and accepted only after their exact SHA256 digests
match the values pinned in `scripts/build-macos.sh`. `FFMPEG-LICENSE.txt` is
included in every Mac handoff.

- Binary release and corresponding sources: https://github.com/eugeneware/ffmpeg-static/releases/tag/b6.1.1
- FFmpeg project and source downloads: https://ffmpeg.org/
- FFmpeg Apple Silicon SHA256: `a90e3db6a3fd35f6074b013f948b1aa45b31c6375489d39e572bea3f18336584`
- FFprobe Apple Silicon SHA256: `bb2db6f5d8cef919da12fbf592119a987202a8c060a886f3cab091f9cab90b64`
- FFmpeg Intel SHA256: `ebdddc936f61e14049a2d4b549a412b8a40deeff6540e58a9f2a2da9e6b18894`
- FFprobe Intel SHA256: `fa3add0ce901f7241abe0dfc0155d958fc834aca3f8ce61f87cc712ae669c1e0`

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
