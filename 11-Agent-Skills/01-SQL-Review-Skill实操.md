# 从零制作 SQL Review Skill

## 1. 建目录

```text
clickhouse-sql-review/
├── SKILL.md
├── agents/openai.yaml
├── scripts/validate_sql.py
├── references/clickhouse-rules.md
├── references/sensitive-columns.md
├── references/metric-definitions.md
└── references/failure-cases.md
```

## 2. 写 frontmatter

```yaml
---
name: clickhouse-sql-review
description: Review ClickHouse SQL for read-only safety, table and column access, limits, and metric-definition consistency. Use before executing model-generated analytics SQL.
---
```

description 要让 Agent 能判断何时加载。不要写空泛的“帮助处理 SQL”。
当前 Skill Creator 规范要求 frontmatter 只保留 `name`、`description`；版本、作者等自定义信息不能随意塞进这里。

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

实现时要能观测三阶段：

1. `discover_skills(root)` 只读 frontmatter，并隔离坏包。
2. `load_instructions(name)` 在任务命中后读完整 SKILL.md。
3. `load_reference(name, path)` 只读正文明确链接且当前结论需要的单份资料。

每次加载记录 stage、relative path 和 bytes。否则“我们是懒加载”只是一句无法验证的描述。

### 5.1 路径安全

第三方 Skill 目录是不可信输入。资源解析必须：

- 只接受 POSIX 相对路径，拒绝绝对路径、反斜杠、`.` 和 `..`；
- reference/script 限定在对应目录，且必须由 SKILL.md 明确提及；
- `resolve()` 后仍在 Skill 根目录；
- 任一路径段为 symlink 时拒绝；
- 对 frontmatter、正文和 reference 设置大小上限。
- 最终包根目录只允许 `SKILL.md`、`agents/`、`scripts/`、`references/`、`assets/`；删除初始化阶段产生的 `examples/` 临时文件。
- 遍历 `assets/` 的类型、大小、内部断链与 symlink，不能只检查 SKILL.md 指向它的第一条链接。

路径检查应在读取/导入之前完成。不要先打开文件再判断“好像还在 Skill 目录里”。

## 6. 测试

- 至少 10 条合法 SELECT，覆盖大小写、注释、别名、CTE、指标和不同环境。
- 至少 20 条拒绝：写操作、多语句/未支持查询形态、越权表/列、无/动态/超限 limit、offset、危险函数、query settings、注释/大小写绕过。
- 5 条口径冲突。
- 5 条“本 Skill 不适用”的任务，验证不会误触发。
- 目录与供应链失败：坏 frontmatter、断链、脚本语法、绝对/穿越路径、未链接资源和 symlink。

配套工程现在有 93 条离线断言，详见 [skill-practice](./skill-practice/README.md)。

## 7. 供应链安全

安装第三方 Skill 前检查来源、脚本、副作用、网络和文件权限。Skill 是可执行流程载体，不能因为格式是 Markdown 就认为安全。

最终用 [Agent Skills 规范](https://openagentskills.dev/docs/specification) 校验名称、frontmatter 和目录约束。
