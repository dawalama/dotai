"""Tests for dotai.store persistence."""

import json

from dotai.models import GlobalConfig, KnowledgeNode, NodeType, ProjectConfig
from dotai.store import (
    get_config_dir,
    load_config,
    load_index,
    save_config,
    save_index,
    set_config_dir,
)


class TestConfigDir:
    def test_set_and_get(self, config_dir):
        set_config_dir(config_dir)
        assert get_config_dir() == config_dir
        # Reset to avoid polluting other tests
        set_config_dir(None)


class TestConfigPersistence:
    def test_save_and_load(self, config_dir):
        set_config_dir(config_dir)
        try:
            config = GlobalConfig(
                projects=[ProjectConfig(name="test", path=config_dir / "test")]
            )
            save_config(config)
            loaded = load_config()
            assert len(loaded.projects) == 1
            assert loaded.projects[0].name == "test"
        finally:
            set_config_dir(None)

    def test_load_missing_returns_default(self, config_dir):
        set_config_dir(config_dir)
        try:
            config = load_config()
            assert config.version == "1.0.0"
            assert config.projects == []
        finally:
            set_config_dir(None)


class TestIndexPersistence:
    def test_save_and_load(self, config_dir):
        set_config_dir(config_dir)
        try:
            node = KnowledgeNode(
                id="root",
                name="Root",
                node_type=NodeType.ROOT,
                children=[
                    KnowledgeNode(id="child", name="Child", node_type=NodeType.SKILL)
                ],
            )
            save_index(node)
            loaded = load_index()
            assert loaded is not None
            assert loaded.id == "root"
            assert len(loaded.children) == 1
        finally:
            set_config_dir(None)

    def test_load_missing_returns_none(self, config_dir):
        set_config_dir(config_dir)
        try:
            assert load_index() is None
        finally:
            set_config_dir(None)
