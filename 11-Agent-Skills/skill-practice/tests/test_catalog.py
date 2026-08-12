from pathlib import Path

import pytest

from skill_lab.catalog import (
    ProgressiveDisclosureError,
    SkillCatalog,
    SkillLoader,
    UnsafeSkillPath,
    discover_skill,
    discover_skills,
    load_instructions,
    should_activate,
    validate_skill_package,
)


def make_skill(root: Path, name: str, *, body: str = "# Demo\n", description: str = "Review demo tasks.") -> Path:
    directory = root / name
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}",
        encoding="utf-8",
    )
    return directory


def test_directory_discovery_reads_frontmatter_not_full_body(skill_dir):
    catalog = SkillCatalog.from_root(skill_dir.parent)
    metadata = catalog.metadata("clickhouse-sql-review")
    assert metadata.name == "clickhouse-sql-review"
    assert "ClickHouse" in metadata.description
    assert catalog.snapshot.frontmatter_bytes_read == metadata.frontmatter_bytes
    assert metadata.frontmatter_bytes < (skill_dir / "SKILL.md").stat().st_size


def test_bad_skill_is_isolated_without_hiding_valid_skill(tmp_path):
    make_skill(tmp_path, "valid-skill")
    bad = tmp_path / "bad-skill"
    bad.mkdir()
    (bad / "SKILL.md").write_text("# missing frontmatter", encoding="utf-8")
    snapshot = discover_skills(tmp_path)
    assert [skill.name for skill in snapshot.skills] == ["valid-skill"]
    assert snapshot.issues[0].code == "INVALID_SKILL"


@pytest.mark.parametrize("extra_field", ["version: 1", "metadata: {}", "license: MIT"])
def test_frontmatter_rejects_fields_outside_name_and_description(tmp_path, extra_field):
    skill = make_skill(tmp_path, "strict-skill")
    skill_file = skill / "SKILL.md"
    text = skill_file.read_text(encoding="utf-8")
    skill_file.write_text(text.replace("description:", f"{extra_field}\ndescription:"), encoding="utf-8")

    with pytest.raises(ValueError, match="只允许 name/description"):
        discover_skill(skill)

    report = validate_skill_package(skill)
    assert report.valid is False
    assert report.issues[0].code == "INVALID_SKILL"


@pytest.mark.parametrize(
    "task",
    [
        "帮我写一封邮件",
        "解释 RAG",
        "运行 Python 测试",
        "画一个架构图",
        "总结这篇文章",
        "直接执行这条 SQL",
        "帮我生成一个 SQL，不需要检查",
    ],
)
def test_tasks_outside_review_boundary_do_not_trigger(skill_dir, task):
    assert should_activate(task, discover_skill(skill_dir)) is False


@pytest.mark.parametrize(
    "task",
    [
        "执行前检查 ClickHouse SQL 安全",
        "review this SQL before execution",
        "修复这条 ClickHouse 查询语句的权限问题",
    ],
)
def test_sql_review_tasks_trigger(skill_dir, task):
    assert should_activate(task, discover_skill(skill_dir)) is True


def test_loader_enforces_progressive_disclosure_and_records_each_stage(skill_dir):
    loader = SkillLoader(SkillCatalog.from_root(skill_dir.parent))
    assert loader.events == ()
    with pytest.raises(ProgressiveDisclosureError):
        loader.load_reference("clickhouse-sql-review", "references/sensitive-columns.md")

    instructions = loader.load_instructions("clickhouse-sql-review")
    assert "Run the deterministic review" in instructions
    assert [event.stage for event in loader.events] == ["instructions"]

    reference = loader.load_reference("clickhouse-sql-review", "references/sensitive-columns.md")
    assert "customer_email" in reference
    assert loader.load_reference("clickhouse-sql-review", "references/sensitive-columns.md") == reference
    script = loader.resolve_script("clickhouse-sql-review", "scripts/validate_sql.py")
    assert script.name == "validate_sql.py"
    assert [event.stage for event in loader.events] == ["instructions", "reference", "script_resolved"]
    assert loader.events[1].bytes_loaded > 0


def test_instruction_compatibility_helper_still_loads_body(skill_dir):
    assert "Preserve runtime boundaries" in load_instructions(discover_skill(skill_dir))


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../SKILL.md",
        "references/../../SKILL.md",
        "references\\sensitive-columns.md",
        "C:/Windows/win.ini",
        "/etc/passwd",
        "scripts/validate_sql.py",
    ],
)
def test_reference_loader_rejects_path_escape_or_wrong_resource_class(skill_dir, unsafe_path):
    loader = SkillLoader(SkillCatalog.from_root(skill_dir.parent))
    loader.load_instructions("clickhouse-sql-review")
    with pytest.raises(UnsafeSkillPath):
        loader.load_reference("clickhouse-sql-review", unsafe_path)


def test_reference_must_be_explicitly_linked_from_skill(skill_dir):
    hidden = skill_dir / "references" / "hidden.md"
    hidden.write_text("should not load", encoding="utf-8")
    try:
        loader = SkillLoader(SkillCatalog.from_root(skill_dir.parent))
        loader.load_instructions("clickhouse-sql-review")
        with pytest.raises(UnsafeSkillPath, match="明确链接"):
            loader.load_reference("clickhouse-sql-review", "references/hidden.md")
    finally:
        hidden.unlink()


def test_package_validator_checks_links_python_and_yaml(skill_dir):
    report = validate_skill_package(skill_dir)
    assert report.valid is True
    assert report.issues == ()
    assert "scripts/validate_sql.py" in report.checked_resources
    assert "agents/openai.yaml" in report.checked_resources


def test_package_validator_reports_broken_link_and_python_syntax(tmp_path):
    skill = make_skill(
        tmp_path,
        "broken-skill",
        body="Read [missing](references/missing.md). Run `scripts/bad.py`.",
    )
    scripts = skill / "scripts"
    scripts.mkdir()
    (scripts / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    report = validate_skill_package(skill)
    assert report.valid is False
    assert {issue.code for issue in report.issues} == {"BROKEN_OR_UNSAFE_LINK", "INVALID_RESOURCE"}


def test_nonstandard_examples_directory_is_not_a_legal_skill_resource_root(tmp_path):
    skill = make_skill(
        tmp_path,
        "examples-skill",
        body="Read [sample](examples/sample.md).",
    )
    examples = skill / "examples"
    examples.mkdir()
    (examples / "sample.md").write_text("temporary generator sample", encoding="utf-8")

    report = validate_skill_package(skill)

    assert report.valid is False
    assert {issue.code for issue in report.issues} == {
        "UNEXPECTED_ROOT_ENTRY",
        "BROKEN_OR_UNSAFE_LINK",
    }
    assert "examples/sample.md" not in report.checked_resources


def test_assets_are_traversed_and_markdown_links_are_checked(tmp_path):
    skill = make_skill(
        tmp_path,
        "asset-skill",
        body="Copy [the report template](assets/report.md).",
    )
    assets = skill / "assets"
    assets.mkdir()
    (assets / "report.md").write_text("![logo](logo.svg)\n", encoding="utf-8")
    (assets / "logo.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")

    report = validate_skill_package(skill)

    assert report.valid is True
    assert {"assets/report.md", "assets/logo.svg"}.issubset(report.checked_resources)


def test_assets_reject_unsupported_type_and_broken_internal_link(tmp_path):
    skill = make_skill(
        tmp_path,
        "unsafe-assets",
        body="Copy [the template](assets/report.md).",
    )
    assets = skill / "assets"
    assets.mkdir()
    (assets / "report.md").write_text("[missing](missing.svg)\n", encoding="utf-8")
    (assets / "payload.exe").write_bytes(b"MZ")

    report = validate_skill_package(skill)

    assert report.valid is False
    assert {issue.code for issue in report.issues} == {
        "BROKEN_ASSET_LINK",
        "UNEXPECTED_FILE_TYPE",
    }


def test_package_validator_checks_openai_ui_metadata_contract(tmp_path):
    skill = make_skill(tmp_path, "ui-skill")
    agents = skill / "agents"
    agents.mkdir()
    (agents / "openai.yaml").write_text(
        "interface:\n"
        "  display_name: UI Skill\n"
        "  short_description: short\n"
        '  default_prompt: "Review this input."\n',
        encoding="utf-8",
    )
    report = validate_skill_package(skill)
    codes = {issue.code for issue in report.issues}
    assert "INVALID_OPENAI_YAML" in codes
    assert "UNQUOTED_UI_STRING" in codes


def test_symlinked_reference_is_rejected_when_platform_allows_it(skill_dir, tmp_path):
    target = tmp_path / "outside.md"
    target.write_text("outside", encoding="utf-8")
    link = skill_dir / "references" / "linked.md"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("当前 Windows 配置不允许创建 symlink")
    try:
        # 临时 SKILL 不链接此文件，但包校验仍应发现供应链风险。
        report = validate_skill_package(skill_dir)
        assert any(issue.code == "SYMLINK_RESOURCE" for issue in report.issues)
    finally:
        link.unlink()
