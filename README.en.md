# qodercn-sub

[中文](README.md) | **English**

Delegate execution tasks to Qoder CN in Ghostty while the coordinating agent defines the goal, sets authorization boundaries, supervises the run, and verifies the result.

This repository is a `SKILL.md` skill for a coordinating agent, with a Python orchestration script. Tasks are handed off through local files. Execution details stay in the terminal and report files; the coordinator reads a compact result instead of importing the entire execution log into its conversation. No measured token savings or model performance benchmarks are provided.

## How it works

1. The coordinator writes a task file with the goal, inputs, allowed changes, executable acceptance checks, and authorization boundaries.
2. `prepare` creates a fresh run directory, task identifier, and `worker.md`.
3. `launch` starts `qoderclicn` in Ghostty. Tasks in the same group share a tab, with a layout of four panes per row. A window is created if none exists.
4. Qoder CN executes the task, saves a detailed report, and atomically writes `final.json` when finished.
5. `wait` validates the result protocol and emits a compact summary. For `READY`, it attempts to close the terminal associated with that run.
6. The coordinator reruns 1–2 key acceptance checks before deciding whether the task is complete.

Use it for well-defined mechanical work, batch processing, and moderately scoped implementation tasks. Keep complex diagnosis, architecture, and cross-module design with the coordinator; independent mechanical subtasks can still be delegated. See [SKILL.md](SKILL.md) for the complete workflow.

## Requirements

| Component | Requirement |
| --- | --- |
| OS | macOS; launch and terminal management use `osascript` and Ghostty's AppleScript interface |
| Python | 3.9+; standard library only, no `pip install` needed |
| Ghostty | Installed, with support for the window, tab, split, and terminal-ID interfaces used by the script; grant macOS automation access when prompted |
| Qoder CN | `qoderclicn` available in `PATH`, with a working account and model configuration |
| Coordinating agent | Can load this type of `SKILL.md`; manual script usage is also supported |

Qoder CN, Ghostty, account credentials, and model configuration are not included. Models must support the script's fixed Max reasoning effort and 1,000,000 context setting; otherwise, report the task as blocked.

### Models and trusted directories

The script accepts only two model aliases. These mappings are project conventions, **not model-identity checks performed by the script**:

| `--model` | Intended model | Use |
| --- | --- | --- |
| `gfmodel` | GLM-5.3-Flash | Short mechanical tasks and batch processing |
| `dfmodel` | DeepSeek-Flash | Simple reasoning and well-defined, moderately scoped implementation |

Verify the bindings in your own Qoder CN configuration before first use. Routing is heuristic, not benchmark-based. See [references/defaults.md](references/defaults.md).

The target project must already be trusted in Qoder CN. `launch` checks `permissions.trustDirectories` in `~/.qoder-cn/settings.json` and stops with `BLOCKED` if the target is not trusted. It does not modify your global trust configuration.

## Installation and agent usage

Replace `skill_root` with the skills root directory configured for your coordinating agent, then clone:

```sh
skill_root="/absolute/path/to/your/skills"
git clone https://github.com/xiaoming728/qodercn-sub.git "$skill_root/qodercn-sub"
```

Reload or discover skills according to your agent host, then explicitly request `qodercn-sub`, for example:

> Use qodercn-sub to perform a read-only directory check in /absolute/path/to/project. Do not modify project files or use the network. For acceptance, run pwd -P and require the project's resolved absolute path, then list files in the project root. Produce a detailed report and a compact summary.

`agents/openai.yaml` supplies display metadata, a default prompt, and `allow_implicit_invocation`. Whether implicit invocation is honored depends on the host. This skill is intended to delegate execution work to Qoder CN by default. Read [Permissions and data](#permissions-and-data) before enabling it.

## Manual example

Run these commands from the repository root. Replace the paths with real absolute paths and create the task file first. `run_dir` must not already exist; use a fresh directory for every task.

A task file should contain at least:

```text
Goal: Perform a read-only inspection of /absolute/path/to/project's root directory.
Input: /absolute/path/to/project.
Allowed changes: Result files and reports inside this run directory only;
                 project files remain read-only.
Acceptance: In the project directory, run pwd -P; require exit code 0 and the
            project's resolved absolute path. Run find . -maxdepth 1 -type f;
            require exit code 0 and include the file list in the report.
Authorization: Local, read-only project access. No deletion or overwriting of
               existing files, git push/reset/clean, global configuration changes,
               dependency installation, network publishing, or paid calls.
               Report BLOCKED if additional authorization is needed.
```

An empty list is valid if the project root contains no regular files. Replace the project path and save this example to the file referenced by `task_file`.

```sh
project_dir="/absolute/path/to/project"
task_file="/absolute/path/to/task.md"
run_dir="/absolute/path/to/new-run"

python3 scripts/supervise.py prepare \
  --cwd "$project_dir" --task "$task_file" --run-dir "$run_dir"

python3 scripts/supervise.py launch \
  --run-dir "$run_dir" --model dfmodel --group demo1

python3 scripts/supervise.py wait --run-dir "$run_dir" --timeout 3600
```

Use letters or digits for `--group`, optionally with hyphens. The same group reuses a Ghostty tab. If omitted, the script uses `CLAUDE_CODE_SESSION_ID`, then `CODEX_THREAD_ID`; provide an explicit group if neither is available. Use distinct identifiers for independent task groups.

`wait` checks the local file every 0.2 seconds by default, without model-driven polling. Set a positive `--poll-interval` to change the interval, or use `--pid` to monitor a verified worker process. A timeout stops waiting but does not terminate the worker. For remote control, the user must enter `/remote-control` in the Ghostty terminal and confirm the connection; the script does not do this on the user's behalf.

## Results and exit codes

In each run directory, `manifest.json` records the task identifier and paths, `worker.md` specifies the task and result protocol, and `terminal_id` identifies the associated terminal. The worker's final `final.json` contains:

```json
{
  "task_id": "<task_id generated by prepare>",
  "status": "READY",
  "summary": "Completed the read-only directory check",
  "checks": ["pwd -P → exit 0; output matches the target project path"],
  "refs": {"report": "/absolute/path/to/new-run/report.md"},
  "blocked": [],
  "report_path": "/absolute/path/to/new-run/report.md"
}
```

The worker should write a temporary JSON file in the same directory, then atomically replace `final.json` using `os.replace`. The result file is limited to 16 KiB and the summary to 600 characters. See the script's `validate` function and [worker-policy.md](references/worker-policy.md) for other field limits.

| Task status | Meaning | Associated terminal |
| --- | --- | --- |
| `READY` | Worker reports that acceptance checks passed; coordinator verification is still required | Close attempted; failures produce a warning only |
| `BLOCKED` | Missing authorization, configuration, or another prerequisite; also used for partial completion | Kept open |
| `FAILED` | Task failed | Kept open |

**A `wait` exit code of 0 means that a valid result was read. Its status may still be `BLOCKED` or `FAILED`. Automation must inspect the JSON `status`.** Protocol validation does not run acceptance checks, verify that reports exist, or establish that the worker's conclusions are true.

| `wait` exit code | Meaning |
| --- | --- |
| `0` | Valid result; inspect `status` |
| `2` | Invalid result format, task identifier, or size |
| `3` | The process supplied through `--pid` exited without a final result |
| `4` | Timed out without a final result |

Argument errors and other runtime failures may also produce nonzero exit codes; inspect standard error for details.

## Permissions and data

- Launch arguments always include `--permission-mode bypass_permissions`. **Task-file authorization rules are behavioral instructions, not an operating-system sandbox.** Use this only for projects and tasks you have authorized.
- Run directories, the task file's parent directory, and the skill directory outside the project are supplied through this session's `permissions.additionalDirectories`. The script does not write global configuration.
- Tasks, reports, and summaries are local files. Data transmission through Qoder CN model requests depends on its configuration. This tool does not guarantee offline operation or data isolation. Keep secrets and unrelated private information out of task files and reports.
- Group terminal state is stored in `~/.cache/qodercn-sub/`. Give each run a separate directory. Users manage run files and report retention.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `not in qodercn trustDirectories` | Trust the target directory through Qoder CN, then retry |
| `qoderclicn not found in PATH` | Ensure the coordinating process can locate the command through its `PATH` |
| `need --group` | Pass an explicit value, such as `--group demo1` |
| Ghostty / `osascript` error | Check Ghostty AppleScript interface support and macOS automation permissions |
| `TIMEOUT` / `WORKER_EXITED_WITHOUT_FINAL` | Inspect the terminal, run directory, and report; establish what already ran before retrying |
| `INVALID_RESULT` | Check the task identifier, field types, size, and atomic-write procedure in `final.json` |
| Terminal close warning | The emitted result remains valid; use standard error to inspect the affected terminal |

Closed panes are filtered out, but subsequent pane placement may become uneven. Consider a new task group after repeatedly closing and relaunching panes.

## Files and tests

| File | Purpose |
| --- | --- |
| [SKILL.md](SKILL.md) | Complete coordinating-agent workflow |
| [agents/openai.yaml](agents/openai.yaml) | Host display and invocation metadata |
| [references/defaults.md](references/defaults.md) | Default settings and model routing |
| [references/worker-policy.md](references/worker-policy.md) | Worker authorization boundaries and reporting requirements |
| [scripts/supervise.py](scripts/supervise.py) | `prepare`, `launch`, and `wait` |
| [scripts/test_supervise.py](scripts/test_supervise.py) | Regression tests for launch and wait behavior |

```sh
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
```

Tests mock terminal calls and check result handling. They do not launch real Ghostty or Qoder CN sessions, and passing tests does not verify your model bindings, login, or terminal integration.
