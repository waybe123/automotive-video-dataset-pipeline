import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from config_loader import load_config, get_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--video-root", default=None)
    parser.add_argument("--caption-root", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    paths = get_paths(cfg)

    manifest = Path(args.manifest) if args.manifest else paths["reports"] / "pass_only.csv"
    videos = Path(args.video_root) if args.video_root else paths["clips"]
    captions = Path(args.caption_root) if args.caption_root else paths["captions"]
    reports = Path(args.report_dir) if args.report_dir else paths["reports"]
    reports.mkdir(parents=True, exist_ok=True)

    minimum = int(cfg["caption"].get("minimum_words", 10))

    with manifest.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] == "PASS"]

    seen = defaultdict(list)
    results = []

    for row in rows:
        relative = Path(row["file"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Guvenli olmayan yol: {relative}")

        video = videos / relative
        caption_file = captions / relative.with_suffix(".txt")
        issues = []

        if not video.is_file():
            issues.append("MISSING_VIDEO")

        if not caption_file.is_file():
            issues.append("MISSING_CAPTION")
            content = ""
        else:
            content = caption_file.read_text(encoding="utf-8").strip()

        words = len(re.findall(r"\b[\w'-]+\b", content))

        if not content and "MISSING_CAPTION" not in issues:
            issues.append("EMPTY_CAPTION")
        elif content and words < minimum:
            issues.append("SHORT_CAPTION")

        if content:
            normalized = " ".join(content.lower().split())
            seen[normalized].append(relative.as_posix())

        results.append({
            "video": relative.as_posix(),
            "caption": relative.with_suffix(".txt").as_posix(),
            "words": words,
            "issues": issues
        })

    for result in results:
        caption_file = captions / result["caption"]
        if caption_file.is_file():
            content = caption_file.read_text(encoding="utf-8").strip()
            if content:
                normalized = " ".join(content.lower().split())
                if len(seen[normalized]) > 1:
                    result["issues"].append("DUPLICATE_CAPTION")

    output = reports / "caption_qc_details.csv"

    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["video", "caption", "words", "status", "issues"]
        )
        writer.writeheader()
        for result in results:
            writer.writerow({
                "video": result["video"],
                "caption": result["caption"],
                "words": result["words"],
                "status": "PASS" if not result["issues"] else "REVIEW",
                "issues": "|".join(result["issues"])
            })

    passed = sum(not r["issues"] for r in results)
    summary = {
        "total": len(results),
        "passed": passed,
        "review": len(results) - passed,
        "minimum_words": minimum
    }

    (reports / "caption_qc_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print("=== CAPTION QC V2 ===")
    print("Toplam:", summary["total"])
    print("PASS:", summary["passed"])
    print("REVIEW:", summary["review"])
    print("Rapor:", output)


if __name__ == "__main__":
    main()
