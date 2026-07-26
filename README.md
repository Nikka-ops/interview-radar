<div align="center">

<h1>📡 InterviewRadar · 面试雷达</h1>

**抓取小红书 & 牛客的真实面经 → AI 过滤去重 → 生成按频次排序的高频题库，并聚合互联网大厂在招岗位**

面向 **数据开发** 与 **Agent / AI 应用开发** 两个方向，专注近三个月、与目标岗位强相关的高频考点。

<p>
<img alt="License" src="https://img.shields.io/badge/License-MIT-yellow.svg">
<img alt="Python" src="https://img.shields.io/badge/Python-3.11+-blue.svg">
<img alt="AI" src="https://img.shields.io/badge/AI-DeepSeek-7c3aed.svg">
<img alt="XHS" src="https://img.shields.io/badge/小红书-Playwright%20CDP-ff2442.svg">
<img alt="Boss" src="https://img.shields.io/badge/Boss直聘-DrissionPage-00a6a7.svg">
</p>

</div>

---

## ✨ 为什么用它

求职真正需要的，是 **最近三个月、跟你目标岗位直接相关、高频出现** 的面试题——而不是一份陈旧的静态题库。InterviewRadar 把「抓面经 → 筛垃圾 → 提题 → 排频次 → 生成解答」这条链路全自动化：

| 输入 | 处理 | 输出 |
|------|------|------|
| 小红书 / 牛客面经帖 | AI 过滤广告与错岗 · OCR/视觉读图片帖 · 提取题目 | 按频次排序的题库 |
| 目标岗位 + 公司 | 近 90 天时效过滤 · 公司标签归一化 · 语义去重合并 | 高频题 + AI 参考答案 |
| Boss 直聘 / 大厂官网 JD | 浏览器监听绕过风控 · 增量去重 | 在招岗位 + 技术栈 & 薪资分析 |

> 💡 **零配置能启动**：没有 API Key 时以基础模式启动，可用内置样例一键体验界面与流程；配上 Key + 抓取自己的面经后，解锁 AI 过滤、解答、语义搜索等完整能力。

---

## 🖼️ 界面预览

| 面经流 · 按公司/来源筛选 | 高频题库 · 分类 + 语义搜索 |
|:--:|:--:|
| ![面经流](docs/screenshots/home.png) | ![高频题库](docs/screenshots/bank.png) |
| **在招岗位 · 技术栈 & 薪资分析** | **模拟面试 · 导简历 + AI 追问** |
| ![在招岗位](docs/screenshots/jobs.png) | ![模拟面试](docs/screenshots/mock.png) |

---

## 🚀 三步上手

```bash
# 1) 克隆 & 安装（自动校验 Python ≥ 3.11 并建虚拟环境）
git clone https://github.com/Nikka-ops/interview-radar.git interview-radar && cd interview-radar
bash install.sh

# 2) 启动 Web UI
bash start-web.sh                                   # macOS / Linux
.venv\Scripts\python.exe -m scripts.api.server      # Windows
```

打开 **http://localhost:8765** —— 支持 `#bank` / `#jobs` / `#mock` 直达对应视图。
macOS 双击 `start.command`、Windows 双击 `start.bat` 亦可一键启动并自动打开浏览器。

**3) 解锁 AI 能力（可选）**：在网页右上角 ⚙ 设置里直接填 DeepSeek API Key，保存即生效——无需手改 `.env`。

<details>
<summary>手动安装 / 直接写 .env</summary>

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

```env
# AI 过滤 / 题目聚类 / 生成解答（不配则基础模式）
DEEPSEEK_API_KEY=sk-xxxxxxxx
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash        # 便宜模型：过滤 / 聚类 / 答案
DEEPSEEK_PREP_MODEL=deepseek-v4-pro     # 强模型：模拟面试 prep（可选）
# 模型名配置驱动：上游若再改名，只改这里即可，无需动代码

# 题库聚类的 DeepSeek 并发数（可选，默认 12；DeepSeek 为付费 API，并发安全）
AI_CLUSTER_WORKERS=12

# 小红书抓取（可选，见「数据源与抓取」）
XHS_DRIVER=playwright
# 单轮抓取词数上限（护账号降频用，默认 35）
XHS_MAX_KEYWORDS_PER_RUN=35

# 图片帖视觉兜底（可选，OCR 读不出时调用）
VISION_API_KEY=
VISION_MODEL=qwen-vl-plus
```
</details>

---

## 🧭 Web UI 功能

<table>
<tr><td width="50%">

**📋 面经库（Posts）**
- 按公司 / 来源（小红书·牛客）/ 关键词筛选
- 卡片式布局，点击展开完整正文
- 导出 JSON / Markdown 频次报告

**🧠 题库（Bank）**
- 按 **频次** 降序：高频 ≥3 · 中频 2 · 低频 1
- 按考察方向分类（Spark / Hive·SQL / 数仓 / Flink / RAG / Agent / MCP …）
- **题目抽屉**：AI 参考答案 + 考察点 + 深挖方向 + 常见误区
- **掌握度标记** + **语义搜索**（自然语言检索相关题）

</td><td width="50%">

**🎤 模拟面试（Mock）**
- **导入简历**（PDF / 图片 / TXT）自动填技术背景
- AI 面试官从题库挑最匹配的题，结合你的项目追问、逐题点评，末尾生成整体评价

**📚 复习弱项**
- 自动筛出「不会 / 模糊」的题，卡片式翻面复习

**💼 在招岗位（Jobs）**
- 正式 / 实习分 Tab，独立计数，标记「新开」
- **技术栈需求分析**：JD 中各技术出现频次
- **薪资分析**：月薪分桶 · 公司中位对比 · 实习日薪

</td></tr>
</table>

**体验特性**：抓取时**实时进度条 + 人话状态**（"抓取小红书：第 5/30 词"）不再黑盒 · **深色 / 浅色**一键切换（跟随系统，记忆选择）· **移动端自适应** · 抓取失败时给"发生什么 + 下一步怎么办"，页面顶部可查各数据源健康状态。

---

## 🛰️ 数据源与抓取

### 面经

- **小红书（主源）** — 默认 `Playwright + 已登录 CDP Chrome`：驱动真实浏览器搜索、**监听浏览器自发的搜索响应**，不重放签名请求、不烧 Cookie；`Spider_XHS` 作兼容回退。**逐词断点续抓**：每个关键词抓完即落盘记账，遇验证码/风控立即停，下轮从断点继续，不重抓已完成的词。
- **牛客（辅源）** — 自动发现面经帖，二次请求详情页补全正文。
- **图片帖** — 下载图片 → RapidOCR 读文字 → 合并入正文；OCR 失败或低质时自动触发 **视觉大模型**（Qwen-VL / GLM-4V，配 `VISION_API_KEY`）兜底读图。
- **抓取范围可选** — 构建时选 **时间范围**（近 1 周 / 1 月 / 3 月 / 半年）与 **公司范围**（全部大厂 / 指定公司）。

### 岗位

- **大厂官网（job-pro）** — 字节 / 腾讯 / 美团 / 快手 / 网易 / 小米 / 阿里 / 百度 / 华为等官网 JD。
- **Boss 直聘** — [DrissionPage](https://github.com/g1879/DrissionPage) 网络监听：浏览器正常导航职位页，拦截其自发的真实 XHR，不注入人工请求，规避 code-37 风控。列表抓取稳定；JD 详情有 **预检 + 限速 + 熔断**，触发风控自动跳过而不硬刷。

### AI 过滤（配 DeepSeek Key）

每条面经经 `judge_post()` 判定：广告 / 求助 / 培训 / 错岗 → 丢弃；识别 `data` / `ai_app` 岗位归类。自由文本 role 会归一化，标题明确其它岗位的帖被否决——**保证题库岗位纯净**。无 Key 时降级为正则兜底。

---

## 🔧 抓取运维手册（实战最常用）

小红书与 Boss 依赖登录态，是最容易「出问题」的环节。健壮性设计 + 一条命令恢复：

| 场景 | 做法 |
|------|------|
| **小红书首次接入** | 启动专用 Chrome 登录 → `python -m scripts.tools.refresh_cookies xhs` 自动写入 Cookie |
| **Cookie / 登录失效** | 在专用 Chrome 重新登录 → 再跑一次上面的 `refresh_cookies xhs` |
| **弹出人机验证码** | 在 Chrome 手动完成验证；抓取器已内置**验证码检测**，触发即停当轮不硬刷 |
| **查看抓取健康状态** | `corpus_cache/daily/scrape_health.json`（每源记录 ok / 登录失效 / 风控 + 下一步） |
| **全量覆盖（2-3 天）** | 每 4 小时计划任务 × 小批量（35 词/轮，带随机抖动），`scrape_state` 轮转不重复 |
| **Boss 详情受限** | 停手 1-2 天让其冷却；详情预检会自动跳过风控期，靠每日任务恢复 |

> ⚠️ 用 Playwright 主源时，需保持那个 **已登录的专用 Chrome 开着**——计划任务靠它抓取。
> 反爬的本质是「频率」：小批量 + 随机抖动 = 真人级节奏，一次性抓几百词必触发验证码。

<details>
<summary>命令行抓取 / 定时任务安装</summary>

```bash
# 小红书单轮温和抓取（35 词，供每 4 小时计划任务调用）
python -m scripts.tools.xhs_batch_run data       # 数据开发
python -m scripts.tools.xhs_batch_run ai_app     # Agent 开发

# 拉取在招岗位
python -m scripts.run_jobs --role-id data

# 安装每日定时抓取（跨平台：Task Scheduler / cron）
python -m scripts.tools.install_daily_schedule --hour 9 --minute 30 --role-ids data,ai_app
```
</details>

---

## 🧩 支持的岗位

| 岗位 | `role_id` | 关键技术方向 |
|------|-----------|-------------|
| 数据开发 | `data` | Spark / Flink / Hive / 数仓 / ETL |
| Agent / AI 应用开发 | `ai_app` | RAG / Agent / MCP / LLM 应用 |

目标公司锁定互联网大厂（字节 / 腾讯 / 阿里 / 美团 / 京东 / 百度 / 快手 / 网易 / 滴滴 / 小红书 / bilibili / 拼多多 / OPPO / vivo / 华为 / 小米 等），其余归入「其他」。

---

## 🏗️ 项目结构

```
scripts/
├── api/            Web UI 后端 + 前端静态资源（server.py / static/）
├── corpus/         面经流水线：ai_gate 过滤聚类 · extract_questions 提题
│                   dedupe_rank 频次×时效排序 · semantic_merge 语义去重
├── scrape/         小红书抓取：xhs_playwright_driver（主）· spider_xhs_driver（回退）
│                   scrape_health 健康状态 · xhs_batch_run 温和批量
├── jobs/           岗位抓取：connectors/（boss_drission · job_pro · 各大厂官网）
│                   tech_stack 技术栈分析 · salary 薪资分析
├── ocr/            图片下载 + RapidOCR pipeline（视觉大模型兜底）
├── tools/          refresh_cookies 一键重认证 · install_daily_schedule 定时任务
├── service.py      面经主流水线入口
└── models.py       RawPost / Question 数据模型
config/company_aliases.yaml   公司名归一化
corpus_cache/                 运行时数据（题库 / 岗位快照 / 图片，gitignored）
```

---

## 🎯 设计原则

1. **AI First** — 能用 DeepSeek 解决的判断（筛帖 / 归类 / 去重 / 解答）不写死规则，正则只作离线兜底；模型名配置驱动，上游改名不影响代码。
2. **复用开源** — OCR→RapidOCR · 相似度→rapidfuzz · 浏览器→Playwright / DrissionPage，不造轮子。
3. **增量优先 & 韧性** — 抓取全程增量去重；失败优雅降级、状态可见、绝不用空结果覆盖好数据。
4. **并发 + 缓存降本** — 过滤与题目聚类的 DeepSeek 调用并发执行（深度重建从 1 小时压到几分钟）；聚类结果按题目内容缓存，重建只算新增批次，token 消耗大幅下降。

---

## ⚠️ 已知限制

- 小红书 Cookie 约 1-2 周失效，需重登 + `refresh_cookies` 更新（已做到一条命令）。
- 图片帖 OCR 对低分辨率 / 竖排文字识别有限，可配视觉大模型兜底。
- Boss JD 详情接口易触发风控，高频查询需冷却，靠每日任务缓慢恢复。

---

## 📜 免责声明

本项目是**面向个人的自托管学习/研究工具**，仅供个人求职备考使用。使用前请知悉：

- **数据抓取的合规责任由使用者自行承担。** 是否抓取、如何抓取、抓取频率，均由你在本地用自己的账号登录态触发；请遵守小红书、牛客、Boss 直聘及各来源平台的用户协议、`robots` 规则与相关法律法规。项目作者不对使用者的抓取行为负责。
- **本仓库不内置、不分发任何抓取到的面经/岗位数据**，所有内容均由使用者在本地自行抓取并存于本地缓存（`corpus_cache/`，已 gitignore）。
- **请勿用于商业用途、大规模抓取、或对外分发抓取内容**；请自觉控制频率，尊重目标平台。
- 抓取到的面经/简历等可能含个人信息，请妥善保管本地数据；简历上传处理后即从服务端删除。
- 本软件按“原样”提供，不含任何明示或默示担保，使用风险自负（详见 [LICENSE](LICENSE)）。

> 简言之：这是给你**自己在本机跑、用自己的账号、看自己的备考题库**的工具。怎么用、是否合规，取决于你。

---

## 🙏 致谢

本项目基于并致敬原作 **[KunChen1110/InterviewRadar](https://github.com/KunChen1110/InterviewRadar)**（作者 [@KunChen1110](https://github.com/KunChen1110)）。

原作确立了这套方法论与工程骨架——**Agent 编排 + Python 确定性处理**的分工、`RawPost`/`Question` 数据模型、`connectors / corpus / ocr` 分层、按频次×时效排序与语义去重的面经流水线。本项目在此基础上做了数据/Agent 岗位方向的**垂直重工程化**：自研 Playwright 小红书驱动、岗位与薪资分析、交互式模拟面试、抓取健壮性（断点续抓 / 抗风控 / 健康状态）、Web UI 与一键自托管等。

衷心感谢原作者的开创性工作。若你想要更**通用、可追溯、Agent 原生**的版本，推荐直接使用原作。

---

## 📜 License

MIT — 详见 [LICENSE](LICENSE)，保留原作版权声明。

<div align="center">

Built with [Claude Code](https://claude.com/claude-code)

</div>
