"""Core data models for the ~/.ai/ knowledge system."""

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    ROOT = "root"
    CATEGORY = "category"
    PROJECT = "project"
    DOCUMENT = "document"
    SECTION = "section"
    ENTRY = "entry"
    SKILL = "skill"
    TOOL = "tool"
    ROLE = "role"
    RULE = "rule"


class SkillCategory(str, Enum):
    """Skill categories inspired by real-world usage patterns.

    Helps organize skills by purpose so agents (and humans) can quickly
    find the right skill for the job.
    """

    REFERENCE = "reference"          # Library/CLI documentation lookups
    VERIFICATION = "verification"    # Testing, validation, type-checking
    DATA = "data"                    # Dashboards, queries, monitoring
    WORKFLOW = "workflow"            # Multi-step automation
    SCAFFOLDING = "scaffolding"     # Boilerplate / code generation
    CODE_QUALITY = "code-quality"   # Review, linting, style enforcement
    DEPLOYMENT = "deployment"        # CI/CD, release, ship
    DEBUGGING = "debugging"          # Investigation, root-cause analysis
    MAINTENANCE = "maintenance"      # Operational procedures, migrations


class Role(BaseModel):
    """A reusable cognitive mode / persona for AI agents."""

    id: str
    name: str
    description: str
    persona: str = ""  # The full persona prompt
    principles: list[str] = Field(default_factory=list)
    anti_patterns: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    file_path: Path | None = None
    scope: str = "global"

    def to_prompt(self) -> str:
        """Generate the full role prompt for LLM injection."""
        lines = [self.persona]

        if self.principles:
            lines.append("")
            lines.append("## Principles")
            for p in self.principles:
                lines.append(f"- {p}")

        if self.anti_patterns:
            lines.append("")
            lines.append("## Anti-patterns (avoid these)")
            for a in self.anti_patterns:
                lines.append(f"- {a}")

        return "\n".join(lines)


class Rule(BaseModel):
    """A structured coding rule that agents can parse and enforce."""

    id: str
    name: str
    description: str
    enabled: bool = Field(default=True, description="Whether this rule is active")
    tags: list[str] = Field(default_factory=list)
    globs: list[str] = Field(default_factory=list, description="File patterns this rule applies to (e.g. *.tsx)")
    body: str = ""  # The full rule content agents should follow
    file_path: Path | None = None
    scope: str = "global"

    def to_prompt(self) -> str:
        """Generate the rule prompt for LLM injection."""
        lines = [f"### Rule: {self.name}"]
        lines.append(f"_{self.description}_")
        if self.globs:
            lines.append(f"**Applies to:** {', '.join(self.globs)}")
        lines.append("")
        lines.append(self.body)
        return "\n".join(lines)


class Skill(BaseModel):
    """A reusable AI skill/workflow.

    Skills can be either single markdown files or folder-based packages:

    Single file:  ~/.ai/skills/review.md
    Folder-based: ~/.ai/skills/deploy/
                    main.md        # Skill definition
                    scripts/       # Helper scripts (shell, python)
                    assets/        # Templates, configs, reference docs
                    config.json    # User-specific configuration
    """

    id: str
    name: str
    description: str
    category: SkillCategory | None = Field(None, description="Skill category for organization")
    trigger: str | None = Field(None, description="Slash command or trigger phrase")
    role: str | None = Field(None, description="Role ID to adopt when running this skill")
    allowed_tools: list[str] = Field(default_factory=list, description="Tools the agent may use")
    inputs: list[dict] = Field(default_factory=list, description="Input parameters")
    steps: list[str] = Field(default_factory=list, description="Execution steps")
    examples: list[str] = Field(default_factory=list)
    gotchas: list[str] = Field(default_factory=list, description="Common failure points and pitfalls")
    context: list[str] = Field(default_factory=list, description="Contexts where this skill activates (e.g. production, ci, local)")
    tags: list[str] = Field(default_factory=list)
    file_path: Path | None = None
    assets_dir: Path | None = Field(None, description="Directory containing scripts/assets for folder-based skills")
    config: dict = Field(default_factory=dict, description="User-specific configuration from config.json")
    scope: str = "global"  # "global" or project name
    source: str = ""  # Where this skill was installed from (git URL, local path, or "seed")
    raw_body: str = ""  # Full markdown body for runbook-style skills

    @property
    def is_folder_skill(self) -> bool:
        """Whether this skill is a folder-based package."""
        return self.assets_dir is not None

    @property
    def scripts(self) -> list[Path]:
        """List helper scripts in the skill's scripts/ directory."""
        if not self.assets_dir:
            return []
        scripts_dir = self.assets_dir / "scripts"
        if not scripts_dir.exists():
            return []
        return sorted(scripts_dir.iterdir())

    def to_prompt(self, resolved_role: Role | None = None) -> str:
        """Generate the full prompt for LLM execution."""
        lines = []

        # Inject role persona if available
        if resolved_role:
            lines.append(resolved_role.to_prompt())
            lines.append("")
            lines.append("---")
            lines.append("")

        lines.append(f"# Skill: {self.name}")
        lines.append("")
        lines.append(f"**Description:** {self.description}")
        lines.append("")

        if self.category:
            lines.append(f"**Category:** {self.category.value}")
            lines.append("")

        if self.allowed_tools:
            lines.append(f"**Allowed tools:** {', '.join(self.allowed_tools)}")
            lines.append("")

        if self.context:
            lines.append(f"**Active in:** {', '.join(self.context)}")
            lines.append("")

        if self.inputs:
            lines.append("## Inputs")
            for inp in self.inputs:
                required = "(required)" if inp.get("required") else "(optional)"
                lines.append(f"- `{inp['name']}` {required}: {inp.get('description', '')}")
            lines.append("")

        if self.gotchas:
            lines.append("## Gotchas")
            lines.append("")
            lines.append("Common failure points — pay extra attention to these:")
            lines.append("")
            for gotcha in self.gotchas:
                lines.append(f"- ⚠️ {gotcha}")
            lines.append("")

        if self.raw_body:
            # Runbook-style: include full markdown body
            lines.append(self.raw_body)
        elif self.steps:
            lines.append("## Steps")
            for i, step in enumerate(self.steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        if self.examples:
            lines.append("## Examples")
            for ex in self.examples:
                lines.append(f"- {ex}")

        # Reference helper scripts if folder-based
        if self.is_folder_skill and self.scripts:
            lines.append("")
            lines.append("## Helper Scripts")
            lines.append("")
            lines.append("The following scripts are available in this skill's package:")
            for script in self.scripts:
                lines.append(f"- `{script.name}` — run with `bash {script}`")

        # Include user config if set
        if self.config:
            lines.append("")
            lines.append("## Configuration")
            lines.append("")
            for key, value in self.config.items():
                lines.append(f"- **{key}:** {value}")

        return "\n".join(lines)


class KnowledgeNode(BaseModel):
    """A node in the hierarchical knowledge tree."""

    id: str = Field(..., description="Unique identifier for this node")
    name: str = Field(..., description="Human-readable name")
    node_type: NodeType = Field(..., description="Type of this node")
    summary: str | None = Field(None, description="Brief description for LLM reasoning")

    file_path: Path | None = Field(None, description="Path to the source file")
    start_line: int | None = Field(None, description="Start line in file (for sections)")
    end_line: int | None = Field(None, description="End line in file (for sections)")

    tags: list[str] = Field(default_factory=list, description="Semantic tags for filtering")
    metadata: dict = Field(default_factory=dict, description="Arbitrary metadata")

    children: list["KnowledgeNode"] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def find_by_id(self, node_id: str) -> "KnowledgeNode | None":
        if self.id == node_id:
            return self
        for child in self.children:
            result = child.find_by_id(node_id)
            if result:
                return result
        return None

    def find_by_tag(self, tag: str) -> list["KnowledgeNode"]:
        results = []
        if tag in self.tags:
            results.append(self)
        for child in self.children:
            results.extend(child.find_by_tag(tag))
        return results

    def find_by_type(self, node_type: NodeType) -> list["KnowledgeNode"]:
        results = []
        if self.node_type == node_type:
            results.append(self)
        for child in self.children:
            results.extend(child.find_by_type(node_type))
        return results

    def find_by_text(self, query: str) -> list["KnowledgeNode"]:
        """Search nodes by keyword across name, summary, tags, and metadata."""
        results = []
        q = query.lower()
        searchable = " ".join([
            self.name.lower(),
            (self.summary or "").lower(),
            " ".join(self.tags).lower(),
            " ".join(str(v) for v in self.metadata.values()).lower(),
        ])
        if q in searchable:
            results.append(self)
        for child in self.children:
            results.extend(child.find_by_text(query))
        return results

    def to_toc(self, indent: int = 0) -> str:
        """Generate a table-of-contents style representation."""
        prefix = "  " * indent
        type_icon = {
            NodeType.ROOT: "📚",
            NodeType.CATEGORY: "📁",
            NodeType.PROJECT: "🗂️",
            NodeType.DOCUMENT: "📄",
            NodeType.SECTION: "📑",
            NodeType.ENTRY: "•",
            NodeType.TOOL: "🔧",
            NodeType.SKILL: "⚡",
            NodeType.ROLE: "🎭",
        }.get(self.node_type, "•")

        lines = [f"{prefix}{type_icon} [{self.id}] {self.name}"]
        if self.summary:
            lines.append(f"{prefix}   └─ {self.summary}")

        for child in self.children:
            lines.append(child.to_toc(indent + 1))

        return "\n".join(lines)

    def to_compact_json(self) -> dict:
        """Compact JSON for LLM context - omits empty fields."""
        data = {"id": self.id, "name": self.name, "type": self.node_type.value}
        if self.summary:
            data["summary"] = self.summary
        if self.file_path:
            data["file"] = str(self.file_path)
        if self.tags:
            data["tags"] = self.tags
        if self.children:
            data["children"] = [c.to_compact_json() for c in self.children]
        return data


class ProjectConfig(BaseModel):
    """Configuration for a registered project."""

    name: str
    path: Path
    ai_dir: Path = Field(default=Path(".ai"))
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    disabled_rules: list[str] = Field(default_factory=list, description="Global rule IDs to skip in this project")

    @property
    def full_ai_path(self) -> Path:
        return self.path / self.ai_dir

    @property
    def rules_path(self) -> Path:
        return self.full_ai_path / "rules"

    @property
    def skills_path(self) -> Path:
        return self.full_ai_path / "skills"

    @property
    def roles_path(self) -> Path:
        return self.full_ai_path / "roles"


class GlobalConfig(BaseModel):
    """Global configuration for the ~/.ai/ knowledge system."""

    version: str = "1.0.0"
    global_ai_dir: Path = Field(default=Path.home() / ".ai")
    projects: list[ProjectConfig] = Field(default_factory=list)

    @property
    def global_rules_path(self) -> Path:
        return self.global_ai_dir / "rules"

    @property
    def global_skills_path(self) -> Path:
        return self.global_ai_dir / "skills"

    @property
    def global_roles_path(self) -> Path:
        return self.global_ai_dir / "roles"

    def get_project(self, name: str) -> ProjectConfig | None:
        return next((p for p in self.projects if p.name == name), None)

    def add_project(self, project: ProjectConfig) -> None:
        existing = self.get_project(project.name)
        if existing:
            self.projects.remove(existing)
        self.projects.append(project)
