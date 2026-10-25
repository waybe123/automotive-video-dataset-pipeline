import argparse
import csv
import json
from pathlib import Path

from config_loader import load_config, get_paths


def safe_relative(value):
    p = Path(value)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise ValueError(f"Guvenli olmayan yol: {value}")
    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--qc-report", default=None)
    parser.add_argument("--video-root", default=None)
    parser.add_argument("--caption-root", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    paths = get_paths(cfg)

    reports = Path(args.report_dir) if args.report_dir else paths["reports"]
    source = Path(args.manifest) if args.manifest else reports / "pass_only.csv"
    qc_file = Path(args.qc_report) if args.qc_report else reports / "caption_qc_details.csv"
    video_root = Path(args.video_root) if args.video_root else paths["clips"]
    caption_root = Path(args.caption_root) if args.caption_root else paths["captions"]

    reports.mkdir(parents=True, exist_ok=True)

    with source.open(newline="", encoding="utf-8") as f:
        source_rows = [
            r for r in csv.DictReader(f)
            if r["status"] == "PASS"
        ]

    with qc_file.open(newline="", encoding="utf-8") as f:
        qc_rows = list(csv.DictReader(f))

    qc_map = {}
    for row in qc_rows:
        key = safe_relative(row["video"]).as_posix()
        if key in qc_map:
            raise RuntimeError(f"Tekrarlanan QC kaydi: {key}")
        qc_map[key] = row

    accepted = []
    excluded = []
    seen = set()

    for row in source_rows:
        relative = safe_relative(row["file"])
        key = relative.as_posix()

        if key in seen:
            raise RuntimeError(f"Tekrarlanan kaynak kaydi: {key}")
        seen.add(key)

        qc = qc_map.get(key)
        caption = relative.with_suffix(".txt")
        reasons = []

        if qc is None:
            reasons.append("MISSING_QC")
        elif qc["status"] != "PASS":
            reasons.append(qc.get("issues") or "QC_REVIEW")
        elif safe_relative(qc["caption"]) != caption:
            reasons.append("CAPTION_MISMATCH")

        video_path = video_root / relative
        caption_path = caption_root / caption

        if not video_path.is_file():
            reasons.append("MISSING_VIDEO")
        if not caption_path.is_file():
            reasons.append("MISSING_CAPTION")
        elif not caption_path.read_text(encoding="utf-8").strip():
            reasons.append("EMPTY_CAPTION")

        if reasons:
            excluded.append({
                "video": key,
                "reason": "|".join(reasons)
            })
            continue

        accepted.append({
            "video": key,
            "caption": caption.as_posix()
        })

    csv_path = reports / "final_manifest.csv"
    jsonl_path = reports / "final_manifest.jsonl"
    excluded_path = reports / "excluded.csv"
    summary_path = reports / "dataset_summary.json"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["video", "caption"])
        writer.writeheader()
        writer.writerows(accepted)

    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in accepted:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with excluded_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["video", "reason"])
        writer.writeheader()
        writer.writerows(excluded)

    summary = {
        "brand": cfg["brand"]["name"],
        "source_pass": len(source_rows),
        "accepted": len(accepted),
        "excluded": len(excluded),
        "video_root": str(video_root),
        "caption_root": str(caption_root)
    }

    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("=== DATASET MANIFEST V2 ===")
    print("Marka:", summary["brand"])
    print("Kaynak PASS:", len(source_rows))
    print("Kabul:", len(accepted))
    print("Haric:", len(excluded))
    print("Manifest:", csv_path)

    if not accepted:
        raise RuntimeError("Gecerli video-caption eslesmesi bulunamadi.")


if __name__ == "__main__":
    main()
