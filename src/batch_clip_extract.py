import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from config_loader import load_config, get_paths


def probe_clip(path):
    if not path.is_file() or path.stat().st_size == 0:
        return False

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", str(path)
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True
        )

        info = json.loads(result.stdout)
        duration = float(info["format"]["duration"])

        return duration > 0

    except Exception:
        return False



def settings_fingerprint(video_cfg):
    keys = [
        "clip_seconds",
        "min_clip_seconds",
        "max_clips_per_video",
        "resolution",
        "fps",
        "codec",
        "crf"
    ]

    settings = {key: video_cfg[key] for key in keys}

    payload = json.dumps(
        settings, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def settings_match(target, video_cfg):
    state_file = target / ".pipeline_settings.json"

    if not state_file.is_file():
        return False

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        return state.get("fingerprint") == settings_fingerprint(video_cfg)
    except Exception:
        return False


def save_settings(target, video_cfg):
    state_file = target / ".pipeline_settings.json"
    payload = {
        "fingerprint": settings_fingerprint(video_cfg),
        "settings": video_cfg
    }

    temp = target / ".pipeline_settings.tmp"
    temp.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8"
    )
    temp.replace(state_file)

def completed(target, source, scenes):
    manifest = target / "manifest.json"

    if not manifest.is_file():
        return False

    # Kaynak video veya sahne bilgisi degismisse yeniden isle.
    manifest_time = manifest.stat().st_mtime_ns

    if (
        source.stat().st_mtime_ns > manifest_time
        or scenes.stat().st_mtime_ns > manifest_time
    ):
        return False

    try:
        records = json.loads(manifest.read_text(encoding="utf-8"))

        if not isinstance(records, list) or not records:
            return False

        names = set()

        for item in records:
            if not isinstance(item, dict):
                return False

            name = item.get("file")

            if not isinstance(name, str) or not name:
                return False

            relative = Path(name)

            if (
                relative.is_absolute()
                or ".." in relative.parts
                or relative.suffix.lower() != ".mp4"
            ):
                return False

            if name in names:
                return False

            names.add(name)

            clip = target / relative

            if not probe_clip(clip):
                return False

        # Manifest disinda kalmis klipler varsa eksik/tutarsiz islem olabilir.
        actual = {
            p.relative_to(target).as_posix()
            for p in target.rglob("*.mp4")
        }

        return actual == names

    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    cfg = load_config(args.config)
    paths = get_paths(cfg)

    metadata = json.loads(
        paths["metadata"].read_text(encoding="utf-8")
    )

    if not isinstance(metadata, list):
        raise ValueError("Raw metadata bir JSON listesi olmali.")

    if args.limit > 0:
        metadata = metadata[:args.limit]

    output_dir = paths["clips"]
    output_dir.mkdir(parents=True, exist_ok=True)

    report = output_dir / "batch_report.csv"
    rows = []
    started = time.time()

    def write_report():
        # Ayni icerige sahip raporu gereksiz yere yeniden yazma.
        import io

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["index", "video", "status"])
        writer.writerows(rows)

        content = buffer.getvalue()

        if report.is_file() and report.read_text(encoding="utf-8") == content:
            return

        report.write_text(content, encoding="utf-8")

    for i, item in enumerate(metadata, 1):
        name = item["file"]
        source = paths["raw"] / name
        scenes = paths["scenes"] / f"video_{i:04d}.csv"
        target = output_dir / f"video_{i:04d}"

        print(f"[{i}/{len(metadata)}] {name}", flush=True)

        if not source.is_file() or not scenes.is_file():
            rows.append([i, name, "MISSING"])
            write_report()
            continue

        video_cfg = cfg["video"]

        if completed(target, source, scenes) and settings_match(target, video_cfg):
            print("  SKIPPED: Klipler zaten hazir.", flush=True)
            rows.append([i, name, "SKIPPED"])
            write_report()
            continue

        target.mkdir(parents=True, exist_ok=True)
        video_cfg = cfg["video"]

        command = [
            sys.executable,
            str(Path(__file__).with_name("clip_extract_production.py")),
            "--video", str(source),
            "--scenes", str(scenes),
            "--output", str(target),
            "--clip-seconds", str(video_cfg["clip_seconds"]),
            "--min-seconds", str(video_cfg["min_clip_seconds"]),
            "--max-clips", str(video_cfg["max_clips_per_video"]),
            "--width", str(video_cfg["resolution"][0]),
            "--height", str(video_cfg["resolution"][1]),
            "--fps", str(video_cfg["fps"]),
            "--codec", str(video_cfg["codec"]),
            "--crf", str(video_cfg["crf"])
        ]

        result = subprocess.run(command)

        valid = result.returncode == 0 and completed(target, source, scenes)

        if valid:
            save_settings(target, video_cfg)

        status = "OK" if valid else "ERROR"

        rows.append([i, name, status])
        write_report()

        if status == "ERROR":
            raise RuntimeError(f"Klip uretimi basarisiz: {name}")

    print("\n=== KLIP URETIMI TAMAMLANDI ===")
    print("Video:", len(rows))
    print("Yeni tamamlanan:", sum(r[2] == "OK" for r in rows))
    print("Atlanan:", sum(r[2] == "SKIPPED" for r in rows))
    print("Sure (dk):", round((time.time() - started) / 60, 2))


if __name__ == "__main__":
    main()
