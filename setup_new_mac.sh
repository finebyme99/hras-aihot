#!/bin/bash
# =============================================================
#  AI 科技热点 → 飞书推送 一键部署脚本
#  新 Mac 上运行一次即可完成全部配置
#
#  前置条件：
#    1. 已将 AI热点 目录（含 ai_news_sender.py / banner.html / config.json）
#       拷贝到新电脑的某个位置
#    2. 已安装 Google Chrome
#    3. 已安装 Python 3（Homebrew 或官方安装包均可）
# =============================================================

set -e

# ── 颜色 ──
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
fail() { echo -e "${RED}  ❌ $1${NC}"; exit 1; }
info() { echo -e "${CYAN}  ▸ $1${NC}"; }

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   AI 科技热点 → 飞书推送  一键部署           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ─────────────────────────────────────────────
# Step 1: 定位项目目录
# ─────────────────────────────────────────────
echo "━━━ Step 1/6  定位项目目录 ━━━"

# 如果脚本在 AI热点 目录内，直接用
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/ai_news_sender.py" ]]; then
    PROJECT_DIR="$SCRIPT_DIR"
else
    # 否则尝试常见位置
    for candidate in \
        "$HOME/Q/AI/26AI落地/AI热点" \
        "$HOME/Desktop/AI热点" \
        "$HOME/Documents/AI热点"; do
        if [[ -f "$candidate/ai_news_sender.py" ]]; then
            PROJECT_DIR="$candidate"
            break
        fi
    done
fi

if [[ -z "$PROJECT_DIR" ]]; then
    echo ""
    echo "  找不到 AI热点 项目目录。请告诉我项目放在哪里："
    read -r -p "  路径: " PROJECT_DIR
    if [[ ! -f "$PROJECT_DIR/ai_news_sender.py" ]]; then
        fail "该目录下找不到 ai_news_sender.py，请确认路径正确"
    fi
fi

ok "项目目录: $PROJECT_DIR"

# 检查关键文件
[[ -f "$PROJECT_DIR/banner.html" ]]  || fail "缺少 banner.html"
[[ -f "$PROJECT_DIR/config.json" ]]  || fail "缺少 config.json（含飞书密钥）"
ok "关键文件齐全（ai_news_sender.py / banner.html / config.json）"

# ─────────────────────────────────────────────
# Step 2: 检测 Python
# ─────────────────────────────────────────────
echo ""
echo "━━━ Step 2/6  检测 Python 环境 ━━━"

PYTHON_PATH=""
# 按优先级搜索
for p in \
    "$(command -v python3 2>/dev/null)" \
    "$HOME/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3" \
    "/usr/bin/python3"; do
    if [[ -x "$p" ]]; then
        PYTHON_PATH="$p"
        break
    fi
done

if [[ -z "$PYTHON_PATH" ]]; then
    fail "未找到 Python 3，请先安装：brew install python3 或从 python.org 下载"
fi

PY_VER=$("$PYTHON_PATH" --version 2>&1)
ok "Python: $PYTHON_PATH ($PY_VER)"

# pip 路径（和 python 同目录）
PIP_PATH="$(dirname "$PYTHON_PATH")/pip3"
if [[ ! -x "$PIP_PATH" ]]; then
    PIP_PATH="$(command -v pip3 2>/dev/null || true)"
fi

# PATH 环境变量（给 launchd 用）
PYTHON_BIN_DIR="$(dirname "$PYTHON_PATH")"
LAUNCHD_PATH="${PYTHON_BIN_DIR}:/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"

# ─────────────────────────────────────────────
# Step 3: 安装 Python 依赖
# ─────────────────────────────────────────────
echo ""
echo "━━━ Step 3/6  安装 Python 依赖 ━━━"

DEPS="requests beautifulsoup4 html2image"
for dep in $DEPS; do
    if "$PYTHON_PATH" -c "import ${dep/beautifulsoup4/bs4}" 2>/dev/null; then
        ok "$dep 已安装"
    else
        info "安装 $dep ..."
        if [[ -x "$PIP_PATH" ]]; then
            "$PIP_PATH" install "$dep" --quiet
        else
            "$PYTHON_PATH" -m pip install "$dep" --quiet
        fi
        ok "$dep 已安装"
    fi
done

# ─────────────────────────────────────────────
# Step 4: 检测 Chrome 并修补脚本中的硬编码路径
# ─────────────────────────────────────────────
echo ""
echo "━━━ Step 4/6  检测 Chrome & 修补路径 ━━━"

CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [[ -x "$CHROME_PATH" ]]; then
    ok "Chrome: $CHROME_PATH"
else
    warn "未检测到 Google Chrome，头图刷新功能将不可用"
    warn "请安装 Chrome 后重新运行本脚本"
fi

# 当前用户 home 目录
CURRENT_HOME="$HOME"
CURRENT_USER="$(whoami)"

# 定义旧路径模板（脚本中硬编码的）
OLD_PYTHON="/usr/local/bin/python3"
OLD_HOME="/Users/apple"
OLD_PROJECT="/Users/apple/Q/AI/26AI落地/AI热点"

# 修补 ai_news_sender.py 中的硬编码路径
SENDER="$PROJECT_DIR/ai_news_sender.py"
PATCH_COUNT=0

# 替换项目目录路径
if [[ "$PROJECT_DIR" != "$OLD_PROJECT" ]]; then
    sed -i '' "s|$OLD_PROJECT|$PROJECT_DIR|g" "$SENDER"
    PATCH_COUNT=$((PATCH_COUNT + 1))
    info "替换项目路径: $OLD_PROJECT → $PROJECT_DIR"
fi

# 替换 Python 路径（如果不同）
if [[ "$PYTHON_PATH" != "$OLD_PYTHON" ]]; then
    # 脚本内可能没有 shebang 用这个，但保险起见检查一下
    if grep -q "$OLD_PYTHON" "$SENDER"; then
        sed -i '' "s|$OLD_PYTHON|$PYTHON_PATH|g" "$SENDER"
        PATCH_COUNT=$((PATCH_COUNT + 1))
        info "替换 Python 路径: $OLD_PYTHON → $PYTHON_PATH"
    fi
fi

# 替换 home 目录路径
if [[ "$CURRENT_HOME" != "$OLD_HOME" ]] && grep -q "$OLD_HOME" "$SENDER"; then
    sed -i '' "s|$OLD_HOME|$CURRENT_HOME|g" "$SENDER"
    PATCH_COUNT=$((PATCH_COUNT + 1))
    info "替换 HOME 路径: $OLD_HOME → $CURRENT_HOME"
fi

if [[ $PATCH_COUNT -eq 0 ]]; then
    ok "路径与原始配置一致，无需修补"
else
    ok "共修补 $PATCH_COUNT 处路径"
fi

# ─────────────────────────────────────────────
# Step 5: 安装 launchd 定时任务
# ─────────────────────────────────────────────
echo ""
echo "━━━ Step 5/6  注册定时任务 ━━━"

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

# 先卸载旧任务（如果存在）
for label in com.ainews.reminder com.ainews.production; do
    if launchctl list 2>/dev/null | grep -q "$label"; then
        launchctl unload "$LAUNCH_AGENTS_DIR/${label}.plist" 2>/dev/null || true
        info "卸载旧任务: $label"
    fi
done

# 生成 reminder plist
cat > "$LAUNCH_AGENTS_DIR/com.ainews.reminder.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ainews.reminder</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>ai_news_sender.py</string>
        <string>--send-reminder</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${LAUNCHD_PATH}</string>
        <key>HOME</key>
        <string>${CURRENT_HOME}</string>
        <key>LANG</key>
        <string>zh_CN.UTF-8</string>
    </dict>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>50</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/ai_news_reminder.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ai_news_reminder_err.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST
ok "已写入 com.ainews.reminder.plist（每天 08:50 提醒卡片）"

# 生成 production plist
cat > "$LAUNCH_AGENTS_DIR/com.ainews.production.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ainews.production</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>ai_news_sender.py</string>
        <string>--send-production</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${LAUNCHD_PATH}</string>
        <key>HOME</key>
        <string>${CURRENT_HOME}</string>
        <key>LANG</key>
        <string>zh_CN.UTF-8</string>
    </dict>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/ai_news_production.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ai_news_production_err.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST
ok "已写入 com.ainews.production.plist（每天 09:30 正式推送）"

# 加载任务
launchctl load "$LAUNCH_AGENTS_DIR/com.ainews.reminder.plist" 2>/dev/null || true
launchctl load "$LAUNCH_AGENTS_DIR/com.ainews.production.plist" 2>/dev/null || true
ok "两个定时任务已加载到 launchd"

# ─────────────────────────────────────────────
# Step 6: 设置定时唤醒
# ─────────────────────────────────────────────
echo ""
echo "━━━ Step 6/6  设置工作日自动唤醒 ━━━"

# pmset repeat 需要 root 权限，用 osascript 弹窗授权
if pmset -g sched 2>/dev/null | grep -q "wake at 8:45AM"; then
    ok "8:45 定时唤醒已存在，跳过"
else
    info "设置工作日 8:45 自动唤醒（可能需要输入密码）..."
    if osascript -e 'do shell script "pmset repeat wake MTWRF 08:45:00" with administrator privileges' 2>/dev/null; then
        ok "已设置工作日 08:45 自动唤醒"
    else
        warn "自动唤醒设置失败，请手动运行: sudo pmset repeat wake MTWRF 08:45:00"
    fi
fi

# ─────────────────────────────────────────────
# 验证
# ─────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  🔍 验证部署结果"
echo ""

# 检查 launchd 任务
if launchctl list 2>/dev/null | grep -q "com.ainews.reminder"; then
    ok "launchd: com.ainews.reminder 已注册"
else
    fail "launchd: com.ainews.reminder 未注册"
fi

if launchctl list 2>/dev/null | grep -q "com.ainews.production"; then
    ok "launchd: com.ainews.production 已注册"
else
    fail "launchd: com.ainews.production 未注册"
fi

# 检查 pmset
if pmset -g sched 2>/dev/null | grep -q "8:45"; then
    ok "pmset: 工作日 08:45 唤醒"
else
    warn "pmset: 未检测到唤醒计划"
fi

# 试跑一下（仅抓取，不发送）
echo ""
info "试运行脚本（抓取新闻）..."
cd "$PROJECT_DIR"
if "$PYTHON_PATH" ai_news_sender.py --push-list 2>&1 | tail -5; then
    ok "脚本执行成功"
else
    warn "脚本执行有异常，请检查上方输出"
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   部署完成！                                 ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║  📋 每日工作流：                              ║"
echo "║    08:45  Mac 自动唤醒                        ║"
echo "║    08:50  提醒卡片 → 测试群（自动）           ║"
echo "║    你选   --preview 选文章 → 测试群预览       ║"
echo "║    09:30  正式推送 → 正式群（自动）           ║"
echo "║                                              ║"
echo "║  🛠  常用命令：                               ║"
echo "║    python3 ai_news_sender.py --push-list     ║"
echo "║    python3 ai_news_sender.py --preview       ║"
echo "║    python3 ai_news_sender.py --send-production║"
echo "║                                              ║"
echo "║  📁 日志：                                    ║"
echo "║    /tmp/ai_news_reminder.log                 ║"
echo "║    /tmp/ai_news_production.log               ║"
echo "║                                              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
