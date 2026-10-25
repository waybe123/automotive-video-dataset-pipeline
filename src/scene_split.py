import argparse
import csv
from pathlib import Path

from scenedetect import open_video, SceneManager, ContentDetector


def detect_scenes(video_path, threshold=27.0, min_scene_len=48):
    video = open_video(str(video_path), backend="pyav")
    manager = SceneManager()
    manager.add_detector(
        ContentDetector(
            threshold=threshold,
            min_scene_len=min_scene_len
        )
    )
    manager.detect_scenes(video=video, show_progress=True)
    scenes = manager.get_scene_list()

    if not scenes:
        duration = video.duration
        if duration is None:
            raise RuntimeError("Video suresi okunamadi")
        scenes = [(video.base_timecode, duration)]

    return [
        {
            "start": round(start.seconds, 3),
            "end": round(end.seconds, 3),
            "duration": round(
                end.seconds - start.seconds, 3
            )
        }
        for start, end in scenes
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--threshold", type=float, default=27.0)
    args = parser.parse_args()

    video = Path(args.video)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    scenes = detect_scenes(video, threshold=args.threshold)

    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["start", "end", "duration"]
        )
        writer.writeheader()
        writer.writerows(scenes)

    print("\n=== SAHNE TESPIT SONUCU ===")
    print("Video:", video.name)
    print("Sahne sayisi:", len(scenes))
    print("Rapor:", output)


if __name__ == "__main__":
    main()
