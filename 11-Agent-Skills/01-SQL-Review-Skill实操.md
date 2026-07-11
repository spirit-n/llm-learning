# 从零制作 SQL Review Skill

## 1. 建目录

```text
clickhouse-sql-review/
├── SKILL.md
├── scripts/validate_sql.py
├── references/clickhouse-rules.md
├── references/sensitive-columns.md
└── examples/cases.md
```

## 2. 写 frontmatter

```yaml
---
name: clickhouse-sql-review
description: Review ClickHouse SQL for read-only safety, table and column access, limits, and metric-definition consistency. Use before executing model-generated analytics SQL.
---
```

description 要让 Agent 能判断何时加载。不要写空泛的“帮助处理 SQL”。

## 3. 正文应写什么

1. 输入要求：SQL、用户/租户、目标指标、环境。
2. 执行顺序：parser → 只读 → 权限 → limit/timeout → 口径。
3. 何时调用脚本和读取哪份 reference。
4. 输出 schema：pass/reject、原因代码、证据和修复建议。
5. 不能做什么：不执行 SQL、不修改权限、不泄露 schema。

## 4. 脚本与自然语言的边界

`validate_sql.py` 做确定性语法/AST 检查；Skill 说明流程与解释；真正执行端仍重复授权和安全检查。不要把安全建立在 Agent “记得遵循 Skill”之上。

## 5. Progressive Disclosure

启动时只需发现 name/description；命中任务后读取 SKILL.md；只有具体规则需要时再加载 reference/脚本。这样减少 context 常驻内容和过时知识污染。

## 6. 测试

- 10 条合法 SELECT。
- 20 条拒绝：写操作、多语句、越权表/列、无 limit、危险函数、注释/大小写绕过。
- 5 条口径冲突。
- 5 条“本 Skill 不适用”的任务，验证不会误触发。

## 7. 供应链安全

安装第三方 Skill 前检查来源、脚本、副作用、网络和文件权限。Skill 是可执行流程载体，不能因为格式是 Markdown 就认为安全。

最终用 [Agent Skills 规范](https://openagentskills.dev/docs/specification) 校验名称、frontmatter 和目录约束。
