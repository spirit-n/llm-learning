# 11｜Agent Skills

**安排：** 第 5 周后半天，P1。

详细学习：[从零制作 SQL Review Skill](./01-SQL-Review-Skill实操.md)。

本章作品：[clickhouse-sql-review](./clickhouse-sql-review/SKILL.md)，配套加载与验收工程：[skill-practice](./skill-practice/README.md)。Skill 包含标准 frontmatter、UI 元数据、确定性 SQL validator 和按需 references；工程还实现多目录发现、渐进披露审计、路径逃逸/symlink 防护、包静态验收，以及 93 条离线断言。

快速开始：

```powershell
cd 11-Agent-Skills/skill-practice
python -m pip install -e ".[dev]"
python -m skill_lab.demo
python -m pytest -q
```

## 零基础前置

会创建文件夹和 Markdown 文件即可开始。YAML frontmatter 是 `SKILL.md` 顶部两条 `---` 之间的结构化说明；第一次只写 `name` 和 `description`，不用研究全部可选字段。

## 与 Prompt、RAG、Tool 的区别

- Prompt：当前一次交互的指令。
- RAG：按需检索事实与知识。
- Tool：执行动作或读取外部系统。
- Skill：把某类任务的流程、规则、脚本、参考和模板封装为可复用能力。

## 标准结构

```text
clickhouse-sql-review/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
├── references/
└── assets/
```

当前 Skill Creator 规范下，`SKILL.md` 的 YAML frontmatter 只允许 `name`、`description`，不要随意加入 `version`、`metadata` 等自定义字段；正文写步骤、边界、验证和输出约定，让 description 同时说明“做什么”和“什么时候用”。根目录只使用 `agents/`、`scripts/`、`references/`、`assets/` 这些标准资源目录，生成器临时产生的 `examples/` 不应进入最终包。

启动时不要读取所有 Skill 正文。正确顺序是：只发现所有 `name`/`description` → 任务命中一个 Skill 后加载其 `SKILL.md` → 只有当前结论需要时才加载正文明确链接的一份 reference。加载器应记录阶段和字节数，才能证明 progressive disclosure 确实发生了。

## 本周作品：SQL Review Skill

- 输入：SQL、目标指标、用户权限、环境。
- 流程：解析 → 只读校验 → 库表/字段权限 → limit/timeout → 口径核对 → 风险报告。
- 资源：ClickHouse SQL 规则、敏感字段清单、指标口径模板。
- 脚本：确定性 SQL AST validator，检查 tenant 表/列、环境 LIMIT/OFFSET、危险函数、query settings 和指标表达式，不把安全检查写成自然语言。
- 输出：pass/reject、原因、证据、建议修复；禁止自动执行。

## 验收

- 10 个正例、20 个反例；同一输入输出稳定。
- Skill 只加载需要的参考，避免把全部内容常驻 context。
- 绝对路径、`..`、反斜杠、未链接资源和 symlink 逃逸都被代码拒绝；坏 Skill 包不会影响其他包发现。
- 包校验器检查严格 frontmatter、标准根目录、断链、Python AST、YAML、assets 类型/大小/symlink 和资源类型，但绝不执行第三方脚本。
- 说明哪些规则放 Skill，哪些必须固化在运行时 Guard 中。安全边界必须由代码执行，不能只写进 Skill。

## 资料怎么用

| 优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P0 | [Agent Skills Specification](https://openagentskills.dev/docs/specification) | 定义 Skill 文件夹、`SKILL.md`、YAML frontmatter、name/description 和可选目录的正式格式 | 先只读目录结构、必填 frontmatter 和命名规则，然后创建最小 Skill；高级 metadata 等真正需要时再查 |
| P1 | [NVIDIA Skills 示例](https://github.com/NVIDIA/skills) | NVIDIA 发布的真实 Skills，可观察企业如何组织指令、references 和 scripts | 先挑一个与你熟悉任务相近的 Skill，看 description 如何写触发条件；不要一次复制整个仓库，也要审查脚本副作用 |

阅读示例的目的不是模仿文字长度，而是看清三件事：何时触发、按什么步骤做、怎样验证结果。
