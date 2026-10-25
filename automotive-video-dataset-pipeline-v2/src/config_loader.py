import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "pipeline.json"


def load_config(path=None):
    config_path = Path(path).resolve() if path else DEFAULT_CONFIG

    if not config_path.is_file():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)

    required = [
        "project", "paths", "brand", "video",
        "scene_detection", "quality_control", "caption"
    ]

    for key in required:
        if key not in config:
            raise ValueError(f"Missing config section: {key}")

    # Relative paths are resolved from the config file's directory.
    base = config_path.parent

    for key in ("data_root", "reports_root"):
        value = Path(config["paths"][key]).expanduser()
        config["paths"][key] = str(
            (base / value).resolve() if not value.is_absolute()
            else value.resolve()
        )

    for key in ("raw_video_directory", "raw_metadata_file"):
        value = Path(config["brand"][key]).expanduser()
        config["brand"][key] = str(
            (base / value).resolve() if not value.is_absolute()
            else value.resolve()
        )

    return config


def get_paths(config):
    brand = config["brand"]["name"]
    brand_root = Path(config["paths"]["data_root"]) / brand

    return {
        "brand_root": brand_root,
        "raw": Path(config["brand"]["raw_video_directory"]),
        "metadata": Path(config["brand"]["raw_metadata_file"]),
        "scenes": brand_root / "scenes",
        "clips": brand_root / "clips",
        "captions": brand_root / "captions",
        "reports": Path(config["paths"]["reports_root"]) / brand,
    }


if __name__ == "__main__":
    config = load_config()
    print("Configuration loaded successfully.")
    for key, value in get_paths(config).items():
        print(f"{key}: {value}")
