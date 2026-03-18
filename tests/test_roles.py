"""Tests for dotai.roles parsing."""

from dotai.roles import load_all_roles, load_roles_from_dir, parse_role_file


class TestParseRoleFile:
    def test_full_role(self, sample_role_file):
        role = parse_role_file(sample_role_file)
        assert role is not None
        assert role.name == "Test Reviewer"
        assert role.description == "A reviewer for tests"
        assert role.id == "test-reviewer"
        assert "review" in role.tags
        assert "testing" in role.tags
        assert "code for correctness" in role.persona
        assert len(role.principles) == 2
        assert "Always check edge cases" in role.principles
        assert len(role.anti_patterns) == 2
        assert role.scope == "global"

    def test_nonexistent_file(self, tmp_path):
        assert parse_role_file(tmp_path / "nope.md") is None

    def test_no_frontmatter(self, tmp_path):
        path = tmp_path / "bare.md"
        path.write_text("You are a helpful assistant.\n\n## Principles\n\n- Be helpful\n")
        role = parse_role_file(path)
        assert role is not None
        assert role.name == "Bare"  # derived from filename
        assert "Be helpful" in role.principles

    def test_auto_description_from_persona(self, tmp_path):
        path = tmp_path / "short.md"
        path.write_text("---\nname: Short\n---\n\nYou are a brief persona.\n")
        role = parse_role_file(path)
        assert role.description == "You are a brief persona"


class TestLoadRolesFromDir:
    def test_loads_multiple(self, ai_dir):
        (ai_dir / "roles" / "a.md").write_text("---\nname: Alpha\ndescription: A\n---\nPersona A.\n")
        (ai_dir / "roles" / "b.md").write_text("---\nname: Beta\ndescription: B\n---\nPersona B.\n")
        roles = load_roles_from_dir(ai_dir / "roles")
        assert len(roles) == 2
        names = {r.name for r in roles}
        assert names == {"Alpha", "Beta"}

    def test_empty_dir(self, ai_dir):
        assert load_roles_from_dir(ai_dir / "roles") == []

    def test_missing_dir(self, tmp_path):
        assert load_roles_from_dir(tmp_path / "nonexistent") == []


class TestLoadAllRoles:
    def test_global_and_project(self, ai_dir, tmp_path):
        from dotai.models import GlobalConfig, ProjectConfig

        (ai_dir / "roles" / "global-role.md").write_text(
            "---\nname: Global Role\ndescription: G\n---\nGlobal.\n"
        )
        proj = tmp_path / "proj"
        proj.mkdir()
        proj_roles = proj / ".ai" / "roles"
        proj_roles.mkdir(parents=True)
        (proj_roles / "proj-role.md").write_text(
            "---\nname: Project Role\ndescription: P\n---\nProject.\n"
        )

        config = GlobalConfig(
            global_ai_dir=ai_dir,
            projects=[ProjectConfig(name="proj", path=proj)],
        )
        roles = load_all_roles(config)
        assert len(roles) == 2
        scopes = {r.scope for r in roles}
        assert "global" in scopes
        assert "proj" in scopes
