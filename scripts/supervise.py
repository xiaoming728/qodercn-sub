#!/usr/bin/env python3
"""Prepare a worker handoff; wait locally and emit bounded final metadata only."""
import argparse
import fcntl
import json
import math
import os
import shlex
import shutil
import sys
from pathlib import Path
import subprocess
import time
import uuid


def emit(value):
    print(json.dumps(value, ensure_ascii=False, separators=(',', ':')), flush=True)


def prepare(args):
    cwd = Path(args.cwd).resolve(strict=True)
    task = Path(args.task).resolve(strict=True)
    run = Path(args.run_dir).resolve()
    run.mkdir(parents=True, exist_ok=False)
    task_id = str(uuid.uuid4())
    policy = Path(__file__).resolve().parents[1] / 'references/worker-policy.md'
    (run / 'manifest.json').write_text(json.dumps({'task_id': task_id, 'cwd': str(cwd), 'task': str(task)}, ensure_ascii=False))
    contract = {'task_id': task_id, 'status': 'READY|BLOCKED|FAILED', 'summary': '',
                'checks': [], 'refs': {}, 'blocked': [], 'report_path': ''}
    (run / 'worker.md').write_text(
        f'目标目录：{cwd}\n公共约束：{policy}\n本次任务：{task}\n'
        f'完整读取这两份文件并按授权执行。最终 JSON 协议：\n{json.dumps(contract, ensure_ascii=False)}\n'
        f'全部前台执行完或明确阻塞/失败后，将真实结果先写 {run / "final.json.tmp"}，'
        f'再使用 os.replace 原子替换为 {run / "final.json"}。'
        '完整报告写独立文件，JSON只含摘要与路径；不能在中途创建final.json。\n')
    emit({'task_id': task_id, 'worker_path': str(run / 'worker.md'), 'run_dir': str(run)})


MODELS = ('gfmodel', 'dfmodel')  # 白名单见 references/defaults.md
COLS = 4  # 同组任务在同一标签内分屏，每行 4 个
STATE = Path.home() / '.cache/qodercn-sub'

# argv: cwd, command, mode(tab|right|down), parent terminal id, PATH；参数经 argv 传入，不拼进 AppleScript
PLACE = """on run argv
  set {wd, cmdline, mode, parentId, envPath} to argv
  tell application "Ghostty"
    set cfg to new surface configuration
    set initial working directory of cfg to wd
    set command of cfg to cmdline
    set environment variables of cfg to {"PATH=" & envPath, "QODERCN_EXPOSE_TOKEN_USAGE=1"}
    if mode is "tab" then
      if (count of windows) is 0 then
        set w to new window with configuration cfg
        return id of focused terminal of selected tab of w
      end if
      return id of focused terminal of (new tab in front window with configuration cfg)
    end if
    if mode is "right" then
      set t to split (terminal id parentId) direction right with configuration cfg
    else
      set t to split (terminal id parentId) direction down with configuration cfg
    end if
    perform action "equalize_splits" on t
    return id of t
  end tell
end run"""

ALIVE = """on run argv
  set out to {}
  tell application "Ghostty"
    repeat with i in argv
      if exists terminal id (contents of i) then set end of out to (contents of i)
    end repeat
  end tell
  set AppleScript's text item delimiters to linefeed
  return out as text
end run"""

CLOSE = """on run argv
  tell application "Ghostty"
    close (terminal id (item 1 of argv))
  end tell
end run"""


def osa(script, *argv):
    return subprocess.run(['osascript', '-e', script, *argv], check=True,
                          capture_output=True, text=True).stdout.strip()


def close_terminal(run):
    path = run / 'terminal_id'
    tid = path.read_text().strip() if path.is_file() else ''
    if not tid:
        return
    try:
        if tid not in osa(ALIVE, tid).splitlines():
            return
        osa(CLOSE, tid)
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = (getattr(exc, 'stderr', '') or '').strip() or str(exc)
        print(f'qodercn-sub: failed to close terminal {tid}: {detail}', file=sys.stderr)


def launch(args):
    run = Path(args.run_dir).resolve(strict=True)
    manifest = json.loads((run / 'manifest.json').read_text())
    cwd = manifest['cwd']
    worker = run / 'worker.md'
    if not worker.is_file():
        raise SystemExit('worker.md missing; run prepare first')
    # qodercn 只在受信任目录生效 bypass_permissions，否则逐条弹确认、任务静默卡住
    conf = Path.home() / '.qoder-cn/settings.json'
    trusted = json.loads(conf.read_text()).get('permissions', {}).get('trustDirectories', []) if conf.exists() else []
    if not any(Path(cwd).is_relative_to(Path(t).resolve()) for t in trusted):
        raise SystemExit(f'BLOCKED: {cwd} not in qodercn trustDirectories; trust it in qodercn first')
    # 目录外材料通过本次启动设置授权；--add-dir 在 Qoder v1.1.83 会额外弹信任确认
    extra = {str(run), str(Path(manifest['task']).parent), str(Path(__file__).resolve().parents[1])} - {cwd}
    group = args.group or os.environ.get('CLAUDE_CODE_SESSION_ID') or os.environ.get('CODEX_THREAD_ID')
    if not group or not group.replace('-', '').isalnum():
        raise SystemExit('need --group <alnum id> (no session id in env)')
    state = STATE / f'{group}.json'
    STATE.mkdir(parents=True, exist_ok=True)
    # 并行派发时串行化 读状态→分屏→写状态，否则都读到空状态各开一个标签
    lock = open(STATE / f'{group}.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX)
    ids = json.loads(state.read_text()) if state.exists() else []
    live = osa(ALIVE, *ids).splitlines() if ids else []
    n = len(live)
    # shortcut: 已关闭的分屏会让后续位置错位，同组若频繁关闭再派发再考虑记录行列坐标
    mode, parent = ('tab', '') if n == 0 else ('right', live[-1]) if n < COLS else ('down', live[n - COLS])
    # Ghostty 以 login shell 启动，不含用户 PATH：用绝对路径并透传 PATH
    exe = shutil.which('qoderclicn')
    if not exe:
        raise SystemExit('qoderclicn not found in PATH')
    cmd = shlex.join([exe, '--model', args.model, '--reasoning-effort', 'max',
                      '--context-window', '1000000', '--permission-mode', 'bypass_permissions',
                      '-w', cwd, '--settings', json.dumps({'permissions': {'additionalDirectories': sorted(extra)}}),
                      '-i', f'完整读取并执行 {worker}'])
    out = osa(PLACE, cwd, cmd, mode, parent, os.environ.get('PATH', ''))
    (run / 'terminal_id').write_text(out)
    state.write_text(json.dumps(live + [out]))
    lock.close()
    emit({'launched': True, 'terminal_id': out, 'placement': mode, 'slot': n, 'model': args.model, 'cwd': cwd, 'worker_path': str(worker)})


def validate(data, task_id):
    if not isinstance(data, dict) or data.get('task_id') != task_id:
        raise ValueError('task_id mismatch')
    if data.get('status') not in {'READY', 'BLOCKED', 'FAILED'}:
        raise ValueError('invalid status')
    if not isinstance(data.get('summary'), str) or len(data['summary']) > 600:
        raise ValueError('invalid summary')
    for field in ('checks', 'blocked'):
        items = data.get(field)
        if not isinstance(items, list) or len(items) > 12 or any(not isinstance(x, str) or len(x) > 240 for x in items):
            raise ValueError(f'invalid {field}')
    refs = data.get('refs')
    if not isinstance(refs, dict) or len(refs) > 12 or any(not isinstance(k, str) or not isinstance(v, str) or len(k) > 80 or len(v) > 240 for k, v in refs.items()):
        raise ValueError('invalid refs')
    report = data.get('report_path')
    if not isinstance(report, str) or (report and not Path(report).is_absolute()):
        raise ValueError('report_path must be absolute')
    return {k: data[k] for k in ('task_id', 'status', 'summary', 'checks', 'refs', 'blocked', 'report_path')}


def wait(args):
    run = Path(args.run_dir).resolve(strict=True)
    manifest = json.loads((run / 'manifest.json').read_text())
    deadline = time.monotonic() + args.timeout
    while True:
        final = run / 'final.json'
        if final.exists():
            try:
                if final.stat().st_size > 16384:
                    raise ValueError('final exceeds 16KB')
                data = validate(json.loads(final.read_text()), manifest['task_id'])
            except (ValueError, OSError) as exc:
                emit({'monitor_status': 'INVALID_RESULT', 'reason': str(exc)[:200]})
                return 2
            emit(data)
            if data['status'] == 'READY':
                close_terminal(run)
            return 0
        if args.pid:
            try:
                os.kill(args.pid, 0)
            except ProcessLookupError:
                emit({'monitor_status': 'WORKER_EXITED_WITHOUT_FINAL'})
                return 3
            except PermissionError:
                pass
        if time.monotonic() >= deadline:
            emit({'monitor_status': 'TIMEOUT', 'task_id': manifest['task_id']})
            return 4
        time.sleep(min(args.poll_interval, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--cwd', required=True)
    p.add_argument('--task', required=True)
    p.add_argument('--run-dir', required=True)
    l = sub.add_parser('launch')
    l.add_argument('--run-dir', required=True)
    l.add_argument('--model', required=True, choices=MODELS)
    l.add_argument('--group', help='同组任务共用一个标签；默认取主会话 ID')
    w = sub.add_parser('wait')
    w.add_argument('--run-dir', required=True)
    w.add_argument('--timeout', type=float, default=3600)
    w.add_argument('--pid', type=int)
    w.add_argument('--poll-interval', type=float, default=0.2,
                   help='seconds between result checks (default 0.2)')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args)
        return 0
    if args.command == 'launch':
        launch(args)
        return 0
    if args.timeout < 0 or (args.pid is not None and args.pid <= 0):
        parser.error('timeout must be nonnegative and PID positive')
    if not math.isfinite(args.poll_interval) or args.poll_interval <= 0:
        parser.error('poll interval must be a positive finite number')
    return wait(args)


if __name__ == '__main__':
    raise SystemExit(main())
