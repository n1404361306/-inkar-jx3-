#!/usr/bin/env bash
# NapCat 统一启动脚本
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="${NAPCAT_WATCHDOG_CONF:-$SCRIPT_DIR/napcat-watchdog.conf}"
# shellcheck source=/dev/null
[[ -f "$CONF" ]] && source "$CONF"

QQ_BIN="${QQ_BIN:-/opt/QQ/qq}"
QQ_NUM="${QQ_NUM:-1091619707}"
NAPCAT_LOG="${NAPCAT_LOG:-/tmp/napcat_run.log}"
QUICK_LOGIN="${QUICK_LOGIN:-1}"
AUTO_LOGIN="${AUTO_LOGIN:-1}"
NAPCAT_ENV="${NAPCAT_ENV:-$SCRIPT_DIR/napcat.env}"
STARTUP_WAIT_SEC="${STARTUP_WAIT_SEC:-30}"
WEBUI_PORT="${WEBUI_PORT:-6099}"

log() {
  echo "[$(date '+%F %T')] $*"
}

load_login_env() {
  if [[ "$AUTO_LOGIN" == "1" && -f "$NAPCAT_ENV" ]]; then
    # shellcheck source=/dev/null
    source "$NAPCAT_ENV"
    export NAPCAT_QUICK_ACCOUNT="${NAPCAT_QUICK_ACCOUNT:-$QQ_NUM}"
  fi
}

stop_napcat() {
  log "停止 NapCat 进程..."
  pkill -f "${QQ_BIN}.*--no-sandbox" 2>/dev/null || true
  pkill -f "xvfb-run.*${QQ_BIN}" 2>/dev/null || true
  sleep 3
  pkill -9 -f "${QQ_BIN}.*--no-sandbox" 2>/dev/null || true
}

start_napcat() {
  local use_quick="${1:-0}"
  local args=(--no-sandbox)
  if [[ "$use_quick" == "1" && -n "$QQ_NUM" ]]; then
    args+=(-q "$QQ_NUM")
  fi

  load_login_env

  log "启动 NapCat (quick_login=${use_quick}, auto_login=${AUTO_LOGIN})..."
  nohup env \
    NAPCAT_QUICK_ACCOUNT="${NAPCAT_QUICK_ACCOUNT:-}" \
    NAPCAT_QUICK_PASSWORD="${NAPCAT_QUICK_PASSWORD:-}" \
  setsid xvfb-run -a "$QQ_BIN" "${args[@]}" >>"$NAPCAT_LOG" 2>&1 < /dev/null &
  local pid=$!
  log "NapCat 已拉起, pid=${pid}"

  local waited=0
  while (( waited < STARTUP_WAIT_SEC )); do
    if ss -tlnp 2>/dev/null | grep -q ":${WEBUI_PORT} "; then
      log "WebUI 端口 ${WEBUI_PORT} 已就绪"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done

  log "警告: ${STARTUP_WAIT_SEC}s 内 WebUI 未就绪，请检查 ${NAPCAT_LOG}"
  return 1
}

wait_for_login() {
  local timeout="${1:-90}"
  local waited=0
  local log_mark
  log_mark=$(wc -l <"$NAPCAT_LOG" 2>/dev/null || echo 0)
  while (( waited < timeout )); do
    if tail -n +"$((log_mark + 1))" "$NAPCAT_LOG" 2>/dev/null | grep -qE '发送 ->|自动快速登录成功|自动密码回退登录成功|密码回退登录成功'; then
      log "检测到 QQ 已登录"
      return 0
    fi
    if tail -n +"$((log_mark + 1))" "$NAPCAT_LOG" 2>/dev/null | grep -qE '需要验证码|新设备需要扫码验证|异常设备需要验证|密码回退需要验证码'; then
      log "自动登录需要人工验证（验证码/新设备），请打开 WebUI 完成"
      return 1
    fi
    sleep 3
    waited=$((waited + 3))
  done
  log "等待自动登录超时，请检查 WebUI 或日志"
  return 1
}

main() {
  local mode="${1:-restart}"
  case "$mode" in
    start)
      start_napcat "$QUICK_LOGIN"
      ;;
    stop)
      stop_napcat
      ;;
    restart|restart-quick)
      stop_napcat
      if [[ "$AUTO_LOGIN" == "1" ]]; then
        start_napcat 1 || true
        wait_for_login 90 || true
      else
        start_napcat 0 || true
        [[ "$QUICK_LOGIN" == "1" ]] && start_napcat 1 || true
      fi
      ;;
    *)
      echo "用法: $0 {start|stop|restart|restart-quick}"
      exit 1
      ;;
  esac
}

main "$@"
