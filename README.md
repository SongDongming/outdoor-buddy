<p align="center">
  <h1 align="center">🏔️ Outdoor Buddy</h1>
  <p align="center"><strong>基于 LangGraph 多智能体的户外徒步一站式助手</strong></p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi" />
  <img src="https://img.shields.io/badge/LangGraph-0.2+-FF6F00" />
  <img src="https://img.shields.io/badge/Alpine.js-3.14-8BC0D0?logo=alpine.js" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql" />
  <img src="https://img.shields.io/badge/Docker-✓-2496ED?logo=docker" />
  <img src="https://img.shields.io/badge/license-MIT-success" />
</p>

---

## ✨ 核心特性

- **7 个 AI Agent 协同** — 路线搜索、装备推荐、天气查询、交通票务、行程预案、智能问答、社区论坛，由 Supervisor 统一调度
- **行程预案并行生成** — 6 个模块（海拔、体能、天气、环境、指南、交通）同时调用 LLM，15-25 秒完成
- **邮箱注册 + 密码重置** — 支持 SMTP 邮件发送，令牌有效期 1 小时
- **AI 头像审核** — 上传头像自动调用视觉模型进行内容安全检测
- **实时交通票务** — 对接 12306 MCP 服务，查询真实车次信息
- **7 天天气预报** — 对接气象 MCP 服务，附徒步可行性评估和装备调整建议
- **Docker 一键部署** — PostgreSQL + MinIO + FastAPI 全容器化，支持开发模式热加载
- **响应式设计** — 浅色高级科技风 UI，适配桌面、平板、手机

## 🏗️ 系统架构

```
用户浏览器 (Alpine.js SPA)
        │
        ▼
┌───────────────────┐
│  FastAPI Gateway   │  ← REST API (/api/v1/*)
└───────┬───────────┘
        │
┌───────▼───────────────────────────────────┐
│         LangGraph Agent System             │
│                                            │
│  SupervisorAgent (路由分发)                 │
│    ├── RouteAgent     路线搜索              │
│    ├── EquipmentAgent 装备推荐              │
│    ├── WeatherAgent   天气查询 (MCP)        │
│    ├── TicketAgent    票务查询 (MCP)        │
│    ├── PlanAgent      行程预案 (6 节点并行)  │
│    └── QAAgent        智能问答              │
│                                            │
│  每个 Agent = LangGraph StateGraph + LLM    │
└───────┬───────────────────────────────────┘
        │
┌───────▼───────────────────────────────────┐
│             Data Layer                     │
│  PostgreSQL (主) + SQLite (回退)            │
│  MinIO / 本地文件系统 (图片存储)            │
│  Redis (可选，缓存)                         │
└───────────────────────────────────────────┘
```

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
- LLM API Key（[DeepSeek](https://platform.deepseek.com/) 或兼容 OpenAI 接口的任意服务）

### 安装步骤

```bash
# 1. 克隆
git clone https://github.com/your-username/outdoor-buddy.git
cd outdoor-buddy

# 2. 配置
cp .env.example .env
# 编辑 .env，填入 API Key

# 3. 启动
docker compose up -d

# 4. 访问
open http://localhost:8001
```

### 开发模式

代码目录已挂载到容器，修改 Python/HTML/CSS/JS 后重启容器即可生效，无需重新构建镜像：

```bash
docker compose restart app
```

## 📋 功能详情

### 🔍 路线查询
输入关键词（如"武功山"、"雨崩"），RouteAgent 通过 LLM 生成结构化路线数据，包含距离、爬升、海拔、难度、最佳季节、综合评分，附 AI 综合分析。结果自动缓存 24 小时。

### 🎒 装备推荐
选择徒步模式（轻装/重装）、天数、季节，EquipmentAgent 基于路线特征自动匹配装备清单。支持导出文本和下载海报。

### 🚂 交通票务
输入出发城市、目的城市、出行日期，TicketAgent 通过 12306 MCP 实时查询车次、座位类型和票价，附接驳建议。

### 🌤️ 天气查询
输入徒步地点，WeatherAgent 返回 7 天预报 + 徒步可行性评估 + 装备调整建议，基于温度、降水、风速综合分析。

### 📋 行程智能预案
核心功能。4 步完成：
1. 搜索路线 → 2. 自动获取天气 → 3. 自动查询车票 → 4. 选择装备模式 → 一键生成

6 个维度并行生成：海拔健康应对、体能与行程分配、天气风险应对、环境安全知识、每日行动指南、交通出行建议。

### 💬 智能问答
QAAgent 覆盖 5 大领域：野外生存、户外急救、天气判断、LNT 环保法则、装备保养。支持多轮对话，含安全风险自动提示。

### 👥 社区论坛
多板块讨论（分享、问答、约伴、装备），支持 Markdown、图片上传、回复嵌套、分页浏览。管理员可删除违规内容。

### 👤 用户系统
- 邮箱注册 + 用户名/邮箱双模式登录
- JWT 认证（24h 有效期）
- 头像上传 + AI 内容审核
- 忘记密码 → 邮件重置
- 路线/预案收藏 + 查询历史

## 🔧 配置参考

### 必需

| 变量 | 说明 |
|------|------|
| `COMPATIBLE_API_KEY` | LLM API 密钥 |
| `COMPATIBLE_BASE_URL` | API 地址（默认 DeepSeek） |
| `COMPATIBLE_MODEL` | 模型名（默认 `deepseek-v4-flash`） |

### 可选

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DB_PASSWORD` | PostgreSQL 密码 | `outdoor_buddy_pg` |
| `SECRET_KEY` | JWT 签名密钥 | 建议修改 |
| `STORAGE_BACKEND` | `local` 或 `minio` | `local` |
| `SMTP_HOST` | 邮件服务器 | 不填则开发模式 |
| `SMTP_PORT` | 邮件端口 | `587` |
| `SMTP_USER` | 邮箱账号 | — |
| `SMTP_PASSWORD` | 邮箱授权码 | — |
| `HTTP_PROXY` | 代理地址 | — |

### SMTP 配置示例

```env
# 163 邮箱
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=your-email@163.com
SMTP_PASSWORD=your-auth-code    # 授权码，非登录密码
SMTP_FROM=your-email@163.com
SMTP_USE_TLS=false              # 163 使用 SSL，非 STARTTLS

# QQ 邮箱
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=your-qq@qq.com
SMTP_PASSWORD=your-auth-code
SMTP_USE_TLS=true
```

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| **后端框架** | FastAPI + Uvicorn |
| **多智能体** | LangGraph + LangChain + ChatOpenAI |
| **数据库** | PostgreSQL 16 (asyncpg) + SQLite 回退 |
| **ORM** | SQLAlchemy 2.0 (AsyncSession) |
| **认证** | JWT (HS256) + PBKDF2-SHA256 |
| **存储** | MinIO (S3) / 本地文件系统 |
| **前端** | Alpine.js 3.14 响应式 SPA |
| **样式** | 纯 CSS (Alpine Tech 设计系统) |
| **字体** | Playfair Display + Inter + JetBrains Mono |
| **部署** | Docker Compose 三容器编排 |

## 📁 项目结构

```
├── app/
│   ├── agents/          # LangGraph Agent (Route, Equipment, Plan, QA, etc.)
│   ├── api/             # FastAPI 路由 (auth, routes, plans, forum, etc.)
│   ├── core/            # 配置管理 + JWT + 密码哈希
│   ├── models/          # SQLAlchemy ORM (User, Forum, RouteCache, etc.)
│   ├── schemas/         # Pydantic 请求/响应验证
│   ├── services/        # 业务逻辑 (route, equipment, storage, etc.)
│   ├── static/          # 前端 (Alpine.js SPA)
│   │   ├── css/         # Alpine Tech 设计系统
│   │   ├── js/          # API 客户端 + 应用逻辑 + Canvas 动画
│   │   └── img/         # 用户上传 (avatars/, uploads/)
│   └── utils/           # LLM 客户端 + MCP 客户端 + 日志
├── scripts/             # 数据库初始化 SQL
├── docker-compose.yml   # app + PostgreSQL + MinIO
├── Dockerfile           # 多阶段构建
└── requirements.txt
```

## 📄 License

MIT © 2025

---

<p align="center"><sub>Built for outdoor enthusiasts · Powered by LangGraph</sub></p>