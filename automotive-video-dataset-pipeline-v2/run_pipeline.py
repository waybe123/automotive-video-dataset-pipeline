import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"


def run(script, *args):
    command = [
        sys.executable,
        str(SRC / script),
        *map(str, args)
    ]
    print(f"\n=== CALISIYOR: {script} ===", flush=True)
    subprocess.run(command, check=True)


def count_pass(report):
    with report.open(newline="", encoding="utf-8") as f:
        return sum(
            row["status"] == "PASS"
            for row in csv.DictReader(f)
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-video-prep", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(SRC))
    from config_loader import load_config, get_paths

    cfg = load_config(args.config)
    paths = get_paths(cfg)

    clips = paths["clips"]
    captions = paths["captions"]
    reports = paths["reports"]
    reports.mkdir(parents=True, exist_ok=True)

    video_qc = reports / "video_qc.csv"
    caption_qc = reports / "caption_qc_details.csv"

    if not args.skip_video_prep:
        run(
            "batch_scene_detect.py",
            "--config", args.config,
            "--limit", args.limit
        )

        run(
            "batch_clip_extract.py",
            "--config", args.config,
            "--limit", args.limit
        )

    run(
        "validate_videos.py",
        "--config", args.config,
        "--video-dir", clips,
        "--report", video_qc
    )

    passed = count_pass(video_qc)
    if passed == 0:
        raise RuntimeError("Video QC: PASS klip bulunamadi")

    print(f"Video QC PASS: {passed}", flush=True)

    # Caption, QC ve manifest ayni video QC raporunu kullanir.
    run(
        "batch_caption.py",
        "--config", args.config,
        "--manifest", video_qc,
        "--video-root", clips,
        "--output-dir", captions
    )

    run(
        "caption_qc_v2.py",
        "--config", args.config,
        "--manifest", video_qc,
        "--video-root", clips,
        "--caption-root", captions,
        "--report-dir", reports
    )

    run(
        "build_manifest_v2.py",
        "--config", args.config,
        "--manifest", video_qc,
        "--qc-report", caption_qc,
        "--video-root", clips,
        "--caption-root", captions,
        "--report-dir", reports
    )

    print("\n=== PIPELINE V2 TAMAMLANDI ===")
    print("Marka:", cfg["brand"]["name"])
    print("Manifest:", reports / "final_manifest.csv")


if __name__ == "__main__":
    main()
