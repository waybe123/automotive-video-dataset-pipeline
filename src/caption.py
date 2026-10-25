import argparse
import json
from pathlib import Path

def get_frames(path, count=5):
    import cv2
    from PIL import Image

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Video acilamadi: {path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < count:
        cap.release()
        raise RuntimeError(f"Yetersiz kare: {path}")

    frames = []
    for i in range(count):
        pos = min(int((i + 0.5) * total / count), total - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ok, frame = cap.read()
        if not ok:
            cap.release()
            raise RuntimeError(f"Kare okunamadi: {path}, {pos}")
        frames.append(Image.fromarray(
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ))

    cap.release()
    return frames

def run(video_dir, output_dir, brand, category="automotive"):
    import torch
    from tqdm import tqdm
    from transformers import (
        Qwen2_5_VLForConditionalGeneration,
        AutoProcessor
    )

    video_dir = Path(video_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    videos = sorted(video_dir.glob("*.mp4"))
    if not videos:
        raise RuntimeError("Video bulunamadi")

    model_id = "Qwen/Qwen2.5-VL-7B-Instruct"
    print("Qwen yukleniyor:", model_id)

    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="sdpa"
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(model_id)

    results = output_dir / "results.jsonl"

    for video in tqdm(videos, desc=f"{brand} caption"):
        target = output_dir / f"{video.stem}.txt"

        if target.exists() and target.read_text(
            encoding="utf-8"
        ).strip():
            continue

        try:
            frames = get_frames(video)

            prompt = (
                f"Describe this {brand} automotive video in one "
                "detailed English paragraph suitable for "
                "text-to-video training. "
                f"The scene category is {category}. "
                "Describe the visible vehicle, color, body style, "
                "camera viewpoint, environment, lighting, people, "
                "and visible changes across the frames. "
                "Only identify the exact vehicle model if clearly "
                "recognizable. Do not invent movements or actions. "
                "Avoid speculation and promotional language. "
                "Write only the caption."
            )

            content = [
                {"type": "image", "image": img}
                for img in frames
            ]
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
                "file": video.name,
                "status": "success",
                "caption": caption
            }

        except Exception as exc:
            record = {
                "file": video.name,
                "status": "error",
                "error": str(exc)
            }

        with results.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print("Caption islemi tamamlandi.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--brand", required=True)
    parser.add_argument("--category", default="automotive")
    args = parser.parse_args()

    run(args.video_dir, args.output_dir, args.brand, args.category)
