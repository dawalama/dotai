"""Persistent storage for configuration and index."""

import json
from pathlib import Path

from .models import GlobalConfig, KnowledgeNode

CONFIG_FILE = "config.json"
INDEX_FILE = "index.json"

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


def load_index() -> KnowledgeNode | None:
    index_path = get_config_dir() / INDEX_FILE
    if index_path.exists():
        data = json.loads(index_path.read_text())
        return KnowledgeNode(**data)
    return None


def save_index(index: KnowledgeNode) -> None:
    ensure_config_dir()
    index_path = get_config_dir() / INDEX_FILE
    data = json.loads(index.model_dump_json())
    index_path.write_text(json.dumps(data, indent=2))


def get_index_path() -> Path:
    return get_config_dir() / INDEX_FILE


def get_config_path() -> Path:
    return get_config_dir() / CONFIG_FILE
