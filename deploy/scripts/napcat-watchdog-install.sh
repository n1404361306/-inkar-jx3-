#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

chmod +x "$SCRIPT_DIR/napcat-start.sh" "$SCRIPT_DIR/napcat-watchdog.sh"

existing="$(crontab -l 2>/dev/null || true)"
{
  echo "$existing" | grep -v 'napcat-watchdog' || true
  echo "*/3 * * * * $SCRIPT_DIR/napcat-watchdog.sh >/dev/null 2>&1"
} | crontab -

echo "已安装 cron 任务:"
crontab -l | grep napcat-watchdog

bash "$SCRIPT_DIR/napcat-watchdog.sh"
echo "看门狗日志:"
tail -5 /var/log/napcat-watchdog.log 2>/dev/null || echo "(首次运行后生成)"
