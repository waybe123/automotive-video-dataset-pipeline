import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

from config_loader import load_config, get_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    cfg = load_config(args.config)
    paths = get_paths(cfg)
    metadata_file = paths["metadata"]
    raw_dir = paths["raw"]
    output_dir = paths["scenes"]
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    if not isinstance(metadata, list):
        raise ValueError("Raw metadata bir JSON listesi olmali.")

    if args.limit > 0:
        metadata = metadata[:args.limit]

    report = output_dir / "batch_report.csv"
    rows = []
    started = time.time()

    for i, item in enumerate(metadata, 1):
        name = item["file"]
        source = raw_dir / name
        target = output_dir / f"video_{i:04d}.csv"

        print(f"[{i}/{len(metadata)}] {name}", flush=True)

        if not source.is_file():
            rows.append([i, name, 0, "MISSING"])
            continue

        if target.is_file():
            with target.open(newline="", encoding="utf-8") as f:
                count = len(list(csv.DictReader(f)))
            if count > 0:
                rows.append([i, name, count, "OK"])
                continue

        try:
            subprocess.run([
                sys.executable,
                str(Path(__file__).with_name("scene_split.py")),
                "--video", str(source),
                "--output", str(target),
                "--threshold",
                str(cfg["scene_detection"]["threshold"])
            ], check=True)

            with target.open(newline="", encoding="utf-8") as f:
                count = len(list(csv.DictReader(f)))

            rows.append([
                i, name, count,
                "OK" if count > 0 else "EMPTY"
            ])
        except Exception as exc:
            print("HATA:", exc, flush=True)
            rows.append([i, name, 0, "ERROR"])

        with report.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["index", "video", "scene_count", "status"])
            writer.writerows(rows)

    print("=== SAHNE TESPITI TAMAMLANDI ===")
    print("Video:", len(rows))
    print("Basarili:", sum(r[3] == "OK" for r in rows))
    print("Sure (dk):", round((time.time() - started) / 60, 2))


if __name__ == "__main__":
    main()
