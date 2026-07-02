#!/usr/bin/env bash
# NapCat 健康检查与自动重启
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="${NAPCAT_WATCHDOG_CONF:-$SCRIPT_DIR/napcat-watchdog.conf}"
# shellcheck source=/dev/null
[[ -f "$CONF" ]] && source "$CONF"

QQ_BIN="${QQ_BIN:-/opt/QQ/qq}"
QQ_NUM="${QQ_NUM:-1091619707}"
WEBUI_PORT="${WEBUI_PORT:-6099}"
NAPCAT_LOG="${NAPCAT_LOG:-/tmp/napcat_run.log}"
WATCHDOG_LOG="${WATCHDOG_LOG:-/var/log/napcat-watchdog.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/napcat-watchdog.lock}"
STATE_FILE="${STATE_FILE:-/tmp/napcat-watchdog.state}"
COOLDOWN_SEC="${COOLDOWN_SEC:-300}"
OFFLINE_GRACE_MIN="${OFFLINE_GRACE_MIN:-15}"
KICK_GRACE_MIN="${KICK_GRACE_MIN:-3}"
START_SCRIPT="${START_SCRIPT:-$SCRIPT_DIR/napcat-start.sh}"

mkdir -p "$(dirname "$WATCHDOG_LOG")"

log() {
  local msg="[$(date '+%F %T')] $*"
  echo "$msg" >>"$WATCHDOG_LOG"
}

in_cooldown() {
  [[ -f "$STATE_FILE" ]] || return 1
  local last
  last=$(grep -E '^last_restart=' "$STATE_FILE" 2>/dev/null | cut -d= -f2 || true)
  [[ -n "$last" ]] || return 1
  local now elapsed
  now=$(date +%s)
  elapsed=$((now - last))
  (( elapsed < COOLDOWN_SEC ))
}

mark_restart() {
  echo "last_restart=$(date +%s)" >"$STATE_FILE"
}

release_lock() {
  flock -u 9 2>/dev/null || true
  exec 9>&- 2>/dev/null || true
}

napcat_running() {
  pgrep -f "${QQ_BIN}.*--no-sandbox" >/dev/null 2>&1
}

webui_listening() {
  ss -tlnp 2>/dev/null | grep -q ":${WEBUI_PORT} "
}

log_tail() {
  [[ -f "$NAPCAT_LOG" ]] || return 0
  tail -n 400 "$NAPCAT_LOG" 2>/dev/null
}

recent_log_match() {
  local pattern="$1"
  log_tail | grep -E "$pattern" | tail -n 1
}

minutes_since_log_line() {
  local line="$1"
  if [[ -z "$line" ]]; then
    echo 999
    return 0
  fi
  local ts
  ts=$(echo "$line" | sed -n 's/^\([0-9-]\{2\}-[0-9-]\{2\} [0-9:]\{8\}\).*/\1/p')
  if [[ -z "$ts" ]]; then
    echo 999
    return 0
  fi
  local log_epoch now
  log_epoch=$(date -d "${ts}" +%s 2>/dev/null || date -d "$(date +%Y)-${ts}" +%s 2>/dev/null || echo 0)
  now=$(date +%s)
  echo $(( (now - log_epoch) / 60 ))
}

needs_manual_verification() {
  recent_log_match '需要验证码|密码回退需要验证码|登录态已失效|请重新登录' >/dev/null
}

qq_recently_active() {
  local recv_line login_line recv_min login_min
  recv_line=$(log_tail | grep -E '接收 <-' | tail -n 1)
  login_line=$(recent_log_match '登录成功|已登录|自动快速登录成功|密码回退登录成功')
  recv_min=$(minutes_since_log_line "$recv_line")
  login_min=$(minutes_since_log_line "$login_line")
  if [[ -n "$recv_line" && "$recv_min" -le 60 ]]; then
    return 0
  fi
  if [[ -n "$login_line" && "$login_min" -le 60 ]]; then
    return 0
  fi
  return 1
}

should_restart_for_offline() {
  local kick_line offline_line recv_line login_line kick_min offline_min recv_min login_min
  kick_line=$(recent_log_match 'KickedOffLine|登录已失效')
  offline_line=$(recent_log_match '账号状态变更为离线')
  recv_line=$(log_tail | grep -E '接收 <-' | tail -n 1)
  login_line=$(recent_log_match '请扫描下面的二维码|正在快速登录|登录成功|已登录')

  kick_min=$(minutes_since_log_line "$kick_line")
  offline_min=$(minutes_since_log_line "$offline_line")
  recv_min=$(minutes_since_log_line "$recv_line")
  login_min=$(minutes_since_log_line "$login_line")

  # 正在等待扫码/刚发起登录，避免重启打断
  if [[ -n "$login_line" && "$login_min" -le 30 ]]; then
    if recent_log_match '请扫描下面的二维码' >/dev/null; then
      return 1
    fi
  fi

  # 最近被踢下线，且之后长时间无收消息
  if [[ -n "$kick_line" || -n "$offline_line" ]]; then
    local since_offline=$offline_min
  local grace=$OFFLINE_GRACE_MIN
    [[ -n "$kick_line" && "$kick_min" -lt "$since_offline" ]] && since_offline=$kick_min
    # 腾讯强制踢下线（登录失效）用更短等待，避免进程空跑数小时
    if [[ -n "$kick_line" ]]; then
      grace=$KICK_GRACE_MIN
    fi
    if (( since_offline >= grace && recv_min >= grace )); then
      log "检测到离线超过 ${grace} 分钟 (kick=${kick_min}m recv=${recv_min}m)"
      return 0
    fi
  fi
  return 1
}

check_health() {
  local reason=""

  if ! napcat_running; then
    reason="NapCat 进程不存在"
  elif ! webui_listening; then
    reason="WebUI 端口 ${WEBUI_PORT} 未监听"
  elif recent_log_match '无法重复登录' >/dev/null; then
    local dup_line dup_min
    dup_line=$(recent_log_match '无法重复登录')
    dup_min=$(minutes_since_log_line "$dup_line")
    if (( dup_min <= 30 )); then
      reason="登录状态僵死 (无法重复登录)"
    fi
  elif recent_log_match 'Worker进程意外退出 \(3/3\)' >/dev/null; then
    reason="Worker 进程连续崩溃"
  elif needs_manual_verification && ! qq_recently_active; then
    log "QQ 未登录：需人工短信/扫码验证，请打开 WebUI http://127.0.0.1:${WEBUI_PORT}/webui (账号 ${QQ_NUM})"
    exit 0
  elif should_restart_for_offline; then
    reason="QQ 长时间离线"
  fi

  if [[ -n "$reason" ]]; then
    if in_cooldown; then
      log "跳过重启: ${reason} (冷却中 ${COOLDOWN_SEC}s)"
      exit 0
    fi
    log "触发重启: ${reason}"
    mark_restart
    # 必须在拉起 xvfb-run 前释放 flock，否则子进程会继承锁导致后续 cron 全部静默跳过
    release_lock
    bash "$START_SCRIPT" restart >>"$WATCHDOG_LOG" 2>&1 || log "重启命令执行失败"
    exit 0
  fi

  if napcat_running && ! qq_recently_active; then
    log "NapCat 进程在运行，但 QQ 未登录或长时间无消息（请检查 WebUI :${WEBUI_PORT}）"
    exit 0
  fi

  log "健康检查通过"
}

# 防止 cron 重叠执行
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK_FILE"
  flock -n 9 || { log "跳过: 看门狗锁被占用 (可能上次重启未释放)"; exit 0; }
else
  if [[ -f "$LOCK_FILE" ]]; then
    pid=$(cat "$LOCK_FILE" 2>/dev/null || true)
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      exit 0
    fi
  fi
  echo $$ >"$LOCK_FILE"
fi

check_health
