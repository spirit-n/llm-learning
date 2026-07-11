# 11｜Agent Skills

**安排：** 第 5 周后半天，P1。

详细学习：[从零制作 SQL Review Skill](./01-SQL-Review-Skill实操.md)。

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
├── scripts/
├── references/
└── assets/
```

`SKILL.md` 至少包含 YAML frontmatter 的 `name`、`description`，正文写触发条件、步骤、边界、验证和输出约定。让 description 同时说明“做什么”和“什么时候用”。

## 本周作品：SQL Review Skill

- 输入：SQL、目标指标、用户权限、环境。
- 流程：解析 → 只读校验 → 库表/字段权限 → limit/timeout → 口径核对 → 风险报告。
- 资源：ClickHouse SQL 规则、敏感字段清单、指标口径模板。
- 脚本：确定性 SQL parser/validator，不把所有检查写成自然语言。
- 输出：pass/reject、原因、证据、建议修复；禁止自动执行。

## 验收

- 10 个正例、20 个反例；同一输入输出稳定。
- Skill 只加载需要的参考，避免把全部内容常驻 context。
- 说明哪些规则放 Skill，哪些必须固化在运行时 Guard 中。安全边界必须由代码执行，不能只写进 Skill。

## 资料怎么用

| 优先级 | 资料 | 它是干什么的 | 零基础怎么使用 |
|---|---|---|---|
| P0 | [Agent Skills Specification](https://openagentskills.dev/docs/specification) | 定义 Skill 文件夹、`SKILL.md`、YAML frontmatter、name/description 和可选目录的正式格式 | 先只读目录结构、必填 frontmatter 和命名规则，然后创建最小 Skill；高级 metadata 等真正需要时再查 |
| P1 | [NVIDIA Skills 示例](https://github.com/NVIDIA/skills) | NVIDIA 发布的真实 Skills，可观察企业如何组织指令、references 和 scripts | 先挑一个与你熟悉任务相近的 Skill，看 description 如何写触发条件；不要一次复制整个仓库，也要审查脚本副作用 |

阅读示例的目的不是模仿文字长度，而是看清三件事：何时触发、按什么步骤做、怎样验证结果。
