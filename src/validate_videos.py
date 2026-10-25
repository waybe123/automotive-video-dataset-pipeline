import argparse
import csv
import json
import subprocess
from pathlib import Path
from config_loader import load_config, get_paths
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
import time


def probe_video(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,avg_frame_rate",
            "-of", "json", str(path)
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True
    )

    info = json.loads(result.stdout)
    streams = [
        s for s in info.get("streams", [])
        if s.get("codec_type") == "video"
    ]

    if not streams:
        raise ValueError("Video stream yok")

    from fractions import Fraction

    stream = streams[0]

    return (
        float(info.get("format", {}).get("duration", 0)),
        int(stream.get("width", 0)),
        int(stream.get("height", 0)),
        float(Fraction(stream.get("avg_frame_rate", "0/1")))
    )


def inspect_video(path, root):
    row = {
        "file": str(path.relative_to(root)),
        "status": "REVIEW",
        "reason": "",
        "duration": 0,
        "width": 0,
        "height": 0,
        "fps": 0,
        "black_score": "",
        "freeze_score": "",
        "blur_score": ""
    }

    try:
        duration, width, height, fps = probe_video(path)

        row.update({
            "duration": round(duration, 3),
            "width": width,
            "height": height,
            "fps": round(fps, 3)
        })

        reasons = []

        if duration < 2:
            reasons.append("TOO_SHORT")
        if duration > 20:
            reasons.append("TOO_LONG")
        if width < 640 or height < 360:
            reasons.append("LOW_RESOLUTION")
        if fps < 15:
            reasons.append("LOW_FPS")

        # Sample up to 3 frames across the video.
        # This is a fast screening check, not full-frame validation.
        positions = [
            max(0, duration * fraction)
            for fraction in (0.2, 0.5, 0.8)
        ]

        black_count = 0
        freeze_count = 0
        blur_values = []

        try:
            import cv2
            import numpy as np

            cap = cv2.VideoCapture(str(path))
            frames = []

            if not cap.isOpened():
                reasons.append("CANNOT_DECODE")
            else:
                for position in positions:
                    cap.set(cv2.CAP_PROP_POS_MSEC, position * 1000)
                    ok, frame = cap.read()

                    if not ok or frame is None:
                        reasons.append("FRAME_READ_ERROR")
                        continue

                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    small = cv2.resize(gray, (320, 180))

                    if float(np.mean(small)) < 12:
                        black_count += 1

                    blur_values.append(
                        float(cv2.Laplacian(small, cv2.CV_64F).var())
                    )

                    frames.append(small)

                for a, b in zip(frames, frames[1:]):
                    difference = float(
                        np.mean(
                            cv2.absdiff(a, b)
                        )
                    )
                    if difference < 1.0:
                        freeze_count += 1

            cap.release()

        except ImportError:
            reasons.append("OPENCV_NOT_INSTALLED")

        row["black_score"] = black_count
        row["freeze_score"] = freeze_count
        row["blur_score"] = (
            round(sum(blur_values) / len(blur_values), 2)
            if blur_values else ""
        )

        if black_count >= 2:
            reasons.append("POSSIBLE_BLACK_VIDEO")

        if freeze_count >= 2:
            reasons.append("POSSIBLE_FROZEN_VIDEO")

        # Conservative heuristic: flag for review, never auto-reject.
        if blur_values and sum(blur_values) / len(blur_values) < 8:
            reasons.append("POSSIBLE_BLUR")

        if not reasons:
            row["status"] = "PASS"
            row["reason"] = "OK"
        else:
            row["status"] = "REVIEW"
            row["reason"] = "|".join(sorted(set(reasons)))

    except Exception as exc:
        row["status"] = "REJECT"
        row["reason"] = str(exc)[:200]

    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-dir", default=None)
    parser.add_argument("--report", default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    paths = get_paths(cfg)
    root = Path(args.video_dir) if args.video_dir else paths["clips"]
    if args.workers < 1:
        raise ValueError("--workers en az 1 olmali")
    videos = sorted(root.rglob("*.mp4"))

    if args.limit:
        videos = videos[:args.limit]

    if not videos:
        raise RuntimeError("Video bulunamadi")

    print("Bulunan klip:", len(videos), flush=True)

    started = time.time()
    rows = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(inspect_video, p, root): p
            for p in videos
        }

        for future in as_completed(futures):
            rows.append(future.result())

            if len(rows) % 100 == 0:
                print(
                    f"Kontrol: {len(rows)}/{len(videos)}",
                    flush=True
                )

    rows.sort(key=lambda x: x["file"])

    report = Path(args.report) if args.report else paths["reports"] / "pass_only.csv"
    report.parent.mkdir(parents=True, exist_ok=True)

    with report.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter(row["status"] for row in rows)

    print("\n=== KALITE KONTROL SONUCU ===")
    print("Toplam:", len(rows))
    print("PASS:", counts["PASS"])
    print("REVIEW:", counts["REVIEW"])
    print("REJECT:", counts["REJECT"])
    print("Sure (dakika):", round((time.time() - started) / 60, 2))
    print("Rapor:", report)


if __name__ == "__main__":
    main()
