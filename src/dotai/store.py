"""Persistent storage for dotai configuration."""

import json
from pathlib import Path

from .models import GlobalConfig

CONFIG_FILE = "config.json"

# Default config directory — can be overridden by consumers
_config_dir: Path | None = None
_DEFAULT_CONFIG_DIR = Path.home() / ".config" / "dotai"


def set_config_dir(path: Path) -> None:
    """Override the config directory (for consumers like RDC)."""
    global _config_dir
    _config_dir = path


def get_config_dir() -> Path:
    """Return the active config directory."""
    return _config_dir or _DEFAULT_CONFIG_DIR


def ensure_config_dir() -> Path:
    d = get_config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_config() -> GlobalConfig:
    config_path = get_config_dir() / CONFIG_FILE
    if config_path.exists():
        data = json.loads(config_path.read_text())
        return GlobalConfig(**data)
    return GlobalConfig()


def save_config(config: GlobalConfig) -> None:
    ensure_config_dir()
    config_path = get_config_dir() / CONFIG_FILE
    data = json.loads(config.model_dump_json())
    config_path.write_text(json.dumps(data, indent=2))


def get_config_path() -> Path:
    return get_config_dir() / CONFIG_FILE
