import argparse
import csv
import json
import sys
from pathlib import Path
from config_loader import load_config, get_paths

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--video-root", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--brand", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--config", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    paths = get_paths(cfg)

    brand = args.brand or cfg["brand"]["name"]
    root = Path(args.video_root) if args.video_root else paths["clips"]
    output = Path(args.output_dir) if args.output_dir else paths["captions"]
    manifest = (
        Path(args.manifest)
        if args.manifest
        else paths["reports"] / "pass_only.csv"
    )

    if not manifest.is_file():
        raise FileNotFoundError(f"Manifest bulunamadi: {manifest}")

    with manifest.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    rows = [r for r in rows if r["status"] == "PASS"]

    if args.limit > 0:
        rows = rows[:args.limit]

    if not rows:
        raise RuntimeError("PASS klip bulunamadi")

    missing = [
        r["file"] for r in rows
        if not (root / r["file"]).is_file()
    ]
    if missing:
        raise RuntimeError(
            f"{len(missing)} video bulunamadi. Ornek: {missing[:3]}"
        )

    def caption_is_current(row):
        video = root / row["file"]
        caption = output / Path(row["file"]).with_suffix(".txt")

        return (
            caption.is_file()
            and caption.read_text(encoding="utf-8").strip()
            and caption.stat().st_mtime_ns >= video.stat().st_mtime_ns
        )

    pending = [r for r in rows if not caption_is_current(r)]

    print("Marka:", brand)
    print("PASS klip:", len(rows))
    print("Caption bekleyen:", len(pending))
    print("Model:", cfg["caption"]["model"])

    if args.dry_run:
        print("DRY RUN BASARILI - GPU modeli yuklenmedi.")
        return

    if not pending:
        print("Tum caption dosyalari hazir.")
        return

    output.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(Path(__file__).parent))
    from caption import get_frames

    import torch
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
    from tqdm import tqdm

    model_id = cfg["caption"]["model"]
    print("Model yukleniyor...", flush=True)

    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="sdpa"
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(model_id)

    log_path = output / "results.jsonl"
    success = 0
    errors = 0
    skipped = 0

    for row in tqdm(rows, desc=f"{brand} captions"):
        relative = Path(row["file"])
        video = root / relative

        # Her klibe benzersiz, klasor yapisini koruyan caption yolu
        target = output / relative.with_suffix(".txt")
        target.parent.mkdir(parents=True, exist_ok=True)

        if caption_is_current(row):
            skipped += 1
            continue

        try:
            frames = get_frames(video, count=cfg["caption"].get("frames", 5))

            prompt = (
                f"Describe this {brand} automotive video in one "
                "detailed English paragraph suitable for text-to-video training. "
                "Describe only what is visible: the vehicle, color, body style, "
                "camera viewpoint, environment, lighting, people, and visible "
                "changes across the frames. Identify the exact model only if "
                "clearly recognizable. Do not invent actions, camera movements, "
                "or vehicle details. Avoid speculation and promotional language. "
                "Write only the caption."
            )

            content = [{"type": "image", "image": img} for img in frames]
            content.append({"type": "text", "text": prompt})

            text = processor.apply_chat_template(
                [{"role": "user", "content": content}],
                tokenize=False,
                add_generation_prompt=True
            )

            inputs = processor(
                text=[text],
                images=frames,
                padding=True,
                return_tensors="pt"
            ).to(model.device)

            with torch.inference_mode():
                generated = model.generate(
                    **inputs,
                    max_new_tokens=220,
                    do_sample=False
                )

            generated = generated[:, inputs.input_ids.shape[1]:]
            caption = processor.batch_decode(
                generated,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0].strip()

            if not caption:
                raise RuntimeError("Bos caption")

            temp = target.with_suffix(".txt.tmp")
            temp.write_text(caption, encoding="utf-8")
            temp.replace(target)

            record = {
                "file": relative.as_posix(),
                "status": "success",
                "caption_file": target.relative_to(output).as_posix()
            }
            success += 1

        except Exception as exc:
            record = {
                "file": relative.as_posix(),
                "status": "error",
                "error": str(exc)
            }
            errors += 1

        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        if (success + errors) % 100 == 0:
            print(
                f"Yeni: {success} | Hata: {errors} | "
                f"Onceden hazir: {skipped}",
                flush=True
            )

    print(
        f"TAMAMLANDI | Yeni: {success} | "
        f"Hata: {errors} | Atlanan: {skipped}",
        flush=True
    )

if __name__ == "__main__":
    main()
