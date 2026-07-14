"""Tests for preference / taste packs."""

from pathlib import Path

from dotai.models import GlobalConfig, ProjectConfig
from dotai.preferences import (
    activate_pack,
    create_preference_pack,
    deactivate_pack,
    format_preferences_section,
    load_active_pack_ids,
    load_preferences_from_dir,
    parse_preference_file,
    pull_preference_pack,
    resolve_preference_packs,
)
from dotai.cli.prefs_cmd import _find_pack_or_local
from dotai.sync import generate_primer


class TestParsePreferencePack:
    def test_full_pack(self, tmp_path):
        path = tmp_path / "cli.md"
        path.write_text(
            "---\n"
            "name: CLI Conventions\n"
            "id: cli\n"
            "description: How I build CLIs\n"
            "domain: cli\n"
            "tags: typescript, commander\n"
            "source: local\n"
            "---\n\n"
            "- Prefer TypeScript + tsup\n"
            "- Use Commander.js\n"
        )
        pack = parse_preference_file(path)
        assert pack is not None
        assert pack.id == "cli"
        assert pack.domain == "cli"
        assert "Commander" in pack.body
        assert "typescript" in pack.tags

    def test_folder_pack(self, tmp_path):
        folder = tmp_path / "design-eng"
        folder.mkdir()
        (folder / "main.md").write_text(
            "---\nname: Design Eng\ndomain: design\n---\n\nTight spacing, 8px grid.\n"
        )
        pack = parse_preference_file(folder / "main.md")
        assert pack is not None
        assert pack.id == "design-eng"
        assert pack.domain == "design"


class TestActiveAndResolve:
    def test_activate_and_resolve(self, ai_dir, config):
        create_preference_pack(
            ai_dir / "preferences",
            "CLI Conventions",
            domain="cli",
            body="- Use tsup\n- Prefer pnpm\n",
            pack_id="cli",
        )
        activate_pack(config, "cli", global_scope=True)
        assert "cli" in load_active_pack_ids(ai_dir)

        packs = resolve_preference_packs(config)
        assert len(packs) == 1
        assert packs[0].id == "cli"

        deactivate_pack(config, "cli", global_scope=True)
        assert resolve_preference_packs(config) == []

    def test_project_active_overrides(self, ai_dir, tmp_path):
        create_preference_pack(
            ai_dir / "preferences",
            "CLI",
            body="- global cli\n",
            pack_id="cli",
        )
        proj = tmp_path / "app"
        proj.mkdir()
        (proj / ".ai" / "preferences").mkdir(parents=True)
        create_preference_pack(
            proj / ".ai" / "preferences",
            "CLI",
            body="- project cli flavor\n",
            pack_id="cli",
        )
        config = GlobalConfig(
            global_ai_dir=ai_dir,
            projects=[ProjectConfig(name="app", path=proj)],
        )
        activate_pack(config, "cli", project_path=proj)
        packs = resolve_preference_packs(config, project_name="app", project_path=proj)
        assert len(packs) == 1
        assert "project cli" in packs[0].body

    def test_session_extra_prefs(self, ai_dir, config):
        create_preference_pack(
            ai_dir / "preferences",
            "Design",
            domain="design",
            body="- 8px grid\n",
            pack_id="design",
        )
        # Not in active list, but passed as extra
        packs = resolve_preference_packs(config, extra=["design"])
        assert len(packs) == 1
        assert packs[0].id == "design"


class TestPull:
    def test_pull_local_file(self, ai_dir):
        src = ai_dir.parent / "taste.md"
        src.write_text("# Taste\n\n- Prefer vitest\n- lowercase -v flags\n")
        dest = ai_dir / "preferences"
        installed = pull_preference_pack(str(src), dest, pack_name="cli-awais", domain="cli")
        assert len(installed) == 1
        content = installed[0].read_text()
        assert "vitest" in content
        assert "id: cli-awais" in content
        assert "domain: cli" in content


class TestPrimerIntegration:
    def test_primer_includes_active_prefs(self, ai_dir, config):
        create_preference_pack(
            ai_dir / "preferences",
            "CLI Conventions",
            domain="cli",
            body="- Prefer Commander and tsup\n",
            pack_id="cli",
        )
        activate_pack(config, "cli", global_scope=True)
        primer = generate_primer(config)
        assert "Active Preference Packs" in primer
        assert "Commander" in primer
        assert "Hard rules" in primer or "hard rules" in primer.lower()

    def test_format_section_compact(self, ai_dir):
        pack = create_preference_pack(
            ai_dir / "preferences", "X", body="- a\n", pack_id="x"
        )
        parsed = parse_preference_file(pack)
        section = format_preferences_section([parsed], compact=True)
        assert parsed.id in section
        assert "Soft" in section or "soft" in section.lower()


class TestLoadFromDir:
    def test_empty(self, ai_dir):
        assert load_preferences_from_dir(ai_dir / "preferences") == []

    def test_loads_multiple(self, ai_dir):
        create_preference_pack(ai_dir / "preferences", "A", pack_id="a", body="- a\n")
        create_preference_pack(ai_dir / "preferences", "B", pack_id="b", body="- b\n")
        packs = load_preferences_from_dir(ai_dir / "preferences")
        assert {p.id for p in packs} == {"a", "b"}

    def test_lookup_does_not_cross_into_another_project(self, ai_dir, tmp_path):
        project_a = tmp_path / "a"
        project_b = tmp_path / "b"
        (project_a / ".ai" / "preferences").mkdir(parents=True)
        (project_b / ".ai" / "preferences").mkdir(parents=True)
        create_preference_pack(
            project_b / ".ai" / "preferences",
            "Only B",
            pack_id="only-b",
        )
        config = GlobalConfig(
            global_ai_dir=ai_dir,
            projects=[
                ProjectConfig(name="a", path=project_a),
                ProjectConfig(name="b", path=project_b),
            ],
        )

        assert _find_pack_or_local(
            config,
            "only-b",
            project_a,
            include_global=False,
        ) is None
