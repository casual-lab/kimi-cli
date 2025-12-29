# e2e-timewalker

> 简体中文版 · [English](./README.md)

**e2e-timewalker** 是 Kimi CLI monorepo 中专门面向端到端测试的工具集。它按照时间线完整记录 CLI 会话、重放终端状态，并与基线版本对比生成可读的报告，帮助研发与 QA 快速定位“非确定性”场景中的问题。

可以把它理解成一台时间旅行录影机：你可以回到任意一个命令执行瞬间，查看终端颜色、光标移动或工具调用的细节，然后将结果沉淀成易于审阅的报告。

---

## 核心能力

- **场景执行器**：在受控的 PTY 沙箱中运行脚本化 CLI 会话，注入统一的提示符与辅助命令。
- **时间线采集**：保存原始输出流、结构化事件、输入指令和环境元数据。
- **状态重放**：将终端画面还原为 HTML / PNG / 文本关键帧，方便并排对比。
- **差异洞察**：与稳定基线比较，生成基于规则或 LLM 的预警与说明。
- **自动化友好**：提供 Make 命令、CLI 入口与 CI 集成示例，降低接入成本。

---

## 架构概览

```
┌──────────────────────────────┐
│        Scenario Runner       │
│  - PTY 管理                  │
│  - JSON DSL 执行             │
│  - 环境注入                  │
└──────────────┬───────────────┘
               │ 时间线数据
┌──────────────▼───────────────┐
│        Data Recorder         │
│  - 原始输出流                │
│  - 结构化日志                │
│  - 会话元数据                │
└──────────────┬───────────────┘
               │ 产物
┌──────────────▼───────────────┐
│   Replay & Inspection stack  │
│  - HTML/PNG/文本关键帧       │
│  - 基线差异分析              │
│  - 预警与注释                │
└──────────────┬───────────────┘
               │ 报告模型
┌──────────────▼───────────────┐
│  Report & Workflow adapter   │
│  - Markdown/HTML 报告        │
│  - Make/CLI 集成             │
│  - CI 钩子与人工审核         │
└──────────────────────────────┘
```

---

## 工作流程

1. **准备**：编写或选择一个描述会话流程的 JSON 场景文件。
2. **执行**：通过 `make e2e-run`（或 Python 入口）运行场景，生成结果包。
3. **重放**：使用 `make e2e-report` 解析结果包，重建终端画面并对比基线，输出报告。
4. **审阅**：在本地或 CI 产物中查看关键帧、预警和日志。
5. **迭代**：根据真实需求更新基线、忽略规则或场景步骤。

---

## JSON 场景 DSL（草案）

```json
{
  "name": "echo_conversation",
  "description": "使用 echo provider 发起对话",
  "vars": {
    "workspace": "~/demo"
  },
  "steps": [
    { "type": "command", "run": "cd {{ workspace }}" },
    { "type": "command", "run": "kimi --provider echo --message 'hello'" },
    {
      "type": "wait",
      "expect": { "contains": "hello" },
      "timeout": 5
    },
    { "type": "snapshot", "label": "after_echo" }
  ]
}
```

能力亮点：
- **command 步骤**：向 PTY 发送任意 shell 指令。
- **wait 步骤**：在超时时间内轮询输出，匹配特定模式或自定义条件。
- **snapshot 步骤**：标记关键时刻，便于重放与报告引用。
- **变量与模板**：安全复用目录、参数或密钥。
- **Schema 校验**：通过 JSON Schema 保证场景在执行前合法。

---

## CLI 与 Make 命令（规划）

| 命令 | 说明 |
|------|------|
| `make e2e-run` | 执行指定 JSON 场景（`SCENARIO=...`），输出结果包（`OUTDIR=...`）。 |
| `make e2e-report` | 分析结果包（`RESULT=...`），重建关键帧并生成 Markdown / HTML 报告。 |
| `make e2e-all` | 依次执行 `e2e-run` 与 `e2e-report`，适合本地一键测试或 CI 使用。 |

Python 入口与上述命令一一对应（如 `uv run python -m e2e_timewalker.run`、`...report`）。

---

## 目录结构（建议）

```
kimi-cli/e2e-timewalker/
├── README.md / README.zh.md
├── Makefile.inc               # 被主仓 Makefile 引入的 e2e 目标
├── timewalker/
│   ├── runner.py              # PTY 调度与 DSL 引擎
│   ├── recorder.py            # 原始/结构化采集
│   ├── replayer.py            # 关键帧生成工具
│   ├── inspector.py           # 差异、规则与 LLM 钩子
│   ├── reporter.py            # 报告渲染
│   └── dsl/
│       ├── schema.json        # 场景 JSON Schema
│       └── parser.py          # 校验与模板处理
├── scenarios/                 # 示例与正式场景
├── baselines/                 # 基线关键帧（纳入版本控制）
├── outputs/                   # 生成产物（gitignore）
└── workflows/github-example.yml (可选)
```

---

## 集成方式

- **本地迭代**：修改场景 → `make e2e-run` → 检查产物 → 调整 → `make e2e-report`。
- **基线维护**：需求确认后，使用辅助命令刷新 `baselines/` 中对应的参考数据。
- **CI 检查**：在工作流中调用 `make e2e-all`，上传报告和快照，必要时通过 PR 评论提示。
- **人工复核**：审阅 Markdown 报告，处理预警，更新忽略规则，必要时触发重新录制。

---

## 后续规划

- 扩展 DSL（循环、分支、并发片段、可复用宏等）。
- 开发轻量级 Web 查看器，浏览时间线与 diff。
- 加强规则引擎，引入更丰富的 LLM 提示，生成更具可操作性的摘要。
- 提升跨平台兼容性（macOS / Linux 容器 / WSL 等）。

---

## 贡献指南

1. 阅读中英文 README 了解目标和结构规划。
2. 选择某个子模块（runner、recorder、replayer、inspector、reporter、DSL）提出实现方案。
3. 以示例场景为起点，跑通完整 pipeline 后再扩展功能。
4. 随 DSL 能力变化，保持文档与 JSON Schema 更新一致。

欢迎通过 issue 或 PR 提交建议，一起打造好用的端到端“时间旅行器”。
