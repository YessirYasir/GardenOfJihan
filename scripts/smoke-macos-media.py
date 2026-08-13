from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603
        command, check=True, capture_output=True, text=True, shell=False
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    args = parser.parse_args()
    app = args.package_root.resolve() / "Garden of Jihan.app"
    matches = [path for path in app.rglob("ffmpeg") if path.is_file()]
    concrete = [path for path in matches if not path.is_symlink()]
    if len(concrete) != 1:
        raise SystemExit("Bundled Mac FFmpeg was not found")
    ffmpeg = str(concrete[0])
    filters = run([ffmpeg, "-hide_banner", "-filters"])
    if " subtitles " not in f"{filters.stdout}\n{filters.stderr}":
        raise SystemExit("Bundled Mac media engine cannot render styled captions")

    with tempfile.TemporaryDirectory(prefix="goj-macos-media-") as temporary:
        root = Path(temporary)
        captions = root / "unicode.ass"
        captions.write_text(
            """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,3,1,2,30,30,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Caption,,0,0,0,,Garden of Jihan · جيهان · Soomaali
""",
            encoding="utf-8",
        )
        caption_output = root / "caption.mp4"
        run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x244A35:s=640x360:d=1",
                "-vf",
                f"subtitles=filename='{captions}'",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-y",
                str(caption_output),
            ]
        )
        framing_output = root / "framing.mp4"
        run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=1280x720:d=2:r=12",
                "-vf",
                "scale=540:960:force_original_aspect_ratio=increase,crop=540:960:max(0\\,min(iw-ow\\,0.5*iw-ow/2)):0",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-y",
                str(framing_output),
            ]
        )
        if not caption_output.is_file() or not framing_output.is_file():
            raise SystemExit("Mac caption or vertical framing smoke output is missing")
    print("Mac captions and vertical framing passed")


if __name__ == "__main__":
    main()
