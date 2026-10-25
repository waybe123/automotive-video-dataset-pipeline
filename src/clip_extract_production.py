import argparse
import csv
import json
import subprocess
from pathlib import Path


def extract(video, start, duration, output, args):
    width = args.width
    height = args.height

    if width <= 0 or height <= 0 or args.fps <= 0:
        raise ValueError("Cozunurluk ve FPS pozitif olmali.")

    vf = (
        f"fps={args.fps},"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    )

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-nostdin", "-y",
        "-ss", str(start),
        "-i", str(video),
        "-t", str(duration),
        "-vf", vf,
        "-an",
        "-c:v", args.codec,
        "-preset", "fast",
        "-crf", str(args.crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output)
    ]

    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--scenes", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--clip-seconds", type=float, default=5.0)
    parser.add_argument("--min-seconds", type=float, default=2.0)
    parser.add_argument("--max-clips", type=int, default=0)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=544)
    parser.add_argument("--fps", type=float, default=24)
    parser.add_argument("--codec", default="libx264")
    parser.add_argument("--crf", type=int, default=18)
    args = parser.parse_args()

    if args.clip_seconds <= 0 or args.min_seconds <= 0:
        raise ValueError("Klip sureleri pozitif olmali.")
    if args.max_clips < 0:
        raise ValueError("max-clips negatif olamaz.")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    with open(args.scenes, newline="", encoding="utf-8") as f:
        scenes = list(csv.DictReader(f))

    count = 0
    records = []

    for scene_index, scene in enumerate(scenes, 1):
        start = float(scene["start"])
        end = float(scene["end"])

        while end - start >= args.min_seconds:
            duration = min(args.clip_seconds, end - start)

            if duration < args.min_seconds:
                break

            name = (
                f"{Path(args.video).stem}_clip_{count + 1:06d}.mp4"
            )
            target = output / name

            extract(args.video, start, duration, target, args)

            records.append({
                "file": name,
                "scene": scene_index,
                "start": round(start, 3),
                "duration": round(duration, 3)
            })

            count += 1
            start += duration

            if args.max_clips and count >= args.max_clips:
                break

        if args.max_clips and count >= args.max_clips:
            break

    (output / "manifest.json").write_text(
        json.dumps(records, indent=2),
        encoding="utf-8"
    )

    print("=== KLIP URETIM SONUCU ===")
    print("Uretilen klip:", count)
    print("Klasor:", output)


if __name__ == "__main__":
    main()
