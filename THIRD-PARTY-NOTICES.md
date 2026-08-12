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
