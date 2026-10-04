# Agent Skill 发现、加载与验收工程

## 2026-10：通用格式与本地严格策略

`discover_skill(..., profile="standard")` / `validate_skill_package(..., profile="standard")` 支持 `license`、`compatibility`、`metadata`、实验性的 `allowed-tools` 及额外资源目录；字段含义依据 [Agent Skills specification](https://agentskills.io/specification)。默认仍为 `strict`：只收 name/description、使用本项目目录/文件类型限制，并检查本地 UI 元数据。

两种 profile 都保留路径与大小约束，不执行脚本。这里的 standard 是格式检查＋本加载器安全限制，不是任意宿主兼容性认证；`allowed-tools` 也不授予程序实际权限。Python-only 脚本策略、`agents/openai.yaml` 要求和资源 allowlist 属于**本课程的宿主策略**，不是通用格式的强制规定。

```python
from pathlib import Path
from skill_lab.catalog import validate_skill_package
report = validate_skill_package(Path("../clickhouse-sql-review"), profile="standard")
print(report.valid, report.issues)
```

运行 `python -m pytest tests/test_catalog.py -q` 比较两个 profile；阅读 `catalog.py` 的 `discover_skill` 和 `validate_standard_format`。引入第三方 Skill 仍需人工审查内容、依赖与执行权限，格式正确不等于可信。

实际 Skill 位于上一级 [clickhouse-sql-review](../clickhouse-sql-review/SKILL.md)。本工程不只演示“读一个 Markdown”：它把目录发现、确定性路由、渐进披露、路径隔离、包静态校验和 SQL 安全 validator 分开实现，并为每层准备失败场景。

## 运行

```powershell
cd 11-Agent-Skills/skill-practice
python -m pip install -e ".[dev]"
python -m skill_lab.demo
python -m pytest -q
```

## 三阶段渐进披露

```text
启动阶段
  discover_skills(root)
  只读取每个 SKILL.md 的 YAML frontmatter
        ↓ 任务命中
指令阶段
  SkillLoader.load_instructions(name)
  加载该 Skill 的完整 SKILL.md
        ↓ 具体解释需要
资源阶段
  load_reference(name, "references/...")
  每次只加载正文明确链接的一份 reference
```

`SkillLoader.events` 记录每个阶段、相对路径和加载字节数，因此可以证明“启动时没有把所有 Skill/reference 常驻 Context”。脚本只在正文加载后通过 `resolve_script()` 解析；解析路径不等于自动执行。

## 目录发现与失败隔离

`SkillCatalog.from_root(...)` 会按目录名稳定排序并发现多个 Skill。一个包缺少 frontmatter、name 与目录不一致或 metadata 非法时，会进入 `CatalogSnapshot.issues`，不会让其他有效 Skill 一起消失。重复 name 也会被拒绝。

当前 `should_activate` 是 SQL Review Skill 的确定性练习路由器：同时要求 SQL/ClickHouse 信号和 review/检查信号，并覆盖“直接执行”“只生成、不检查”等负例。新 Skill 不能靠宽泛关键词自动激活，应补自己的正负例路由规则。

## 路径安全

reference/script 加载统一执行以下约束：

- 只接受 POSIX 相对路径，不接受绝对路径、反斜杠、`.` 或 `..`。
- reference 必须位于 `references/`，Python 脚本必须位于 `scripts/`。
- reference 必须由 SKILL.md 明确链接，脚本必须由正文明确提到。
- `resolve()` 后仍必须位于当前 Skill 根目录。
- 任一路径段是 symlink 都拒绝，避免包内链接跳到用户主目录或其他仓库。
- 对 frontmatter、SKILL.md 和 reference 设置独立大小上限。

这些限制针对的是第三方 Skill 供应链风险，不能靠 Prompt 中一句“不要访问外部文件”代替。

## Skill 包静态验收

`validate_skill_package(...)` 不执行脚本，只静态检查：

- frontmatter、name、description 和目录对应关系；
- frontmatter 只能包含 `name`、`description`，根目录不能混入非标准 `examples/` 等临时产物；
- Markdown 本地链接是否存在且未逃逸；
- `scripts/` 下 Python 是否能通过 AST 语法解析；
- `agents/openai.yaml` 是否为合法 mapping、UI 字符串是否加引号、description 长度以及 default prompt 是否显式包含 `$skill-name`；
- `assets/` 是否逐文件满足类型、大小、内部 Markdown 断链和 symlink 约束；
- 其他 resource 类型、文件大小和 symlink。

运行时发现只读 frontmatter；完整包验收读取全部资源。两者是不同阶段，不要为了“先验收过”就让所有资源常驻模型上下文。

## SQL validator 能力

[validate_sql.py](../clickhouse-sql-review/scripts/validate_sql.py) 使用 `sqlglot` 解析 ClickHouse AST，且绝不连接数据库。它检查：

- 空输入、长度、解析、多语句和根查询形态；
- tenant 表 allowlist 与表级 column allowlist；
- `SELECT *`、敏感列、外部 I/O/数据库和延迟函数；
- dev/staging/prod 不同的正整数 LIMIT，动态/超大 OFFSET；
- 禁止 query-level `SETTINGS`，避免 SQL 覆盖执行端资源策略；
- 指标字段与 `success_rate` 除法、`active_users` 去重计数等表达式形态；
- `FINAL`、dictionary access、JOIN、DISTINCT、窗口与生产无 WHERE 等成本 warning；
- `policy_version`、环境、已检查表列和 normalized SQL（仅 pass）审计字段。

`pass` 只代表“可进入执行侧 Guard”。数据库账号只读、重复授权、超时、扫描量、内存、并发和审计日志仍必须由执行服务落实。

## 测试覆盖

离线测试覆盖 93 个通过/拒绝/路由/包安全断言，包括：

- 多 Skill 目录发现与坏包隔离；
- frontmatter-only 发现、正文/reference 分阶段加载；
- `..`、绝对路径、反斜杠、未链接文件和 symlink；
- frontmatter 任意扩展、非标准 `examples/`、包内/asset 断链、asset 类型、Python 语法错误、YAML/资源和 `agents/openai.yaml` 契约检查；
- 12 条合法 SQL、30+ 条安全/形态拒绝、8 条指标冲突；
- 多错误聚合、环境 LIMIT 和成本 warning。

Windows 没有创建 symlink 权限时，对应一条测试会明确 skip；其余测试仍应通过。

## 建议阅读顺序

1. `../clickhouse-sql-review/SKILL.md`：触发后的流程、资源路由和边界。
2. `src/skill_lab/catalog.py`：目录发现、懒加载、路径安全和包校验。
3. `../clickhouse-sql-review/scripts/validate_sql.py`：确定性 SQL 安全边界。
4. `../clickhouse-sql-review/references/`：按失败类型/业务问题加载的资料。
5. `tests/test_catalog.py` 与 `tests/test_validator.py`：正例、负例和供应链失败场景。

## 真实模型实验

`tests_live/test_live_skill_explanation.py` 只让真实模型解释确定性 validator 的结果；测试要求模型不能把代码作出的 `reject` 改成 `pass`。配置继续使用仓库统一的 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY_ENV` 和对应密钥变量，不写死端点、模型或 key。见 [统一 live 配置](../../shared/README.md)：

```powershell
python -m pip install -e ".[dev,live]"
python -m pytest -q tests_live -m live
```
