# AI 热点日报 → 飞书卡片推送

每天自动抓取 AI 热点新闻，用户选择条目后以飞书消息卡片推送到群聊。

## 文件清单

| 文件 | 用途 |
|------|------|
| `ai_news_sender.py` | 主脚本：爬取新闻、构建卡片、发送到飞书 |
| `config.json` | 飞书应用凭证 + 正式群/测试群 chat_id |
| `banner.html` | 头图 HTML 模板（自动渲染当天日期） |
| `banner.png` | 头图底图（html2image 渲染后上传飞书） |
| `setup_new_mac.sh` | 新电脑一键部署脚本（检测 Python/Chrome、装依赖、注册 launchd） |
| `today_cache.json` | 当日新闻缓存（`--push-list` 时生成，当天有效） |
| `today_selection.json` | 用户选择的条目（`--preview` 时生成，当天有效） |
| `使用说明.md` | 面向人类的完整使用文档 |

## 每日工作流

```
08:50  launchd 自动执行 --send-reminder
       → 抓取最新新闻 + 刷新头图日期 + 推送提醒卡片到测试群

用户   终端运行 --preview
       → 交互式选择条目 + 推送预览卡片到测试群

09:30  launchd 自动执行 --send-production
       → 按用户选的条目推送正式卡片到正式群
       → 如果用户没跑 --preview，自动每类取 2 条兜底
```

## 命令

```bash
python3 ai_news_sender.py --push-list         # 抓取 + 推送新闻列表到测试群
python3 ai_news_sender.py --preview            # 交互式选条目 + 推送预览到测试群
python3 ai_news_sender.py --send-production    # 按选中条目推送到正式群
python3 ai_news_sender.py --send-reminder      # 推送提醒卡片到测试群（08:50 定时用）
python3 ai_news_sender.py --refresh-banner     # 单独刷新头图日期
```

## 卡片格式规范（当前版本）

### 正式卡片（build_card）

- **标题**：`🚀 AI岛 · 热点日报  |  {日期}`
- **副标题**：各分类名用 ` · ` 连接
- **头图**：banner.png 渲染当天日期后上传飞书
- **日期行**：头图下方直接展示 `{日期} | 共抓取 X 条 AI 热点`，紧接分割线
- **分类标题**：中文序号 + 粗体，如 `**一、模型发布/更新**`（字号小于卡片标题）
- **内容格式**：每条 = 加粗标题 + 正文摘要（≤120字） + `[查看原文](url)` 链接，自动编号
- **结尾**：分割线 → `数据集成来源：https://aihot.virxact.com/daily | HH:MM 发送`
- **主题色**：`blue`
- **分类背景**：统一 `blue-50`（column_set）

### 提醒卡片（build_list_card，8:50 推送）

- 样式与正式卡片一致（标题、头图、日期行相同）
- 展示所有可见分类的全部条目（仅标题 + 链接，无正文摘要）
- 底部提示：`请在终端运行 python3 ai_news_sender.py --preview 选择要发送的条目，正式卡片将以你选的条目为准。`

## 配置

### config.json

```json
{
  "_说明": "飞书应用凭证和目标群聊配置",
  "app_id": "cli_xxxx",
  "app_secret": "xxxx",
  "production_chat_id": "oc_正式群ID",
  "test_chat_id": "oc_测试群ID"
}
```

飞书应用需开通 `im:message:send_as_bot` 权限，机器人需被拉入正式群和测试群。

### 脚本内可调配置

- `HIDDEN_CATEGORIES`：爬取但不展示的分类（当前：`{"论文研究"}`）
- `CATEGORY_BG`：分类背景色映射（飞书颜色枚举）
- `BANNER_IMG_KEY`：飞书已上传的头图 img_key（`--refresh-banner` 会自动更新）

## 新电脑部署

1. 将整个 `AI热点/` 目录拷贝到新电脑
2. 确保已安装 Google Chrome 和 Python 3
3. 运行 `bash setup_new_mac.sh`
4. 脚本会自动：检测 Python → 安装依赖 → 修补硬编码路径 → 注册 launchd 定时任务 → 设置工作日唤醒

### 电源管理（保证定时任务执行）

- 接电源时系统不自动休眠：`sudo pmset -c sleep 0 disksleep 0`
- 工作日 08:45 自动唤醒：`sudo pmset repeat wake MTWRF 08:45:00`
- 合盖需外接显示器才能保持唤醒；无外接屏建议用 Amphetamine App

## 常见问题

**头图日期没更新** → 运行 `--refresh-banner`，需 Chrome + html2image

**定时任务没执行** → `launchctl list | grep ainews` 检查状态；看日志 `/tmp/ai_news_production.log`

**想改分类背景色** → 编辑脚本顶部 `CATEGORY_BG` 字典

**想隐藏某个分类** → 编辑 `HIDDEN_CATEGORIES`，加入分类名

**想改定时时间** → 编辑 `~/Library/LaunchAgents/com.ainews.*.plist` 中的 Hour/Minute，然后 unload + load
