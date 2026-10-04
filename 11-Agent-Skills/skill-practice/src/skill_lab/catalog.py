"""Skill 目录发现、渐进加载、路径隔离和包校验。"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FRONTMATTER_MAX_BYTES = 16 * 1024
INSTRUCTIONS_MAX_BYTES = 128 * 1024
RESOURCE_MAX_BYTES = 256 * 1024
ASSET_MAX_BYTES = 5 * 1024 * 1024
ALLOWED_REFERENCE_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json"}
ALLOWED_FRONTMATTER_FIELDS = {"name", "description"}
STANDARD_FRONTMATTER_FIELDS = ALLOWED_FRONTMATTER_FIELDS | {
    "license", "compatibility", "metadata", "allowed-tools",
}
ValidationProfile = Literal["strict", "standard"]
ALLOWED_ROOT_ENTRIES = {"SKILL.md", "agents", "scripts", "references", "assets"}
ALLOWED_ASSET_SUFFIXES = {
    ".css",
    ".csv",
    ".docx",
    ".gif",
    ".htm",
    ".html",
    ".ico",
    ".j2",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".otf",
    ".pdf",
    ".png",
    ".pptx",
    ".svg",
    ".tmpl",
    ".ts",
    ".tsv",
    ".tsx",
    ".ttf",
    ".txt",
    ".webp",
    ".woff",
    ".woff2",
    ".xlsx",
    ".yaml",
    ".yml",
}
TEXT_ASSET_SUFFIXES = {
    ".css",
    ".csv",
    ".htm",
    ".html",
    ".j2",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".svg",
    ".tmpl",
    ".ts",
    ".tsv",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


class SkillCatalogError(ValueError):
    """Skill 包或目录不符合可安全加载的约束。"""


class ProgressiveDisclosureError(SkillCatalogError):
    """调用顺序跳过了渐进披露阶段。"""


class UnsafeSkillPath(SkillCatalogError):
    """资源路径可能逃逸 Skill 根目录或经过符号链接。"""


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    path: Path
    frontmatter_bytes: int
    license: str | None = None
    compatibility: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()
    allowed_tools: str | None = None


@dataclass(frozen=True)
class CatalogIssue:
    path: str
    code: str
    message: str


@dataclass(frozen=True)
class CatalogSnapshot:
    skills: tuple[SkillMetadata, ...]
    issues: tuple[CatalogIssue, ...]
    frontmatter_bytes_read: int


@dataclass(frozen=True)
class LoadEvent:
    stage: str
    skill_name: str
    relative_path: str
    bytes_loaded: int


@dataclass(frozen=True)
class SkillPackageReport:
    skill_name: str | None
    valid: bool
    issues: tuple[CatalogIssue, ...]
    checked_resources: tuple[str, ...]


def discover_skill(skill_dir: Path, *, profile: ValidationProfile = "strict") -> SkillMetadata:
    """只读 frontmatter；strict 是本地安全 profile，不是通用格式标准。"""

    _validate_profile(profile)
    if skill_dir.is_symlink():
        raise UnsafeSkillPath("Skill 目录不能是符号链接")
    skill_dir = skill_dir.resolve(strict=True)
    path = _safe_path(skill_dir, "SKILL.md", allowed_roots={"SKILL.md"}, require_file=True)
    metadata, bytes_read = _read_frontmatter(path)
    allowed_fields = ALLOWED_FRONTMATTER_FIELDS if profile == "strict" else STANDARD_FRONTMATTER_FIELDS
    unexpected_fields = sorted(set(metadata) - allowed_fields)
    if unexpected_fields:
        raise SkillCatalogError(
            ("strict profile 的 frontmatter 只允许 name/description，发现："
             if profile == "strict" else "标准未定义的 frontmatter 字段（扩展请放 metadata）：")
            + ", ".join(unexpected_fields)
        )
    name = metadata.get("name", "")
    description = metadata.get("description", "")
    if not isinstance(name, str) or len(name) > 64 or not NAME_PATTERN.fullmatch(name) or name != skill_dir.name:
        raise SkillCatalogError("Skill name 不合法或与目录名不一致")
    if not isinstance(description, str) or not description.strip():
        raise SkillCatalogError("Skill description 不能为空")
    if len(description) > 1_024:
        raise SkillCatalogError("Skill description 过长，无法作为轻量发现元数据")
    for key in ("license", "compatibility", "allowed-tools"):
        if key in metadata and (not isinstance(metadata[key], str) or not metadata[key].strip()):
            raise SkillCatalogError(f"{key} 必须是非空字符串")
    if len(metadata.get("compatibility", "")) > 500:
        raise SkillCatalogError("compatibility 不能超过 500 字符")
    extensions = metadata.get("metadata", {})
    if not isinstance(extensions, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in extensions.items()
    ):
        raise SkillCatalogError("metadata 必须是字符串键到字符串值的 mapping")
    return SkillMetadata(
        name=name,
        description=description.strip(),
        path=skill_dir,
        frontmatter_bytes=bytes_read,
        license=metadata.get("license"),
        compatibility=metadata.get("compatibility"),
        metadata=tuple(sorted(extensions.items())),
        allowed_tools=metadata.get("allowed-tools"),
    )


def discover_skills(root: Path, *, profile: ValidationProfile = "strict") -> CatalogSnapshot:
    """扫描一个目录下的 Skill；坏包会隔离到 issues，不影响其他包发现。"""

    _validate_profile(profile)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise SkillCatalogError(f"Skill root 不是目录：{root}")
    skills: list[SkillMetadata] = []
    issues: list[CatalogIssue] = []
    names: set[str] = set()

    for candidate in sorted(root.iterdir(), key=lambda value: value.name):
        if candidate.name.startswith(".") or not candidate.is_dir():
            continue
        if candidate.is_symlink():
            issues.append(CatalogIssue(str(candidate), "SYMLINK_SKILL_DIR", "拒绝通过符号链接发现 Skill"))
            continue
        if not (candidate / "SKILL.md").is_file():
            continue
        try:
            metadata = discover_skill(candidate, profile=profile)
        except (OSError, SkillCatalogError, yaml.YAMLError) as exc:
            issues.append(CatalogIssue(str(candidate), "INVALID_SKILL", str(exc)))
            continue
        if metadata.name in names:
            issues.append(CatalogIssue(str(candidate), "DUPLICATE_SKILL_NAME", metadata.name))
            continue
        names.add(metadata.name)
        skills.append(metadata)

    return CatalogSnapshot(
        skills=tuple(skills),
        issues=tuple(issues),
        frontmatter_bytes_read=sum(skill.frontmatter_bytes for skill in skills),
    )


class SkillCatalog:
    """Skill 元数据目录；启动阶段只持有轻量 frontmatter。"""

    def __init__(self, snapshot: CatalogSnapshot):
        self.snapshot = snapshot
        self._by_name = {skill.name: skill for skill in snapshot.skills}

    @classmethod
    def from_root(cls, root: Path, *, profile: ValidationProfile = "strict") -> "SkillCatalog":
        return cls(discover_skills(root, profile=profile))

    def metadata(self, name: str) -> SkillMetadata:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise SkillCatalogError(f"未发现 Skill：{name}") from exc

    def match(self, task: str) -> tuple[SkillMetadata, ...]:
        return tuple(skill for skill in self.snapshot.skills if should_activate(task, skill))


class SkillLoader:
    """在命中任务后加载正文，并在需要解释时才加载单个 reference。"""

    def __init__(self, catalog: SkillCatalog):
        self.catalog = catalog
        self._instructions: dict[str, str] = {}
        self._references: dict[tuple[str, str], str] = {}
        self._linked_resources: dict[str, set[str]] = {}
        self._events: list[LoadEvent] = []

    @property
    def events(self) -> tuple[LoadEvent, ...]:
        return tuple(self._events)

    def load_instructions(self, name: str) -> str:
        metadata = self.catalog.metadata(name)
        cached = self._instructions.get(name)
        if cached is not None:
            return cached
        path = _safe_path(metadata.path, "SKILL.md", allowed_roots={"SKILL.md"}, require_file=True)
        text, size = _read_bounded(path, INSTRUCTIONS_MAX_BYTES)
        self._instructions[name] = text
        self._linked_resources[name] = _extract_local_links(text)
        self._events.append(LoadEvent("instructions", name, "SKILL.md", size))
        return text

    def load_reference(self, name: str, relative_path: str) -> str:
        metadata = self.catalog.metadata(name)
        if name not in self._instructions:
            raise ProgressiveDisclosureError("必须先加载 SKILL.md，再按需加载 reference")
        normalized = _normalize_relative_path(relative_path)
        if not normalized.startswith("references/"):
            raise UnsafeSkillPath("reference 必须位于 references/ 目录")
        if normalized not in self._linked_resources[name]:
            raise UnsafeSkillPath("只能加载 SKILL.md 明确链接的 reference")
        cache_key = (name, normalized)
        if cache_key in self._references:
            return self._references[cache_key]
        path = _safe_path(metadata.path, normalized, allowed_roots={"references"}, require_file=True)
        if path.suffix.lower() not in ALLOWED_REFERENCE_SUFFIXES:
            raise UnsafeSkillPath(f"不允许加载该 reference 类型：{path.suffix}")
        text, size = _read_bounded(path, RESOURCE_MAX_BYTES)
        self._references[cache_key] = text
        self._events.append(LoadEvent("reference", name, normalized, size))
        return text

    def resolve_script(self, name: str, relative_path: str) -> Path:
        metadata = self.catalog.metadata(name)
        if name not in self._instructions:
            raise ProgressiveDisclosureError("必须先加载 SKILL.md，再解析脚本")
        normalized = _normalize_relative_path(relative_path)
        if not normalized.startswith("scripts/") or not normalized.endswith(".py"):
            raise UnsafeSkillPath("只允许解析 scripts/ 下的 Python 脚本")
        # 脚本必须在正文出现过，防止模型任意猜测并执行 Skill 包里的隐藏文件。
        if normalized not in self._instructions[name]:
            raise UnsafeSkillPath("只能解析 SKILL.md 明确提到的脚本")
        path = _safe_path(metadata.path, normalized, allowed_roots={"scripts"}, require_file=True)
        self._events.append(LoadEvent("script_resolved", name, normalized, 0))
        return path


def should_activate(task: str, metadata: SkillMetadata) -> bool:
    """当前练习的确定性路由器；生产可替换为分类器，但仍应保留负例集。"""

    text = task.casefold()
    if metadata.name != "clickhouse-sql-review":
        # 未知 Skill 不靠宽泛关键词误触发；应为它补独立且可测试的路由规则。
        return False
    sql_signal = any(word in text for word in ("sql", "clickhouse", "查询语句"))
    review_signal = any(word in text for word in ("review", "检查", "评审", "审查", "安全", "执行前", "修复"))
    review_negated = any(word in text for word in ("不需要检查", "不用检查", "无需评审", "不要审查"))
    execute_only = any(word in text for word in ("直接执行", "帮我运行", "连接数据库执行")) and not review_signal
    return sql_signal and review_signal and not review_negated and not execute_only


def load_instructions(metadata: SkillMetadata) -> str:
    """兼容单 Skill 示例的便捷函数；需要审计加载阶段时使用 SkillLoader。"""

    snapshot = CatalogSnapshot((metadata,), (), metadata.frontmatter_bytes)
    return SkillLoader(SkillCatalog(snapshot)).load_instructions(metadata.name)


def validate_skill_package(
    skill_dir: Path, *, profile: ValidationProfile = "strict"
) -> SkillPackageReport:
    """默认本地 strict 包验收；standard 只做格式与路径卫生，不授予执行权限。"""

    _validate_profile(profile)
    if profile == "standard":
        return validate_standard_format(skill_dir)
    issues: list[CatalogIssue] = []
    resources: list[str] = []
    skill_name: str | None = None
    try:
        metadata = discover_skill(skill_dir)
        skill_name = metadata.name
    except (OSError, SkillCatalogError, yaml.YAMLError) as exc:
        return SkillPackageReport(None, False, (CatalogIssue(str(skill_dir), "INVALID_SKILL", str(exc)),), ())

    # 本项目 strict profile 的目录 allowlist；通用 Agent Skills 标准允许额外目录。
    for entry in sorted(metadata.path.iterdir(), key=lambda value: value.name):
        if entry.name not in ALLOWED_ROOT_ENTRIES:
            issues.append(
                CatalogIssue(entry.name, "UNEXPECTED_ROOT_ENTRY", "strict profile 不允许此根目录项目")
            )

    # 校验器要看完整包，但与运行时发现阶段分开，避免把“静态验收”误当成“常驻加载”。
    catalog = SkillCatalog(CatalogSnapshot((metadata,), (), metadata.frontmatter_bytes))
    loader = SkillLoader(catalog)
    try:
        instructions = loader.load_instructions(metadata.name)
    except (OSError, SkillCatalogError) as exc:
        issues.append(CatalogIssue("SKILL.md", "INSTRUCTIONS_UNREADABLE", str(exc)))
        instructions = ""

    for raw in MARKDOWN_LINK.findall(instructions):
        target = raw.split("#", 1)[0].strip()
        if not target or "://" in target or target.startswith("#"):
            continue
        try:
            linked = _normalize_relative_path(target)
            _safe_path(
                metadata.path,
                linked,
                allowed_roots={"references", "scripts", "assets", "agents"},
                require_file=True,
            )
        except (OSError, SkillCatalogError) as exc:
            issues.append(CatalogIssue(target, "BROKEN_OR_UNSAFE_LINK", str(exc)))

    for directory, suffixes in (
        ("scripts", {".py"}),
        ("references", ALLOWED_REFERENCE_SUFFIXES),
        ("agents", {".yaml", ".yml"}),
        ("assets", ALLOWED_ASSET_SUFFIXES),
    ):
        base = metadata.path / directory
        if base.is_symlink():
            issues.append(CatalogIssue(directory, "SYMLINK_RESOURCE", "资源目录不能是符号链接"))
            continue
        if not base.exists():
            continue
        if not base.is_dir():
            issues.append(CatalogIssue(directory, "INVALID_RESOURCE", "资源目录名被普通文件占用"))
            continue
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(metadata.path).as_posix()
            if "__pycache__" in path.parts or path.name.startswith("."):
                continue
            if path.is_symlink():
                issues.append(CatalogIssue(relative, "SYMLINK_RESOURCE", "资源不能是符号链接"))
                continue
            if not path.is_file():
                continue
            resources.append(relative)
            if path.suffix.lower() not in suffixes:
                issues.append(CatalogIssue(relative, "UNEXPECTED_FILE_TYPE", path.suffix))
                continue
            try:
                suffix = path.suffix.lower()
                max_bytes = ASSET_MAX_BYTES if directory == "assets" else RESOURCE_MAX_BYTES
                if directory == "assets" and suffix not in TEXT_ASSET_SUFFIXES:
                    # 二进制资产不做 UTF-8 解码，但仍执行大小、类型和 symlink 约束。
                    size = path.stat().st_size
                    if size > max_bytes:
                        raise SkillCatalogError(f"文件超过大小限制：{size} > {max_bytes}")
                    continue
                text, _ = _read_bounded(path, max_bytes)
                if suffix == ".py":
                    ast.parse(text, filename=relative)
                elif suffix in {".yaml", ".yml"} and directory != "assets":
                    parsed = yaml.safe_load(text)
                    if not isinstance(parsed, dict):
                        raise ValueError("YAML 顶层必须是 mapping")
                    if relative == "agents/openai.yaml":
                        issues.extend(_validate_openai_yaml(parsed, text, metadata.name))
                if directory == "assets" and suffix == ".md":
                    issues.extend(_validate_asset_links(metadata.path, path, text))
            except (OSError, SyntaxError, ValueError, yaml.YAMLError) as exc:
                issues.append(CatalogIssue(relative, "INVALID_RESOURCE", str(exc)))

    return SkillPackageReport(skill_name, not issues, tuple(issues), tuple(resources))


def _validate_profile(profile: str) -> None:
    if profile not in {"strict", "standard"}:
        raise SkillCatalogError("profile 必须是 strict 或 standard")


def validate_standard_format(skill_dir: Path) -> SkillPackageReport:
    """通用 frontmatter/目录格式检查，并保留本加载器的路径和大小安全约束。

    不强加 Python-only、assets 类型或 agents/openai.yaml UI 契约；不运行脚本。
    合格仅表示格式可识别，不代表依赖可用、内容可信或可在任意宿主执行。
    """
    try:
        metadata = discover_skill(skill_dir, profile="standard")
        instructions, _ = _read_bounded(metadata.path / "SKILL.md", INSTRUCTIONS_MAX_BYTES)
    except (OSError, SkillCatalogError, yaml.YAMLError) as exc:
        return SkillPackageReport(None, False, (CatalogIssue(str(skill_dir), "INVALID_SKILL", str(exc)),), ())
    issues: list[CatalogIssue] = []
    resources: list[str] = []
    roots = {entry.name for entry in metadata.path.iterdir()}
    for path in sorted(metadata.path.rglob("*")):
        relative = path.relative_to(metadata.path).as_posix()
        if path.is_symlink():
            issues.append(CatalogIssue(relative, "SYMLINK_RESOURCE", "资源不能是符号链接"))
            continue
        if not path.is_file() or relative == "SKILL.md":
            continue
        try:
            safe = _safe_path(metadata.path, relative, allowed_roots=roots, require_file=True)
            if safe.stat().st_size > ASSET_MAX_BYTES:
                raise SkillCatalogError("资源超过本加载器大小上限")
            resources.append(relative)
        except (OSError, SkillCatalogError) as exc:
            issues.append(CatalogIssue(relative, "INVALID_RESOURCE", str(exc)))
    for raw in MARKDOWN_LINK.findall(instructions):
        target = raw.split("#", 1)[0].strip()
        if not target or "://" in target or target.startswith("#"):
            continue
        try:
            _safe_path(metadata.path, target, allowed_roots=roots, require_file=True)
        except (OSError, SkillCatalogError) as exc:
            issues.append(CatalogIssue(target, "BROKEN_OR_UNSAFE_LINK", str(exc)))
    return SkillPackageReport(metadata.name, not issues, tuple(issues), tuple(resources))


def _validate_asset_links(skill_root: Path, asset_path: Path, text: str) -> list[CatalogIssue]:
    """检查 Markdown 模板中的本地资产链接，仍禁止绝对路径和 `..` 穿越。"""

    issues: list[CatalogIssue] = []
    asset_parent = asset_path.parent.relative_to(skill_root).as_posix()
    for raw in MARKDOWN_LINK.findall(text):
        target = raw.split("#", 1)[0].strip()
        if not target or "://" in target or target.startswith("#"):
            continue
        relative = f"{asset_parent}/{target}"
        try:
            _safe_path(skill_root, relative, allowed_roots={"assets"}, require_file=True)
        except (OSError, SkillCatalogError) as exc:
            issues.append(
                CatalogIssue(
                    asset_path.relative_to(skill_root).as_posix(),
                    "BROKEN_ASSET_LINK",
                    f"{target}: {exc}",
                )
            )
    return issues


def _validate_openai_yaml(parsed: dict[str, object], raw: str, skill_name: str) -> list[CatalogIssue]:
    """校验 Skill UI 元数据的必要字段和显式调用示例。"""

    issues: list[CatalogIssue] = []
    interface = parsed.get("interface")
    if not isinstance(interface, dict):
        return [CatalogIssue("agents/openai.yaml", "INVALID_OPENAI_YAML", "缺少 interface mapping")]
    for field_name in ("display_name", "short_description", "default_prompt"):
        value = interface.get(field_name)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                CatalogIssue("agents/openai.yaml", "INVALID_OPENAI_YAML", f"{field_name} 必须是非空字符串")
            )
    short_description = interface.get("short_description")
    if isinstance(short_description, str) and not 25 <= len(short_description) <= 64:
        issues.append(
            CatalogIssue("agents/openai.yaml", "INVALID_OPENAI_YAML", "short_description 长度必须为 25 到 64")
        )
    default_prompt = interface.get("default_prompt")
    if isinstance(default_prompt, str) and f"${skill_name}" not in default_prompt:
        issues.append(
            CatalogIssue(
                "agents/openai.yaml",
                "INVALID_OPENAI_YAML",
                f"default_prompt 必须显式包含 ${skill_name}",
            )
        )

    # 规范要求 UI 字符串全部加引号，避免 YAML 对 true/null/# 等值产生隐式类型或截断。
    ui_fields = {"display_name", "short_description", "default_prompt"}
    for line in raw.splitlines():
        stripped = line.strip()
        key, separator, value = stripped.partition(":")
        if separator and key in ui_fields:
            value = value.strip()
            if len(value) < 2 or value[0] not in {'"', "'"} or value[-1] != value[0]:
                issues.append(
                    CatalogIssue("agents/openai.yaml", "UNQUOTED_UI_STRING", f"{key} 必须显式加引号")
                )
    return issues


def _read_frontmatter(path: Path) -> tuple[dict[str, object], int]:
    raw_lines: list[str] = []
    bytes_read = 0
    with path.open("r", encoding="utf-8", newline=None) as handle:
        first = handle.readline()
        bytes_read += len(first.encode("utf-8"))
        if first.strip() != "---":
            raise SkillCatalogError("SKILL.md 缺少 YAML frontmatter")
        for line in handle:
            bytes_read += len(line.encode("utf-8"))
            if bytes_read > FRONTMATTER_MAX_BYTES:
                raise SkillCatalogError("YAML frontmatter 过大")
            if line.strip() == "---":
                break
            raw_lines.append(line)
        else:
            raise SkillCatalogError("YAML frontmatter 缺少结束分隔符")
    parsed = yaml.safe_load("".join(raw_lines))
    if not isinstance(parsed, dict):
        raise SkillCatalogError("YAML frontmatter 顶层必须是 mapping")
    if not all(isinstance(key, str) for key in parsed):
        raise SkillCatalogError("YAML frontmatter 字段名必须是字符串")
    return parsed, bytes_read


def _read_bounded(path: Path, max_bytes: int) -> tuple[str, int]:
    size = path.stat().st_size
    if size > max_bytes:
        raise SkillCatalogError(f"文件超过大小限制：{size} > {max_bytes}")
    return path.read_text(encoding="utf-8"), size


def _extract_local_links(instructions: str) -> set[str]:
    result: set[str] = set()
    for raw in MARKDOWN_LINK.findall(instructions):
        target = raw.split("#", 1)[0].strip()
        if not target or "://" in target or target.startswith("#"):
            continue
        try:
            result.add(_normalize_relative_path(target))
        except UnsafeSkillPath:
            # 非法链接交给包校验器报告；运行时永远不会将其加入允许列表。
            continue
    return result


def _normalize_relative_path(value: str) -> str:
    if not value or "\\" in value:
        raise UnsafeSkillPath("资源路径必须使用非空 POSIX 相对路径")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeSkillPath("资源路径不能是绝对路径或包含 . / ..")
    return path.as_posix()


def _safe_path(root: Path, relative: str, *, allowed_roots: set[str], require_file: bool) -> Path:
    normalized = _normalize_relative_path(relative)
    parts = PurePosixPath(normalized).parts
    if parts[0] not in allowed_roots:
        raise UnsafeSkillPath(f"路径不在允许目录：{parts[0]}")
    candidate = root.joinpath(*parts)

    # resolve + relative_to 防目录穿越；逐段拒绝 symlink 防止目录内链接跳到包外。
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise UnsafeSkillPath(f"路径经过符号链接：{normalized}")
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=require_file)
    except OSError as exc:
        raise UnsafeSkillPath(f"资源不存在或不可访问：{normalized}") from exc
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise UnsafeSkillPath(f"路径逃逸 Skill 根目录：{normalized}") from exc
    if require_file and not resolved.is_file():
        raise UnsafeSkillPath(f"资源不是普通文件：{normalized}")
    return resolved
