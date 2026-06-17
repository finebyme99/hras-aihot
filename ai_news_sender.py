#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI热点日报 → 飞书卡片推送（轻量版 v3）
=========================================
三步工作流：
  ① 抓取新闻 → 推送列表到测试群（你在飞书上看今天有哪些热点）
  ② 选择内容 → 推送预览卡片到测试群（确认效果）
  ③ 定时自动 → 推送到正式群（每天 09:30 由定时任务触发）

依赖安装（终端执行一次即可）：
    pip3 install requests beautifulsoup4 html2image

使用方法：
    python3 ai_news_sender.py --push-list         # ① 抓取 + 推送新闻列表到测试群
    python3 ai_news_sender.py --preview            # ② 选内容 + 推送预览卡片到测试群
    python3 ai_news_sender.py --send-production    # ③ 自动发送到正式群（定时任务用）
    python3 ai_news_sender.py --send-reminder      # ④ 发送提醒卡片到测试群（8:50定时用）
    python3 ai_news_sender.py --refresh-banner     # 单独刷新头图日期
"""

import json
import sys
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─── 日志 ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── 路径 ───────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
CACHE_PATH = SCRIPT_DIR / "today_cache.json"
SELECTION_PATH = SCRIPT_DIR / "today_selection.json"
SOURCE_URL = "https://aihot.virxact.com/daily"

# 分类配置
# HIDDEN_CATEGORIES: 爬取到但不默认展示的分类
HIDDEN_CATEGORIES = {"论文研究"}

CATEGORY_STYLE = {
    "模型发布/更新": {},
    "产品发布/更新": {},
    "行业动态":     {},
    "论文研究":     {},
    "技巧与观点":   {},
}
DEFAULT_STYLE = {}

# 头图 img_key（通过飞书 API 上传获得，新电脑本机 key）
BANNER_IMG_KEY = "img_v3_0212o_88472918-b5a0-4bb8-b4cc-f7f3f25e0f0g"

# 分类背景色（飞书颜色枚举，蓝色系）
CATEGORY_BG = {
    "模型发布/更新": "blue-50",
    "产品发布/更新": "wathet-50",
    "行业动态":     "indigo-50",
    "论文研究":     "violet-50",
    "技巧与观点":   "turquoise-50",
}
DEFAULT_BG = "grey-50"

# 每个分类默认取几条
DEFAULT_PER_CATEGORY = 2


# ╔══════════════════════════════════════════════════════════╗
# ║  配置管理                                                ║
# ╚══════════════════════════════════════════════════════════╝

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        default = {
            "_说明": "把 <...> 替换成你自己的值，保存后重新运行脚本",
            "app_id": "<你的APP_ID>",
            "app_secret": "<你的APP_SECRET>",
            "receive_ids": ["<群聊chat_id>"],
        }
        CONFIG_PATH.write_text(
            json.dumps(default, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("已生成配置模板 → %s", CONFIG_PATH)
        log.info("请先编辑 config.json，填入你自己的飞书应用凭证，再运行。")
        sys.exit(0)

    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    for key in ("app_id", "app_secret"):
        val = cfg.get(key, "")
        if not val or val.startswith("<"):
            log.error("config.json 中 %s 未填写，请先编辑！", key)
            sys.exit(1)

    return cfg


# ╔══════════════════════════════════════════════════════════╗
# ║  新闻缓存：抓取结果存本地，跨步骤复用                        ║
# ╚══════════════════════════════════════════════════════════╝

def save_cache(categorized: dict):
    """把抓取的新闻保存到本地缓存文件"""
    data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
        "data": categorized,
    }
    CACHE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("新闻缓存已保存 → %s（%d 条）",
             CACHE_PATH, sum(len(v) for v in categorized.values()))


def load_cache() -> dict | None:
    """加载本地缓存，过期或不存在返回 None"""
    if not CACHE_PATH.exists():
        return None
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        cached_date = raw.get("date", "")
        today = datetime.now().strftime("%Y-%m-%d")
        if cached_date != today:
            log.warning("缓存日期 %s 不是今天 %s，已过期", cached_date, today)
            return None
        return raw.get("data", {})
    except Exception as e:
        log.warning("读取缓存失败: %s", e)
        return None


# ╔══════════════════════════════════════════════════════════╗
# ║  选择缓存：预览时的选择存本地，定时任务复用                    ║
# ╚══════════════════════════════════════════════════════════╝

def save_selection(selected: dict):
    """把用户预览时选的新闻条目保存下来，供定时任务复用"""
    data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
        "data": selected,
    }
    SELECTION_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    total = sum(len(v) for v in selected.values())
    log.info("选择已保存 → %s（%d 条）", SELECTION_PATH, total)


def load_selection() -> dict | None:
    """加载用户之前的选择，过期或不存在返回 None"""
    if not SELECTION_PATH.exists():
        return None
    try:
        raw = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
        sel_date = raw.get("date", "")
        today = datetime.now().strftime("%Y-%m-%d")
        if sel_date != today:
            log.warning("选择缓存日期 %s 不是今天 %s，已过期", sel_date, today)
            return None
        data = raw.get("data", {})
        if not data:
            return None
        return data
    except Exception as e:
        log.warning("读取选择缓存失败: %s", e)
        return None


# ╔══════════════════════════════════════════════════════════╗
# ║  头图刷新：重新渲染 HTML → PNG → 上传飞书                  ║
# ╚══════════════════════════════════════════════════════════╝

BANNER_HTML_PATH = SCRIPT_DIR / "banner.html"


def refresh_banner(cfg: dict) -> str:
    """
    重新渲染 banner.html → PNG → 上传飞书，返回新的 img_key。
    失败时返回原来的 BANNER_IMG_KEY。
    """
    global BANNER_IMG_KEY

    if not BANNER_HTML_PATH.exists():
        log.warning("banner.html 不存在，跳过头图刷新")
        return BANNER_IMG_KEY

    try:
        from html2image import Html2Image
        import tempfile

        log.info("正在重新渲染头图（日期自动更新）...")

        with tempfile.TemporaryDirectory() as tmpdir:
            hti = Html2Image(
                browser_executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                output_path=tmpdir,
                size=(1250, 500),
            )
            html_content = BANNER_HTML_PATH.read_text(encoding="utf-8")
            hti.screenshot(html_str=html_content, save_as="banner_today.png")

            png_path = Path(tmpdir) / "banner_today.png"
            if not png_path.exists():
                log.warning("头图渲染失败，使用旧图")
                return BANNER_IMG_KEY

            img_data = png_path.read_bytes()

        # 上传到飞书
        token = get_tenant_token(cfg["app_id"], cfg["app_secret"])
        if not token:
            log.warning("获取 Token 失败，头图上传跳过")
            return BANNER_IMG_KEY

        r = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "image_type": (None, "message"),
                "image": ("banner.png", img_data, "image/png"),
            },
            timeout=30,
        )
        result = r.json()
        if result.get("code") == 0:
            new_key = result["data"]["image_key"]
            BANNER_IMG_KEY = new_key
            log.info("头图刷新成功！新 img_key=%s", new_key)
            return new_key
        else:
            log.warning("头图上传失败: %s，使用旧图", result)
            return BANNER_IMG_KEY

    except ImportError:
        log.warning("html2image 未安装，跳过头图刷新。安装命令：pip3 install html2image")
        return BANNER_IMG_KEY
    except Exception as e:
        log.warning("头图刷新异常: %s，使用旧图", e)
        return BANNER_IMG_KEY


# ╔══════════════════════════════════════════════════════════╗
# ║  爬取新闻（按分类）                                       ║
# ╚══════════════════════════════════════════════════════════╝

def scrape_categorized_news() -> dict[str, list[dict]]:
    """
    抓取当天新闻，按分类返回。
    返回: {"模型发布/更新": [...], "产品发布/更新": [...], ...}
    """
    log.info("正在抓取 %s ...", SOURCE_URL)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(SOURCE_URL, headers=headers, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")
    categorized = {}

    # 按 section.daily-section 提取分类和文章
    sections = soup.select("section.daily-section")
    for sec in sections:
        h = sec.select_one("h2, h3")
        cat_name = h.get_text(strip=True) if h else "其他"

        articles = sec.select("article.daily-article")
        items = []
        for art in articles:
            item = _extract_article(art)
            if item:
                items.append(item)

        if items:
            categorized[cat_name] = items

    # 兜底：如果 section 结构不存在，平铺所有 article 到"全部"
    if not categorized:
        articles = soup.select("article.daily-article")
        all_items = [_extract_article(a) for a in articles]
        all_items = [x for x in all_items if x]
        if all_items:
            categorized["全部"] = all_items

    # 去重（每个分类内按标题去重）
    for cat in categorized:
        seen, unique = set(), []
        for n in categorized[cat]:
            if n["title"] not in seen:
                seen.add(n["title"])
                unique.append(n)
        categorized[cat] = unique

    total = sum(len(v) for v in categorized.values())
    log.info("共抓取 %d 条新闻，%d 个分类", total, len(categorized))
    return categorized


def _extract_article(art) -> dict | None:
    """从 article 元素提取一条新闻"""
    title_el = art.select_one("h3.daily-article-title")
    summary_el = art.select_one(".daily-article-summary")
    source_el = art.select_one(".daily-article-source")

    title = _text(title_el)
    if not title:
        return None

    url = ""
    for a in art.select("a[href]"):
        href = a.get("href", "")
        if href.startswith("http"):
            url = href
            break

    if url and not url.startswith("http"):
        url = f"https://aihot.virxact.com{url}"

    return {
        "title": title,
        "content": _text(summary_el),
        "url": url,
        "source": _text(source_el),
    }


def _text(el) -> str:
    return el.get_text(strip=True) if el else ""


# ╔══════════════════════════════════════════════════════════╗
# ║  交互式选择：你来挑哪些分类 & 每类取几条                     ║
# ╚══════════════════════════════════════════════════════════╝

def interactive_select(categorized: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """
    展示所有新闻条目，让你逐条挑选要发送哪些。
    选完后自动按分类归组，套用卡片模板。
    """
    # 过滤掉隐藏分类
    visible_cats = {k: v for k, v in categorized.items() if k not in HIDDEN_CATEGORIES}

    # 构建编号列表
    all_items = []
    for cat_name, items in visible_cats.items():
        for item in items:
            all_items.append({**item, "_cat": cat_name})

    if not all_items:
        log.warning("没有可显示的新闻条目")
        return {}

    print()
    print(f"  今日 AI 热点（共 {len(all_items)} 条）：")
    print("  " + "=" * 52)

    current_cat = ""
    for i, item in enumerate(all_items, 1):
        if item["_cat"] != current_cat:
            current_cat = item["_cat"]
            print(f"\n  ▸ {current_cat}")
        t = item["title"]
        if len(t) > 50:
            t = t[:47] + "..."
        print(f"  {i:2d}. {t}")

    print()
    print("  " + "=" * 52)
    print("  输入序号选择要发送的条目（如 1,3,5,8），")
    print("  全部选直接回车，q 取消")
    print()

    while True:
        raw = input("  选条目 > ").strip()
        if raw == "":
            selected_items = all_items
            break
        if raw.lower() == "q":
            return {}
        try:
            indices = [int(x.strip()) for x in raw.replace("，", ",").split(",") if x.strip()]
            valid = [i for i in indices if 1 <= i <= len(all_items)]
            if not valid:
                print(f"  [!] 请输入 1~{len(all_items)} 的数字")
                continue
            selected_items = [all_items[i - 1] for i in valid]
            break
        except ValueError:
            print("  [!] 格式不对，请输入数字，如：1,3,5,8")

    # 按分类归组（保持原始分类顺序）
    result = {}
    for item in selected_items:
        cat = item["_cat"]
        if cat not in result:
            result[cat] = []
        clean = {k: v for k, v in item.items() if k != "_cat"}
        result[cat].append(clean)

    # 按 categorized 的原始顺序排列分类
    ordered = {}
    for cat in categorized:
        if cat in result:
            ordered[cat] = result[cat]

    total = sum(len(v) for v in ordered.values())
    log.info("你选了 %d 条新闻，涉及 %d 个分类", total, len(ordered))
    return ordered


# ╔══════════════════════════════════════════════════════════╗
# ║  构建飞书卡片                                            ║
# ╚══════════════════════════════════════════════════════════╝

def build_card(selected: dict[str, list[dict]], banner_key: str = "") -> str:
    """
    构建飞书卡片 JSON（v2 格式，复刻旧版"AI岛·热点日报"样式）。
    结构：头图 → 标题+副标题 → 顶部 nav 分类条 → 日期摘要 →
          各分类区块（column_set + 蓝色背景）→ 底部"AI Land · 智多星"署名

    banner_key: 外部传入的 img_key，缺省时使用模块级 BANNER_IMG_KEY
    """
    img_key = banner_key or BANNER_IMG_KEY
    today = datetime.now().strftime("%Y-%m-%d")
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[datetime.now().weekday()]

    # 副标题：分类名用 · 连接
    subtitle_text = " · ".join(selected.keys())
    total = sum(len(v) for v in selected.values())

    elements = []

    # ── 头图 ──
    if img_key:
        elements.append({
            "tag": "img",
            "img_key": img_key,
            "alt": {"tag": "plain_text", "content": "AI岛 · 热点日报"},
        })

    # ── 日期摘要（图片下方直接展示） ──
    elements.append({
        "tag": "markdown",
        "content": f"**{today}**  |  共抓取 {total} 条 AI 热点",
    })
    elements.append({"tag": "hr"})

    # ── 各分类区块：统一浅蓝蓝色，加中文序号，缩小分类标题 ──
    cn_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    for idx, (cat_name, items) in enumerate(selected.items()):
        if not items:
            continue

        cn_prefix = cn_nums[idx] if idx < len(cn_nums) else str(idx + 1)

        # 构建分类内的新闻列表 markdown
        news_lines = []
        for i, item in enumerate(items, 1):
            title = item["title"]
            content = item["content"]
            url = item["url"]

            if len(content) > 120:
                content = content[:117] + "..."

            lines = [f"**{i}. {title}**"]
            if content:
                lines.append(content)
            if url:
                lines.append(f"[查看原文]({url})")
            news_lines.append("\n".join(lines))

        inner_content = "\n\n".join(news_lines)

        # 统一 blue-50 浅蓝背景，分类标题用粗体（小于卡片标题字号）
        elements.append({
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "blue-50",
            "columns": [{
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "padding": "16px 16px 16px 16px",
                "elements": [
                    {"tag": "markdown", "content": f"**{cn_prefix}、{cat_name}**"},
                    {"tag": "markdown", "content": inner_content},
                ],
            }],
        })

        elements.append({"tag": "hr"})

    # ── 结尾：分割线 + 数据来源 + 发送时间 ──
    elements.append({
        "tag": "markdown",
        "content": f"数据集成来源：[https://aihot.virxact.com/daily](https://aihot.virxact.com/daily)  |  {datetime.now().strftime('%H:%M')} 发送",
    })

    # 飞书卡片限制 50 个 elements
    if len(elements) > 50:
        log.warning("卡片元素超过 50 个（%d），已截断", len(elements))
        elements = elements[:49]

    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"🚀 AI岛 · 热点日报  |  {today}",
            },
            "subtitle": {
                "tag": "plain_text",
                "content": subtitle_text,
            },
            "template": "blue",
        },
        "body": {
            "elements": elements,
        },
    }

    return json.dumps(card, ensure_ascii=False)


def build_list_card(categorized: dict[str, list[dict]], banner_key: str = "") -> str:
    """
    构建「新闻列表」卡片（推送到测试群，方便浏览今天有哪些热点）。
    简洁文本列表，不含头图，方便快速浏览后做选择。
    """
    img_key = banner_key or BANNER_IMG_KEY
    today = datetime.now().strftime("%Y-%m-%d")
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[datetime.now().weekday()]
    total = sum(len(v) for v in categorized.values())

    elements = []

    # ── 头图（与正式卡一致） ──
    if img_key:
        elements.append({
            "tag": "img",
            "img_key": img_key,
            "alt": {"tag": "plain_text", "content": "AI岛 · 热点日报"},
        })

    # ── 日期摘要（图片下方直接展示） ──
    elements.append({
        "tag": "markdown",
        "content": f"**{today}**  |  共抓取 {total} 条 AI 热点",
    })
    elements.append({"tag": "hr"})

    # 各分类的新闻列表
    for cat_name, items in categorized.items():
        if not items:
            continue

        lines = []
        for i, item in enumerate(items, 1):
            title = item["title"]
            url = item["url"]
            if url:
                lines.append(f"{i}. [{title}]({url})")
            else:
                lines.append(f"{i}. {title}")

        content = "\n".join(lines)

        elements.append({
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "blue-50",
            "columns": [{
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "padding": "16px 16px 16px 16px",
                "elements": [
                    {"tag": "markdown", "content": f"## {cat_name}（{len(items)} 条）"},
                    {"tag": "markdown", "content": content},
                ],
            }],
        })

        elements.append({"tag": "hr"})

    # 提示：引导用户执行 --preview 选择条目
    elements.append({
        "tag": "markdown",
        "content": "请在终端运行 `python3 ai_news_sender.py --preview` 选择要发送的条目，正式卡片将以你选的条目为准。",
    })

    # 结尾：数据来源
    elements.append({
        "tag": "markdown",
        "content": f"数据集成来源：[https://aihot.virxact.com/daily](https://aihot.virxact.com/daily)  |  {datetime.now().strftime('%H:%M')} 发送",
    })

    # 飞书卡片限制 50 个 elements
    if len(elements) > 50:
        elements = elements[:49]

    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"🚀 AI岛 · 热点日报  |  {today}",
            },
            "subtitle": {
                "tag": "plain_text",
                "content": f"共 {total} 条 · {len(categorized)} 个分类",
            },
            "template": "blue",
        },
        "body": {
            "elements": elements,
        },
    }

    return json.dumps(card, ensure_ascii=False)


def build_reminder_card() -> str:
    """构建提醒卡片：提醒用户运行预览脚本"""
    today = datetime.now().strftime("%Y-%m-%d")
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[datetime.now().weekday()]

    elements = [
        {
            "tag": "markdown",
            "content": f"**{today} {weekday}**",
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": "今日 AI 热点已就绪，请在终端运行以下命令选择并预览卡片：",
        },
        {
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "turquoise-50",
            "columns": [{
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "padding": "16px 16px 16px 16px",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "```\npython3 /Users/zt26278/Q/AI/26AI落地/AI热点/ai_news_sender.py --preview\n```",
                    },
                ],
            }],
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": "选择完成后预览卡片将推送到本群，确认效果后运行：",
        },
        {
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "blue-50",
            "columns": [{
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "padding": "16px 16px 16px 16px",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "```\npython3 /Users/zt26278/Q/AI/26AI落地/AI热点/ai_news_sender.py --send-production\n```",
                    },
                ],
            }],
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": f"数据集成来源：[https://aihot.virxact.com/daily](https://aihot.virxact.com/daily)",
        },
    ]

    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"📋 AI热点日报 · 操作提醒  |  {today}",
            },
            "subtitle": {
                "tag": "plain_text",
                "content": "请运行脚本完成今日热点推送",
            },
            "template": "turquoise",
        },
        "body": {
            "elements": elements,
        },
    }

    return json.dumps(card, ensure_ascii=False)


# ╔══════════════════════════════════════════════════════════╗
# ║  发送飞书消息                                            ║
# ╚══════════════════════════════════════════════════════════╝

def get_tenant_token(app_id: str, app_secret: str) -> str:
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        r = requests.post(url, json={
            "app_id": app_id,
            "app_secret": app_secret,
        }, timeout=10)
        token = r.json().get("tenant_access_token", "")
        if token:
            log.info("Token 获取成功")
        else:
            log.error("Token 获取失败: %s", r.json())
        return token
    except Exception as e:
        log.error("获取 Token 异常: %s", e)
        return ""


def send_card_to_group(chat_id: str, token: str, card_json: str) -> bool:
    api = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    try:
        r = requests.post(api, headers=headers, json={
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": card_json,
        }, timeout=10)
        result = r.json()
        if result.get("code") == 0:
            msg_id = result.get("data", {}).get("message_id")
            log.info("发送成功！message_id=%s", msg_id)
            return True
        log.error("发送失败: code=%s msg=%s", result.get("code"), result.get("msg"))
        return False
    except Exception as e:
        log.error("发送异常: %s", e)
        return False


# ╔══════════════════════════════════════════════════════════╗
# ║  主流程                                                 ║
# ╚══════════════════════════════════════════════════════════╝

def main():
    push_list = "--push-list" in sys.argv
    preview = "--preview" in sys.argv
    send_prod = "--send-production" in sys.argv
    send_reminder = "--send-reminder" in sys.argv
    refresh_flag = "--refresh-banner" in sys.argv

    # 兼容旧用法
    auto_mode = "--auto" in sys.argv
    test_mode = "--test" in sys.argv
    if auto_mode and not test_mode:
        send_prod = True
    if auto_mode and test_mode:
        # 旧用法：自动模式发测试群 → 等同于 push-list
        push_list = True

    print()
    print("  AI 科技热点 → 飞书卡片推送 v3")
    print("  ──────────────────────────────")
    print()

    # 加载配置
    cfg = load_config()

    # ═══════════════════════════════════════════════════════
    # ① 推送新闻列表到测试群
    # ═══════════════════════════════════════════════════════
    if push_list:
        print("  ▸ 步骤 ①：抓取新闻 → 推送列表到测试群")
        print()

        categorized = scrape_categorized_news()
        if not categorized:
            log.error("未抓取到任何新闻，请检查网站是否可访问。")
            return

        # 保存到缓存
        save_cache(categorized)

        # 刷新头图，获取今日的 img_key
        banner_key = refresh_banner(cfg)

        # 构建列表卡片
        card_json = build_list_card(categorized, banner_key=banner_key)

        # 发送到测试群
        token = get_tenant_token(cfg["app_id"], cfg["app_secret"])
        if not token:
            log.error("获取 Token 失败，请检查 config.json")
            return

        test_chat_id = cfg.get("test_chat_id", "")
        if not test_chat_id:
            log.error("config.json 中未配置 test_chat_id")
            return

        if send_card_to_group(test_chat_id, token, card_json):
            print()
            print("  ✅ 新闻列表已推送到测试群！")
            print("  👉 在飞书上浏览今天的热点，然后运行下一步：")
            print("     python3 /Users/zt26278/Q/AI/26AI落地/AI热点/ai_news_sender.py --preview")
            print()
        else:
            log.error("推送到测试群失败")
        return

    # ═══════════════════════════════════════════════════════
    # ② 选择内容 → 推送预览卡片到测试群
    # ═══════════════════════════════════════════════════════
    if preview:
        print("  ▸ 步骤 ②：选择内容 → 推送预览卡片到测试群")
        print()

        # 从缓存加载
        categorized = load_cache()
        if not categorized:
            log.error("没有找到今日新闻缓存。请先运行：python3 /Users/zt26278/Q/AI/26AI落地/AI热点/ai_news_sender.py --push-list")
            return

        log.info("从缓存加载了 %d 条新闻", sum(len(v) for v in categorized.values()))

        # 交互式选择
        selected = interactive_select(categorized)
        if not selected:
            print("\n  未选择任何分类，已取消。")
            return

        # 确认选择
        print("\n  你的选择：")
        for cat, items in selected.items():
            print(f"    {cat}: {len(items)} 条")
            for i, n in enumerate(items, 1):
                print(f"       {i}. {n['title'][:45]}")
        print()

        confirm = input("  确认发送预览到测试群？(y/n) > ").strip().lower()
        if confirm not in ("y", "yes", ""):
            print("  已取消。")
            return

        # 保存选择（供定时任务复用）
        save_selection(selected)

        # 刷新头图，获取今日的 img_key
        banner_key = refresh_banner(cfg)

        # 构建卡片
        card_json = build_card(selected, banner_key=banner_key)
        log.info("卡片构建完成")

        # 发送到测试群
        token = get_tenant_token(cfg["app_id"], cfg["app_secret"])
        if not token:
            log.error("获取 Token 失败，请检查 config.json")
            return

        test_chat_id = cfg.get("test_chat_id", "")
        if send_card_to_group(test_chat_id, token, card_json):
            print()
            print("  ✅ 预览卡片已推送到测试群！去飞书看看效果吧。")
            print("  👉 满意的话，定时任务会在 09:30 自动推送到正式群。")
            print("     也可以手动运行：python3 /Users/zt26278/Q/AI/26AI落地/AI热点/ai_news_sender.py --send-production")
            print()
        else:
            log.error("推送到测试群失败")
        return

    # ═══════════════════════════════════════════════════════
    # ③ 发送到正式群（定时任务 / 手动触发）
    # ═══════════════════════════════════════════════════════
    if send_prod or refresh_flag:
        print("  ▸ 步骤 ③：自动发送到正式群")
        print()

        # 从缓存加载，没有就重新抓取
        categorized = load_cache()
        if not categorized:
            log.info("无缓存，重新抓取新闻...")
            categorized = scrape_categorized_news()
            if not categorized:
                log.error("未抓取到任何新闻，请检查网站是否可访问。")
                return
            save_cache(categorized)

        # 优先使用预览时的选择，没有则自动全选
        saved = load_selection()
        if saved:
            selected = saved
            total = sum(len(v) for v in selected.values())
            log.info("使用预览选择：共 %d 条新闻", total)
        else:
            log.info("未找到预览选择，使用自动模式...")
            visible_cats = {k: v for k, v in categorized.items() if k not in HIDDEN_CATEGORIES}
            selected = {cat: items[:DEFAULT_PER_CATEGORY] for cat, items in visible_cats.items()}
            total = sum(len(v) for v in selected.values())
            log.info("自动模式：选取 %d 个分类，共 %d 条", len(selected), total)

        # 刷新头图，获取今日的 img_key
        banner_key = refresh_banner(cfg)

        # 构建卡片
        card_json = build_card(selected, banner_key=banner_key)
        log.info("卡片构建完成")

        # 发送到正式群
        token = get_tenant_token(cfg["app_id"], cfg["app_secret"])
        if not token:
            log.error("获取 Token 失败，请检查 config.json")
            return

        prod_chat_id = cfg.get("production_chat_id", "")
        if not prod_chat_id:
            log.error("config.json 中未配置 production_chat_id")
            return

        if send_card_to_group(prod_chat_id, token, card_json):
            print()
            print("  ✅ 已推送到正式群！")
            print()
        else:
            log.error("推送到正式群失败")
        return

    # ═══════════════════════════════════════════════════════
    # ④ 发送提醒卡片到测试群（定时任务 8:50 触发）
    # ═══════════════════════════════════════════════════════
    if send_reminder:
        print("  ▸ 发送提醒卡片到测试群")
        print()

        # 同时抓取新闻并缓存（为后续步骤准备）
        categorized = scrape_categorized_news()
        if categorized:
            save_cache(categorized)
            log.info("新闻已抓取并缓存")

        # 构建并发送提醒卡片
        card_json = build_reminder_card()

        token = get_tenant_token(cfg["app_id"], cfg["app_secret"])
        if not token:
            log.error("获取 Token 失败，请检查 config.json")
            return

        test_chat_id = cfg.get("test_chat_id", "")
        if not test_chat_id:
            log.error("config.json 中未配置 test_chat_id")
            return

        if send_card_to_group(test_chat_id, token, card_json):
            print()
            print("  ✅ 提醒卡片已推送到测试群！")
            print()
        else:
            log.error("推送提醒卡片失败")
        return

    # ═══════════════════════════════════════════════════════
    # 没有指定任何模式 → 显示帮助
    # ═══════════════════════════════════════════════════════
    print("  使用方法（三步工作流）：")
    print()
    print("  ① 抓取新闻 + 推送列表到测试群：")
    print("     python3 /Users/zt26278/Q/AI/26AI落地/AI热点/ai_news_sender.py --push-list")
    print()
    print("  ② 选择内容 + 推送预览卡片到测试群：")
    print("     python3 /Users/zt26278/Q/AI/26AI落地/AI热点/ai_news_sender.py --preview")
    print()
    print("  ③ 自动发送到正式群（定时任务用）：")
    print("     python3 /Users/zt26278/Q/AI/26AI落地/AI热点/ai_news_sender.py --send-production")
    print()
    print("  ④ 发送提醒卡片到测试群（定时任务 8:50 用）：")
    print("     python3 /Users/zt26278/Q/AI/26AI落地/AI热点/ai_news_sender.py --send-reminder")
    print()
    print("  其他：")
    print("     python3 /Users/zt26278/Q/AI/26AI落地/AI热点/ai_news_sender.py --refresh-banner   # 单独刷新头图")
    print()


if __name__ == "__main__":
    main()
