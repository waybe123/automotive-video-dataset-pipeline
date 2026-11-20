# Multi-Brand Automotive Video Dataset Pipeline

An automated, configurable pipeline that converts raw automotive videos into training-ready video-caption datasets.

The pipeline performs scene detection, clip extraction, video quality control, AI caption generation, caption quality control, and final manifest generation.

**Scope:** Dataset preparation only. Model training and cloud backup are not included.

## Features

- Automatic scene detection
- Configurable video clip extraction
- Resolution and FPS normalization
- Video quality control
- Qwen2.5-VL caption generation
- Caption quality control
- CSV and JSONL manifests
- Resume support
- Configurable automotive brands
- No cloud storage requirement

## Requirements

- Python 3.10+
- FFmpeg and FFprobe
- NVIDIA GPU recommended for caption generation
- CUDA-compatible PyTorch
- Sufficient disk space

Default caption model: `Qwen/Qwen2.5-VL-7B-Instruct`.

The current caption implementation uses the Qwen2.5-VL architecture.

## Installation

Clone your repository and enter the project directory:

    git clone https://github.com/waybe123/automotive-video-dataset-pipeline.git
    cd automotive-video-dataset-pipeline

Create a Python environment:

    python -m venv .venv
    source .venv/bin/activate

Install CUDA-compatible PyTorch for your hardware, then install the remaining dependencies:

    pip install -r requirements.txt

Verify FFmpeg:

    ffmpeg -version
    ffprobe -version

## Input structure

Place your raw videos in the following directory:

    data/
      example_brand/
        raw/
          video_001.mp4
          video_002.mp4
        manifests/
          raw_metadata.json

The metadata file must contain a JSON list:

    [
      {"file": "video_001.mp4"},
      {"file": "video_002.mp4"}
    ]

## Configuration

Edit `config/pipeline.json` before running.

Important settings:

- `brand.name`: Automotive brand or dataset label
- `brand.raw_video_directory`: Input video directory
- `brand.raw_metadata_file`: Raw metadata JSON file
- `video.resolution`: Output resolution
- `video.fps`: Output FPS
- `video.clip_seconds`: Target clip length
- `video.min_clip_seconds`: Minimum clip length
- `video.max_clips_per_video`: Maximum clips per source video (0 = unlimited)
- `scene_detection.threshold`: Scene detection threshold
- `caption.model`: Caption model identifier
- `caption.frames`: Number of sampled frames

Relative paths are resolved relative to the configuration file.

## Usage

Run the full pipeline:

    python run_pipeline.py --config config/pipeline.json

Test with the first source video:

    python run_pipeline.py --config config/pipeline.json --limit 1

Skip video preparation when existing clips are ready:

    python run_pipeline.py --config config/pipeline.json --skip-video-prep

## Pipeline stages

1. Scene detection
2. Clip extraction and normalization
3. Video quality control
4. AI caption generation
5. Caption quality control
6. Final manifest generation

## Output structure

    data/
      example_brand/
        scenes/
        clips/
        captions/

    reports/
      example_brand/
        video_qc.csv
        caption_qc_details.csv
        caption_qc_summary.json
        final_manifest.csv
        final_manifest.jsonl
        excluded.csv
        dataset_summary.json

The final manifest contains accepted video-caption pairs.

## Resume behavior

Previously processed clips can be skipped when their extraction settings and source timestamps remain unchanged.

Existing captions are skipped when they are nonempty and newer than their corresponding video files.

These checks are not full cryptographic verification of source content.

## Limitations

- The default 7B caption model requires substantial GPU memory.
- The caption prompt is designed for automotive content.
- Quality control is heuristic and may require manual review.
- This pipeline does not train video generation models.
- Cloud backups are intentionally excluded.
- Dependencies are not fully version-pinned.

## License

This project is licensed under the MIT License.
