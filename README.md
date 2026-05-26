<div align="center">

<img src="https://img.shields.io/badge/python-3.12+-blue" alt="Python">
<img src="https://img.shields.io/badge/license-MIT-green" alt="License">
<img src="https://img.shields.io/badge/tests-59%20passed-brightgreen" alt="Tests">
<img src="https://img.shields.io/badge/PRs-welcome-orange" alt="PRs">

</div>

<h1 align="center">🏢 Corpus — 企业级多智能体层级协作平台</h1>

<p align="center">
  <em>不是 Chatbot，这是一家由 AI Agent 组成的<strong>虚拟公司</strong>。</em>
</p>

<p align="center">
  每个 Agent 都是一名<strong>员工</strong>——有工位（独立文件夹）、有档案（soul.md）、有记忆（memory.md）、有上级（reports_to 链）。<br>
  它们像真实公司一样运转：CEO 分解战略、部门协作执行、会议决策、失败升级、HR 招聘。
</p>

---

## 💡 为什么做这个？

现有 Multi-Agent 框架（AutoGen、CrewAI、MetaGPT）解决的是"让 Agent 对话"，但没有解决**组织治理**问题。

真实世界的公司不是一群人围成一圈轮流发言——有**层级、有流程、有问责**。

Corpus 把 Agent 嵌入到公司组织架构中运行：

| 传统 Multi-Agent | Corpus |
|---|---|
| Agent 之间聊天 | Agent 在**部门**中、向**上级**汇报 |
| 一轮对话结束 | 任务有**编号**、有**状态机**、可**审计追溯** |
| 出错了人工介入 | 沿 reports_to 链**自动升级**，监察部分析根因 |
| "人不够了" 无解 | Agent 向 HR **发起招聘请求**，拉会定稿 soul.md |
| 对话即产出 | 任务有 **Artifact**，子任务有**依赖图**，树形追踪 |

---

## 🏛️ 组织架构

```
CEO 办公室 (T0)
│
├─ 幕僚长 ──────────────────── 首席助理 · 跨部门协调
├─ 秘书科 (T2) ─────────────── 所有会议强制参会 · 纪要生成
├─ 通讯科 (T2) ─────────────── 每日简报 · 邮件汇报
│
├─ 产品部门 (T1)
│   ├─ 创意中心 (T2) ─────── 商机发现 · 创意生成
│   ├─ 实现中心 (T2) ─────── 代码→测试→运维
│   └─ 研究中心 (T2) ─────── 市场分析 · 趋势研判
│
├─ 监察部门 (T1)
│   └─ 改进中心 (T2) ─────── 运行时分析 · 根因诊断 · 改进建议
│
└─ 人力资源部门 (T1)
    └─ 招聘中心 (T2) ─────── 招聘研判 · soul.md 研讨会议
```

**任意扩展**：API / CLI 动态创建部门、调整层级、挂靠 Agent，不限层级深度。

---

## 🚀 30 秒快速开始

```bash
# 1. 安装
pip install sqlalchemy aiosqlite alembic litellm fastapi uvicorn typer \
    pydantic pydantic-settings cryptography pyyaml httpx websockets

# 2. 配置
cp .env.example .env   # 填入 FERNET_KEY

# 3. 初始化
python -m src.cli.main init          # 创建组织架构
python -m src.cli.main seed-agents   # 创建 11 名员工

# 4. 配置模型
python -m src.cli.main preset-create  # 填入 API Key

# 5. 启动
python -m src.cli.main serve --port 8080
```

打开 **`http://localhost:8080/dashboard/`** → 开始与 CEO 对话。

---

## 🎯 核心功能矩阵

### 🤖 Agent 管理体系

| 功能 | 描述 |
|---|---|
| **独立人格** | 每个 Agent 有 `soul.md`（角色定位 + 能力 + 约束），可热编辑 |
| **持久记忆** | `memory.md` 持续记录经验，支持重要性评分与容量上限 |
| **物理工作区** | Agent = 文件夹，`soul.md` + `memory.md` + `workspace/` ，可直接在磁盘上查看 |
| **模型切换** | 预设模板保存 API Key，Agent 一键选配，免重复输入 |
| **权限矩阵** | T0/T1/T2 各层级权限递减，部门权限 ∩ 个人权限 = 实际权限 |

### 📋 任务系统

```
CEO 收到用户指令
  → 分解为子任务，生成层级编号 (T-20260526-001-001)
  → 沿部门链分配给执行 Agent
  → Agent 自动认领 → LLM 执行 → 产出 Artifact
  → 子任务全部完成 → 父任务自动标记完成
```

| 特性 | 实现 |
|---|---|
| **层级编号** | `T-{date}-{root}-{child}-{grandchild}` 模式，自动生成 |
| **7 状态机** | pending → in_progress → completed / failed / needs_clarification / blocked / cancelled |
| **依赖图** | 任务间 blocks / informs 依赖，DFS 环检测 |
| **自动执行** | AgentWorker 每 5 秒轮询 pending 任务，Agent 认领后 LLM 执行 |
| **审计链** | 每次状态变更写入 audit_log，完整追溯 |
| **超时检测** | TaskWatchdog 监控超时 / 长时间阻塞，触发升级 |

### 💬 会议系统

```
非轮询式。主席管理发言队列，Agent 主动请求发言，动态回应。
秘书科强制参会 + 实时纪要。终止前逐一轮询所有 Agent 确认无补充。
WebSocket 实时推送。
```

| 会议类型 | 场景 |
|---|---|
| 协调会议 | Agent 间工作协作，主席（或 CEO）主持 |
| 用户直连 | 用户直接对 Agent 下达指令 |
| 招聘研讨 | HR 组织，T1+T2+请求人 6 轮议程定稿 soul.md |

### ⚠️ 升级链

```
任务失败 / 超时 / 需澄清
  → TaskWatchdog 检测
  → 监察部-改进中心 分析根因（LLM 记录 + 指标 + 上下文）
  → 沿 reports_to 链上报：执行 Agent → T2 负责人 → T1 部门长 → CEO → 用户
  → 上级 5 选 1：修改重试 / 再升级 / 直接解决 / 退回原 Agent / 取消
```

### 👥 招聘体系

```
Agent 向 HR 发起招聘请求
  → HR 研判（工作量 / 技术栈 / 新能力 / 替换）
  → 通过 → soul.md 研讨会议（6 轮议程，三方确认）
  → 定稿 → 创建 Agent → 入职培训 → 活跃
  → 拒绝 → 给出详细理由（含"你处理速度远超人类"提醒）
```

---

## 🖥️ Web 管理面板

`http://localhost:8080/dashboard/` 提供 8 个页签：

| 📊 总览 | 🏗️ 组织 | 🤖 Agent | 📋 任务 | 💬 对话 | 💬 会议 | ⚙️ 预设 | ⚠️ 升级 |
|---|---|---|---|---|---|---|---|

**核心交互**：在 💬 对话页签选 CEO，自然语言布置任务 → CEO 自动解析并创建任务 → AgentWorker 自动执行 → 任务页签实时追踪。

---

## 🧱 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| **语言** | Python 3.12+ / asyncio | LLM 生态第一选择；异步支撑并发 Agent |
| **LLM 抽象** | LiteLLM + OpenAI SDK | 100+ 模型统一调用；新模型自动降级直连 |
| **数据库** | SQLAlchemy 2.x / SQLite↔PostgreSQL | 开发零配置，生产高性能，一套 ORM 兼容 |
| **Web** | FastAPI + WebSocket | 异步原生，自动文档，实时会议推送 |
| **CLI** | Typer | 33 个管理命令，类型安全 |
| **安全** | Fernet (cryptography) | API Key 静态加密存储 |

---

## 📂 项目结构

```
src/
├── core/         配置 · 数据库引擎 · 异常体系
├── models/       22 个 ORM 模型（23 张表）
├── services/     业务逻辑（Agent 生命周期 · 组织管理 · 任务 · 会议 · 升级 · 招聘）
├── agents/       8 个专项 Agent + 注册表 + 基类
├── meeting/      会议协议引擎（消息总线 · 发言队列 · 状态机）
├── api/routes/   8 组 REST 路由 + WebSocket 实时会议
├── cli/          33 个 CLI 命令 + 种子数据
├── repositories/ 4 个异步数据仓库
├── workers/      AgentWorker · TaskWatchdog · DailyBriefing · Scheduler
└── utils/        LLM 客户端 · Fernet 加密 · 文件系统 · ID 生成
```

---

## 🧪 测试

```bash
python -m pytest tests/ -v
# 59 passed
```

覆盖：ORM 模型 · T0/T1/T2 层级校验 · 任务状态机 · 依赖环检测 · 会议协议 · 发言队列 · 升级链 · Agent 创建

---

## 📃 License

MIT — 自由使用、修改、分发。

---

<p align="center">
  <sub>Built with ❤️ by the Corpus Team</sub>
</p>
