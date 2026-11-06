---
name: qodercn-sub
description: 默认把所有消耗 token 的执行任务与脏活累活委派给 qodercn，主控只保留目标判断、派发、监督与精简最终结果。
---

# Qoder CN 任务委派

## 派发

1. 把本次任务写成简短任务文件，引用现有材料路径而不复制会话；公共执行规则见 [references/worker-policy.md](references/worker-policy.md)。任务文件必须含：
   - 目标与输入位置（绝对路径）；
   - 完成条件：可执行的验收命令与预期结果（如"运行 X，退出码 0，输出含 Y"），不写"确保正确"类不可核验表述；
   - 允许改动的文件/目录范围，及禁止事项（默认禁止：删除或覆盖范围外文件、git push/reset/clean、改全局配置、安装依赖、联网发布）；
   - 用户授权边界；超出范围时写 BLOCKED，不自行扩权。
   大任务拆成多个小任务文件逐个派发。完成条件：任务文件含以上各项，路径可由 qodercn 直接读取。
2. 运行 `scripts/supervise.py prepare --cwd <绝对目录> --task <任务文件> --run-dir <新的绝对运行目录>`。完成条件：取得 `task_id`、`worker.md` 与运行目录。
3. 运行 `scripts/supervise.py launch --run-dir <运行目录> --model <gfmodel|dfmodel>`：启动 qodercn：同一主会话的首个任务在当前 Ghostty 窗口新开标签（无窗口时新建），后续任务在该标签内分屏、每行 4 个（分组默认取主会话 ID，可用 `--group` 指定），已关闭的终端 ID 自动过滤、不参与分屏定位，固定使用 [references/defaults.md](references/defaults.md) 的默认设置，并以初始提示让其读取执行 `worker.md`。模型只能从白名单选择（脚本强制）；不手写启动命令、不复用目录或模型不符的会话。目标目录须已在 qodercn 信任列表（否则 YOLO 不生效、任务卡在确认），脚本检查不通过即报 BLOCKED，提示用户在 qodercn 中信任该目录，不自动改配置。完成条件：脚本输出 `launched: true`。
4. 远程控制按需：如需要，提示用户在该 Ghostty 标签输入 `/remote-control` 并确认连接（主控无法向窗口输入）；本地远程控制与云任务（`--remote`）是不同模式。完成条件：用户确认已连接，或不需要远程控制。
5. 执行日志留在 Ghostty 窗口与本地文件，不进入主控上下文。完成条件：qodercn 已开始执行（窗口可见，或 `wait` 未立即异常）。

## 等待

运行 `scripts/supervise.py wait --run-dir <目录> --timeout 3600`；脚本等待 `final.json` 出现并按协议校验（`task_id`、`status`、`summary`、`checks`、`refs`、`blocked`、`report_path`），通过后输出精简结果。校验结果为 `READY` 时，脚本随后按运行目录的 `terminal_id` 精确关闭对应 Ghostty 终端（分屏/标签/独立窗口均可），不影响同窗口其他终端；`BLOCKED`/`FAILED`/超时/结果非法不关闭；`terminal_id` 缺失或终端已关闭静默跳过；关闭失败只在 stderr 输出警告，已校验结果、stdout 字段与退出码保持不变；重复 `wait` 幂等，已完成关闭的终端不会被再次关闭。结果检查间隔默认 0.2 秒，可用 `--poll-interval <秒>` 调整（须为正数），sleep 全在脚本本地、无模型往返。保持持续执行会话，避免反复 sleep、轮询文件或汇报无变化；可用 `--pid <已核实的 worker PID>` 辅助检测进程退出。完成条件：脚本输出合法结果摘要，或超时、进程退出、格式异常等终止状态；后者先查状态元数据，必要时向 qodercn 索取阻塞摘要，先确认已有工作再决定是否重试。

## 结果

仅读精简摘要：`status`、`summary`、`checks`、`refs`、`blocked`、`report_path`；详细过程与完整报告留在独立文件，仅在失败或证据矛盾时定向读取。`READY` 对应的 Ghostty 终端已由 `wait` 自动关闭，主控无需手工关闭。`READY` 时主控亲自复跑 1–2 条关键 `checks` 中的验收命令，不一致即按失败处理；按完成条件与验证证据判断结果：进程存活、退出码 0、阶段性响应与文件出现都不能单独证明完成。不重复 qodercn 已完成且有证据的工作，最终只简短报告成果与真实阻塞。
