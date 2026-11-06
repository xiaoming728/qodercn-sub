# qodercn-sub

**中文** | [English](README.en.md)

把执行任务交给 Qoder CN，在 Ghostty 中运行，由主控 agent 负责确定目标、授权范围、监督和最终验收。

这是供主控 agent 加载的 `SKILL.md` skill，附带 Python 调度脚本。任务通过本地文件交接，执行过程留在终端和报告文件中；主控读取精简的结果摘要，避免把完整执行日志带回主会话。项目未提供 token 节省或模型性能的实测数据。

## 工作方式

1. 主控编写任务文件：目标、输入、允许改动范围、可执行验收命令和授权边界。
2. `prepare` 创建独立运行目录、任务标识和 `worker.md`。
3. `launch` 在 Ghostty 中启动 `qoderclicn`。同组任务放在同一标签内，按每行 4 个分屏布局；没有 Ghostty 窗口时会新建窗口。
4. Qoder CN 执行任务，保存完整报告，最后原子写入 `final.json`。
5. `wait` 校验结果协议并输出摘要；结果为 `READY` 时，尝试关闭该任务对应的终端。
6. 主控亲自复跑 1–2 条关键验收命令，再判断是否完成。

适合目标明确的机械处理、批处理和中等实现任务。复杂诊断、架构和跨模块设计由主控处理，可把其中独立的机械子任务交给 Qoder CN。完整规则见 [SKILL.md](SKILL.md)。

## 环境要求

| 项目 | 要求 |
| --- | --- |
| 系统 | macOS；启动和终端管理使用 `osascript` 与 Ghostty AppleScript 接口 |
| Python | 3.9+；仅使用标准库，无需 `pip install` |
| Ghostty | 安装并支持脚本所用的新建窗口、标签、分屏及终端 ID 接口；按系统提示授权自动化控制 |
| Qoder CN | `qoderclicn` 在 `PATH` 中可用，且已配置可用的账号与模型 |
| 主控 agent | 支持加载此类 `SKILL.md`；也可手动调用脚本 |

本仓库不包含 Qoder CN、Ghostty、账号凭据或模型配置。模型必须支持脚本固定使用的 Max 思考强度和 1,000,000 上下文设置，否则应报告阻塞。

### 模型与信任目录

脚本只接受两个模型别名，以下名称是项目约定，**不是脚本对实际模型身份的验证**：

| `--model` | 约定模型 | 用途 |
| --- | --- | --- |
| `gfmodel` | GLM-5.3-Flash | 短机械任务、批处理 |
| `dfmodel` | DeepSeek-Flash | 简单推理、目标明确的中等实现 |

首次使用前，在自己的 Qoder CN 配置中核实别名绑定。路由规则是启发式，非性能基准；详见 [references/defaults.md](references/defaults.md)。

目标项目须已通过 Qoder CN 加入信任目录。`launch` 会检查 `~/.qoder-cn/settings.json` 中的 `permissions.trustDirectories`，未受信任则输出 `BLOCKED` 并停止；脚本不会代你修改全局信任配置。

## 安装与 agent 使用

将下面的 `skill_root` 换成主控 agent 实际配置的 skills 根目录，再克隆：

```sh
skill_root="/absolute/path/to/your/skills"
git clone https://github.com/xiaoming728/qodercn-sub.git "$skill_root/qodercn-sub"
```

按宿主 agent 的方式重新加载或发现 skill，并明确请求使用 `qodercn-sub`，例如：

> 使用 qodercn-sub，在 /absolute/path/to/project 执行一个只读目录检查。不得修改项目文件或联网；验收时运行 pwd -P，结果须为目标项目的真实绝对路径，并列出项目根目录的文件。输出完整报告和精简摘要。

`agents/openai.yaml` 提供显示名称、默认提示词，并启用 `allow_implicit_invocation`；宿主是否采纳隐式调用取决于其支持情况。此 skill 的默认意图是把执行工作交给 Qoder CN，启用前请阅读 [权限与数据](#权限与数据)。

## 手动运行示例

以下命令从仓库根目录执行。先将路径替换为实际的绝对路径，并创建任务文件；`run_dir` 必须尚不存在，每次任务使用新目录。

任务文件至少应包含这些内容：

```text
目标：只读检查 /absolute/path/to/project 的根目录。
输入：/absolute/path/to/project。
允许改动：仅本次运行目录内的结果文件与报告；项目文件保持只读。
验收：在项目目录运行 pwd -P，退出码为 0，输出为该项目的真实绝对路径；
      运行 find . -maxdepth 1 -type f，退出码为 0，并把文件列表写入报告。
授权：只读本地项目；禁止删除或覆盖已有文件、git push/reset/clean、
      修改全局配置、安装依赖、联网发布与付费调用。超出授权时报告 BLOCKED。
```

该示例允许根目录没有普通文件，此时列表为空。将示例中的项目路径替换后保存为 `task_file` 指向的文件。

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

`--group` 使用字母或数字，可含连字符。同一组复用一个 Ghostty 标签；省略时先取 `CLAUDE_CODE_SESSION_ID`，再取 `CODEX_THREAD_ID`，两者均无时须手动指定。独立任务组使用不同标识。

`wait` 默认在本地每 0.2 秒检查一次文件，不通过模型轮询。可用 `--poll-interval` 调整正数间隔，或用 `--pid` 监测已核实的 worker 进程。超时只结束等待，不终止 worker。需要远程控制时，由用户在该 Ghostty 终端输入 `/remote-control` 并确认连接；脚本不会代为确认。

## 结果与退出码

运行目录中的 `manifest.json` 记录任务标识和路径，`worker.md` 指定任务与结果协议，`terminal_id` 用于定位对应终端。Worker 最终写入的 `final.json` 包含：

```json
{
  "task_id": "<prepare 生成的 task_id>",
  "status": "READY",
  "summary": "已完成只读目录检查",
  "checks": ["pwd -P → 退出码 0，输出与目标项目路径一致"],
  "refs": {"report": "/absolute/path/to/new-run/report.md"},
  "blocked": [],
  "report_path": "/absolute/path/to/new-run/report.md"
}
```

Worker 应先写同目录临时 JSON，再用 `os.replace` 原子替换为 `final.json`。结果文件最大 16 KiB，摘要最长 600 字符；其他字段限制见脚本的 `validate` 函数和 [worker-policy.md](references/worker-policy.md)。

| 任务状态 | 含义 | 对应终端 |
| --- | --- | --- |
| `READY` | Worker 报告验收已通过，仍须主控复核 | 尝试关闭；关闭失败仅警告 |
| `BLOCKED` | 缺少授权、配置或其他必要条件，或仅部分完成 | 保留 |
| `FAILED` | 任务失败 | 保留 |

**`wait` 退出码为 0 只表示读到了合法结果，可能仍是 `BLOCKED` 或 `FAILED`。自动化调用必须检查 JSON 的 `status`。** 协议校验不会执行验收命令，也不会核实报告是否存在或结论是否属实。

| `wait` 退出码 | 含义 |
| --- | --- |
| `0` | 合法结果；继续检查 `status` |
| `2` | 结果格式、任务标识或大小无效 |
| `3` | `--pid` 指定的进程已退出，且没有最终结果 |
| `4` | 等待超时，尚无最终结果 |

参数错误和其他运行异常也可能产生非零退出码，应结合标准错误判断。

## 权限与数据

- 启动参数固定包含 `--permission-mode bypass_permissions`。**任务文件中的授权约束是行为规则，不是操作系统沙箱**；请仅对已授权的项目和任务使用。
- 项目之外的运行目录、任务文件父目录和 skill 目录通过本次会话的 `permissions.additionalDirectories` 提供给 Qoder CN；脚本不写入全局配置。
- 任务、报告和摘要是本地文件；Qoder CN 的模型请求是否传输数据取决于其配置。本工具不提供离线运行或数据隔离保证，任务文件和报告应避免包含密钥及无关私人信息。
- 分组终端状态保存在 `~/.cache/qodercn-sub/`。不要让不同工作共用同一运行目录；运行文件和报告由使用者管理。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| `not in qodercn trustDirectories` | 在 Qoder CN 中信任目标目录后重试 |
| `qoderclicn not found in PATH` | 确认当前主控进程的 `PATH` 能找到该命令 |
| `need --group` | 显式传入如 `--group demo1` |
| Ghostty/`osascript` 报错 | 检查 Ghostty 的 AppleScript 接口支持和 macOS 自动化授权 |
| `TIMEOUT` / `WORKER_EXITED_WITHOUT_FINAL` | 查看对应终端、运行目录和报告，确认已有工作后再决定是否重试 |
| `INVALID_RESULT` | 检查 `final.json` 的任务标识、字段类型、大小和原子写入方式 |
| 关闭终端失败 | 结果摘要仍有效；根据标准错误提示检查对应终端 |

已关闭的分屏会被过滤，但后续分屏位置可能不再整齐；大量关闭后重新派发时，可换用新的任务组。

## 文件与测试

| 文件 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | 主控 agent 的完整执行流程 |
| [agents/openai.yaml](agents/openai.yaml) | 宿主显示与调用元数据 |
| [references/defaults.md](references/defaults.md) | 默认参数与模型路由 |
| [references/worker-policy.md](references/worker-policy.md) | Worker 授权边界与回传要求 |
| [scripts/supervise.py](scripts/supervise.py) | `prepare`、`launch`、`wait` |
| [scripts/test_supervise.py](scripts/test_supervise.py) | 启动与等待逻辑的回归测试 |

```sh
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
```

测试使用 mock 验证终端调用和结果处理，不会真实启动 Ghostty 或 Qoder CN；通过测试不代表本机模型、登录和终端集成已验证。
