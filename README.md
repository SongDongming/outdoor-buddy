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
- **SSE 流式输出** — 问答/装备/预案实时逐字显示，右下角带生成状态指示
- **PDF / HTML 双格式导出** — 行程预案与装备方案可一键下载 PDF（weasyprint，含 Markdown 表格/列表渲染）或 HTML 海报
- **内容审核体系** — 五层混合审核：关键词秒拦(Aho-Corasick 2000+ 词) + 本地 NSFW 模型 + DeepSeek 语义复查 + 用户举报 + 管理员审核中心
- **社区论坛** — 帖子/评论点赞（爱心）、嵌套回复、多板块，抖音式单页评论体验
- **邮箱注册 + 密码重置** — 支持 SMTP 邮件发送，令牌有效期 1 小时
- **本地 NSFW 头像审核** — onnxruntime 本地模型检测色情图片，无需视觉云 API
- **实时交通票务** — 对接 12306 MCP 服务，查询真实车次信息
- **7 天天气预报** — 对接气象 MCP 服务，附徒步可行性评估和装备调整建议
- **安全加固** — 内容转义防 XSS、上传魔数校验、SSRF 防护、认证限流、安全响应头（CSP 等）
- **Docker 一键部署** — PostgreSQL + Redis + MinIO + FastAPI 全容器化，支持开发模式热加载
- **进站特效** — "用脚步丈量大地"逐字踩落 + 粉尘动画

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

代码目录已挂载到容器（含 `app/data` 词库），修改 Python/HTML/CSS/JS 后重启容器即可生效，无需重新构建镜像：

```bash
docker compose restart app
```

> 新增系统依赖（如 pango/中文字体/weasyprint）时才需要重新构建镜像：`docker compose build app && docker compose up -d`

## 📋 功能详情

### 🔍 路线查询
输入关键词（如"武功山"、"雨崩"），RouteAgent 通过 LLM 生成结构化路线数据，包含距离、爬升、海拔、难度、最佳季节、综合评分，附 AI 综合分析。结果自动缓存 24 小时。

### 🎒 装备推荐
选择徒步模式（轻装/重装）、天数、季节，EquipmentAgent 基于路线特征自动匹配装备清单，SSE 流式输出。支持导出文本、下载 HTML 海报、下载 PDF。

### 🚂 交通票务
输入出发城市、目的城市、出行日期，TicketAgent 通过 12306 MCP 实时查询车次、座位类型和票价，附接驳建议。

### 🌤️ 天气查询
输入徒步地点，WeatherAgent 返回 7 天预报 + 徒步可行性评估 + 装备调整建议，基于温度、降水、风速综合分析。

### 📋 行程智能预案
核心功能。4 步完成：
1. 搜索路线 → 2. 自动获取天气 → 3. 自动查询车票 → 4. 选择装备模式 → 一键生成

6 个维度并行生成：海拔健康应对、体能与行程分配、天气风险应对、环境安全知识、每日行动指南、交通出行建议。SSE 流式输出，可一键下载 **PDF / HTML**（Markdown 表格、列表、加粗完整渲染）。

### 💬 智能问答
QAAgent 覆盖 5 大领域：野外生存、户外急救、天气判断、LNT 环保法则、装备保养。支持多轮对话（会话上下文记忆）、SSE 流式输出、安全风险自动提示。

### 👥 社区论坛
多板块讨论（分享、问答、约伴、装备），支持 Markdown、图片上传、嵌套回复、分页浏览。**帖子与评论均可点赞**（爱心图标），评论区单页内联展开（抖音风格）。内置**五层内容审核**（见下），管理员可删除/隐藏违规内容、封禁用户。

### 🛡️ 内容审核体系（头像 + 论坛文字 + 论坛图片）
分层的混合审核机制，覆盖头像、帖子、回复、图片：

| 层 | 机制 | 时机 |
|----|------|------|
| L1 | **关键词黑名单**（本地秒拦，`app/data/moderation_keywords.txt` 手工词 + `app/data/lexicon/` 精选词库，共 2000+ 条；Aho-Corasick 多模式匹配） | 发布时即时拦截 |
| L2 | **本地 NSFW 模型**（Yahoo open_nsfw 的 onnxruntime 移植版 `opennsfw-onnx`，权重内置）检测色情类图片 | 头像/图片上传时明显违规直接拒绝，边界图自动标记 |
| L3 | **DeepSeek 文本语义复查**（异步后台） | 发布后后台审查，可疑内容进管理员队列 |
| L4 | **用户举报** 🚩（帖子/回复可举报，限流防刷） | 随时 |
| L5 | **管理员审核中心**（待办队列 = 举报 + AI/NSFW 标记，可隐藏/删除/忽略/封禁用户） | 论坛页「审核中心」 |

> 说明：NSFW 模型只检测色情类图片；暴力/政治等图片靠 L4 举报 + L5 人工兜底。
> DeepSeek 为纯文本模型、不支持图片，头像/图片审核使用本地 NSFW 模型（原 AI 视觉审核方案无效，已替换）。

**词库说明**：L1 关键词来自两个来源，均可热更新（重启生效）：
- `app/data/moderation_keywords.txt` — 手工维护的精简黑名单（约 60 条，格式：# 分类注释 + 每行一词）
- `app/data/lexicon/*.txt` — 精选敏感词库（Sensitive-lexicon 开源词库的精选子集：色情/暴恐/涉枪涉爆/贪腐，共约 2000 条），按分类一个文件，可增删文件调整覆盖范围

匹配使用纯 Python **Aho-Corasick 多模式自动机**（`app/utils/aho_corasick.py`），词量增大不影响检测速度（O(文本长度)），规避了朴素逐词扫描在词表增大后的性能退化。

### 👤 用户系统
- 邮箱注册 + 用户名/邮箱双模式登录
- JWT 认证（24h 有效期）
- 头像上传 + 本地 NSFW 模型内容审核（含管理员复核队列）
- 违规累计可被管理员封禁（封禁后禁止发帖/回复/上传/点赞等写操作）
- 忘记密码 → 邮件重置（令牌不回传客户端，仅记录服务端日志）
- 路线/预案收藏 + 查询历史

## 🛡️ 安全加固

项目在功能完善之外做了系统性的安全与健壮性加固：

| 类别 | 措施 |
|------|------|
| **XSS** | 前端 Markdown 渲染器 `renderMarkdown` 对所有文本（段落/标题/列表/表格/行内）做 HTML 转义，杜绝存储型/反射型 XSS；CSP 安全头作为第二道防线 |
| **认证安全** | 登录/注册/重置口令接口限流防暴力破解；token 失效全局处理（401 清登录态）；封禁用户在 `get_current_user` 统一拦截 |
| **文件上传** | 头像/论坛图片做文件头魔数校验（非图片字节拒绝落盘）；大小校验兜底；PIL 解压炸弹防护（>40MP 拒绝） |
| **SSRF** | 后台图片复核仅接受本站 `/static/img/` 路径，禁止远程 URL 抓取；论坛图片 schema 限本站上传 URL |
| **配置** | 启动时检测默认 `SECRET_KEY` / 默认超管口令并打印 SECURITY 告警 |
| **安全头** | `Content-Security-Policy`、`X-Frame-Options: DENY`、`X-Content-Type-Options: nosniff`、`Referrer-Policy` |
| **CORS** | 收窄允许来源（`CORS_ORIGINS` 配置，不再全放开） |
| **性能** | NSFW 推理放线程池不阻塞事件循环；论坛/收藏热查询补索引；后台任务跟踪防泄漏；Redis 限流原子化；会话内存缓存上限 |
| **健壮性** | 全局异常处理器统一响应；PDF 导出接口需登录且不回显内部错误 |

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
| `NSFW_ENABLED` | 本地 NSFW 图片审核开关 | `true` |
| `NSFW_REJECT_THRESHOLD` | NSFW 分数 ≥ 该值直接拦截（0-1） | `0.8` |
| `NSFW_REVIEW_THRESHOLD` | NSFW 分数 ≥ 该值进入管理员复核队列（0-1） | `0.2` |
| `CORS_ORIGINS` | 允许跨域来源（逗号分隔） | `http://localhost:8001` |

> ⚠️ **安全提醒**：生产环境务必修改 `.env` 中的 `SECRET_KEY`（JWT 签名密钥，用默认值会导致令牌可被伪造）和 `SUPER_ADMIN_PASSWORD`（默认 admin123）。启动时使用默认值会打印 SECURITY 告警。

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
| **内容审核** | Aho-Corasick 词库匹配 + open_nsfw (onnxruntime) + DeepSeek 文本复查 + 举报 + 管理员审核中心 |
| **PDF 导出** | weasyprint (pango + Noto CJK/Emoji 字体) |
| **前端** | Alpine.js 3.14 响应式 SPA |
| **样式** | 纯 CSS (Alpine Tech 设计系统) |
| **字体** | Playfair Display + Inter + JetBrains Mono |
| **部署** | Docker Compose 三容器编排 |

## 📁 项目结构

```
├── app/
│   ├── agents/          # LangGraph Agent (Route, Equipment, Plan, QA, etc.)
│   ├── api/             # FastAPI 路由 (auth, routes, plans, forum, moderation, export, etc.)
│   ├── core/            # 配置管理 + JWT + 密码哈希
│   ├── models/          # SQLAlchemy ORM (User, Forum, Moderation, Favorite, etc.)
│   ├── schemas/         # Pydantic 请求/响应验证
│   ├── services/        # 业务逻辑 (route, equipment, storage, moderation, nsfw, pdf, etc.)
│   ├── data/            # 内容审核词库
│   │   ├── moderation_keywords.txt   # 手工维护关键词
│   │   └── lexicon/                  # Sensitive-lexicon 精选词库（色情/暴恐/涉枪涉爆/贪腐）
│   ├── static/          # 前端 (Alpine.js SPA)
│   │   ├── css/         # Alpine Tech 设计系统
│   │   ├── js/          # API 客户端 + 应用逻辑 + Canvas 动画
│   │   └── img/         # 用户上传 (avatars/, uploads/) + logo/背景图
│   └── utils/           # LLM/MCP 客户端 + Aho-Corasick 匹配器 + Redis + 日志
├── docker-compose.yml   # app + PostgreSQL + Redis + MinIO
├── Dockerfile           # 多阶段构建（含 pango + 中文字体）
└── requirements.txt
```

## 📄 License

MIT © 2025

---

<p align="center"><sub>Built for outdoor enthusiasts · Powered by LangGraph</sub></p>