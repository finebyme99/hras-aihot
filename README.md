## AI热点日报 → 飞书卡片推送（v3 工作流版）

一个 Python 脚本，每天自动爬取 [aihot.virxact.com/daily](https://aihot.virxact.com/daily) 的 AI 热点，支持你在终端逐条选择后，以精美卡片推送到飞书群聊。

---

### 每日工作流

```
08:50  系统自动抓取新闻 + 刷新头图日期 → 推送提醒卡片到测试群
       （你会在飞书收到一张卡片，展示今天所有热点，提醒你来选条目）

你来    终端运行 --preview，按编号选条目 → 预览卡片推送到测试群
       （去飞书看看效果，满意就结束）

09:30  系统自动按你选的条目 → 推送到正式群
       （定时任务自动执行，你不用做任何操作）
```

> 如果 09:30 前没有跑过 --preview，系统会自动选取每类 2 条作为兜底。

---

### 命令一览

```bash
# ① 抓取新闻 + 推送新闻列表到测试群
python3 ai_news_sender.py --push-list

# ② 逐条选择 + 推送预览卡片到测试群
python3 ai_news_sender.py --preview

# ③ 推送到正式群（定时任务自动调用，也可手动触发）
python3 ai_news_sender.py --send-production

# ④ 发送提醒卡片到测试群（定时任务自动调用）
python3 ai_news_sender.py --send-reminder

# 单独刷新头图日期
python3 ai_news_sender.py --refresh-banner
```

---

### --preview 选择流程

运行 `--preview` 后，终端会列出今天所有新闻条目（按分类分组、统一编号），你直接输入想发送的编号即可：

```
  今日 AI 热点（共 20 条）：
  ====================================================

  ▸ 模型发布/更新
   1. Claude Fable 5 和 Claude Mythos 5
   2. Google DeepMind 发布 Gemma 4 12B
   ...

  ▸ 产品发布/更新
   5. Luma AI Ray3.2 API
   ...

  ▸ 行业动态
  10. xxx ...
   ...

  ▸ 技巧与观点
  15. xxx ...
   ...

  ====================================================
  输入序号选择要发送的条目（如 1,3,5,8），
  全部选直接回车，q 取消

  选条目 > 1,2,7,12,19
```

选完后脚本会自动按分类归组、套用卡片模板、推送到测试群，同时保存你的选择供 09:30 定时任务复用。

---

### 定时任务（macOS launchd）

使用 macOS 原生 launchd 调度，不依赖 QoderWork 或 crontab，电脑休眠醒来后会补执行错过的任务。

| 时间 | 任务 | 功能 |
|------|------|------|
| 每天 08:50 | `com.ainews.reminder` | 抓取新闻 + 刷新头图 + 推送提醒卡片到测试群 |
| 每天 09:30 | `com.ainews.production` | 按选中条目推送正式卡片到正式群 |

plist 文件位置：`~/Library/LaunchAgents/`

常用管理命令：

```bash
# 查看任务状态
launchctl list | grep ainews

# 手动触发（不等定时）
launchctl start com.ainews.reminder
launchctl start com.ainews.production

# 停用任务
launchctl unload ~/Library/LaunchAgents/com.ainews.reminder.plist
launchctl unload ~/Library/LaunchAgents/com.ainews.production.plist

# 重新启用
launchctl load ~/Library/LaunchAgents/com.ainews.reminder.plist
launchctl load ~/Library/LaunchAgents/com.ainews.production.plist
```

日志位置：`/tmp/ai_news_reminder.log` 和 `/tmp/ai_news_production.log`

---

### 卡片效果

```
┌──────────────────────────────────────┐
│ ▓▓▓▓▓▓▓▓ 头图（自动渲染日期）▓▓▓▓▓▓▓ │
│      AI岛 · 热点日报  |  2026-06-17   │
├──────────────────────────────────────┤
│ 🚀 AI岛 · 热点日报  |  2026-06-17    │  ← blue 标题栏
│ 模型发布/更新 · 产品发布/更新 · ...    │  ← 副标题（分类名 · 连接）
├──────────────────────────────────────┤
│ 2026-06-17 | 共抓取 X 条 AI 热点     │
│──────────────────────────────────────│
│ ╭─ blue-50 浅蓝背景 ─────────────╮  │
│ │ **一、模型发布/更新**             │  │  ← 中文序号 + 粗体（小于标题字号）
│ │ 1. **Claude Fable 5 ...**       │  │
│ │    Anthropic 今日推出...         │  │
│ │    [查看原文](url)               │  │
│ ╰─────────────────────────────────╯  │
│──────────────────────────────────────│
│ ╭─ blue-50 浅蓝背景 ─────────────╮  │
│ │ **二、产品发布/更新**             │  │
│ │ 1. **Luma AI Ray3.2 API ...**   │  │
│ ╰─────────────────────────────────╯  │
│──────────────────────────────────────│
│ 数据集成来源: aihot.virxact.com/daily │
│ 09:30 发送                            │
└──────────────────────────────────────┘
```

隐藏分类：论文研究（爬取但不默认展示）。行业动态可选——用户 --preview 选了才推，没选就不推。

---

### 配置文件

`config.json`：

```json
{
  "_说明": "飞书应用凭证和目标群聊配置",
  "app_id": "cli_xxxx",
  "app_secret": "xxxx",
  "production_chat_id": "oc_正式群ID",
  "test_chat_id": "oc_测试群ID"
}
```

- **app_id / app_secret**：在 [飞书开放平台](https://open.feishu.cn) 创建企业自建应用获取，需开通 `im:message:send_as_bot` 权限。
- **production_chat_id**：正式群聊 ID。
- **test_chat_id**：测试群聊 ID，所有预览和提醒都发到这里。

---

### 依赖安装

```bash
pip3 install requests beautifulsoup4 html2image
```

- `requests`：HTTP 请求（爬取网页 + 调用飞书 API）
- `beautifulsoup4`：HTML 解析
- `html2image`：渲染头图 HTML → PNG（需要 Google Chrome）

---

### 文件说明

```
AI热点/
├── ai_news_sender.py        ← 主脚本（爬取 + 选择 + 构建卡片 + 发送）
├── config.json              ← 配置（飞书凭证、群聊 ID）
├── banner.html              ← 头图模板（HTML/CSS，自动渲染当天日期）
├── banner.png               ← 头图底图
├── today_cache.json         ← 当日新闻缓存（--push-list 时生成，当天有效）
├── today_selection.json     ← 你的选择记录（--preview 时生成，当天有效）
├── setup_new_mac.sh         ← 新电脑一键部署脚本
├── AGENTS.md                ← Agent 工作手册（新 agent 自动读取）
└── 使用说明.md               ← 本文件
```

---

### 新电脑部署

1. 将整个 `AI热点/` 目录拷贝到新电脑
2. 确保已安装 Google Chrome 和 Python 3
3. 运行 `bash setup_new_mac.sh`
4. 脚本自动完成：检测 Python → 安装依赖 → 修补路径 → 注册定时任务 → 设置唤醒

电源管理（保证定时任务执行）：
- 接电源时不自动休眠：`sudo pmset -c sleep 0 disksleep 0`
- 工作日自动唤醒：`sudo pmset repeat wake MTWRF 08:45:00`
- 合盖需外接显示器才能保持唤醒；无外接屏建议用 Amphetamine App

---

### 常见问题

**Q: 头图日期没更新？**
运行 `--refresh-banner` 或 `--send-reminder`（自动刷新），需要安装 html2image 且电脑上有 Chrome。

**Q: 定时任务没执行？**
检查 launchd 状态：`launchctl list | grep ainews`。如果无输出，重新 load plist 文件。查看日志 `/tmp/ai_news_production.log` 定位原因。

**Q: 想改定时时间？**
编辑 `~/Library/LaunchAgents/com.ainews.reminder.plist` 和 `com.ainews.production.plist` 中的 `Hour` / `Minute`，然后 unload + load 重新加载。

**Q: 想隐藏某个分类？**
编辑脚本顶部的 `HIDDEN_CATEGORIES`，加入分类名即可。

**Q: 想改分类背景色？**
编辑脚本顶部的 `CATEGORY_BG` 字典，值是飞书颜色枚举（blue-50、wathet-50、indigo-50 等）。
