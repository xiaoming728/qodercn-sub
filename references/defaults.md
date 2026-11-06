# 执行默认与模型路由（单一配置源）

qodercn 会话执行设置：除模型外全部默认（用户指定）；模型只从下列白名单按任务选择。

## 默认设置

- 思考强度：Max（`--reasoning-effort max`）
- 上下文：1000000（`--context-window 1000000`）
- 权限：`bypass_permissions`（YOLO）
- 远程控制：按需——由用户在 Ghostty 窗口输入 `/remote-control` 并确认连接；本地远程控制与云任务（`--remote`）是不同模式

## 模型白名单（仅此两种，其他模型不得自动使用）

编码对应表（2026-10-09）：

| 模型 | 自定义编码（`--model`） | 核实状态 |
|---|---|---|
| GLM-5.3-Flash | `gfmodel` | 约定映射；本机别名到具体版本的绑定尚未核实 |
| DeepSeek-Flash | `dfmodel` | 本机 settings.json 当前 model.name 为 dfmodel；此前会话已确认显示 DeepSeek-Flash |

首次使用 `gfmodel` / `dfmodel` 前核对本机实际绑定；仅允许分别绑定到白名单中的两个模型。匹配后使用编码，不匹配或无法核实时报告阻塞，不猜测目标版本、不自动改模型配置。

启动参数（由 `supervise.py launch` 固定生成，Ghostty 同组同标签、每行 4 个分屏）：`qoderclicn --model <编码> --reasoning-effort max --context-window 1000000 --permission-mode bypass_permissions`；分别将 `<编码>` 替换为 `gfmodel`、`dfmodel`。完整模型名称只作识别标签；自定义模型传编码。

目录外的任务、运行文件与公共约束通过本次启动的 `--settings` 中 `permissions.additionalDirectories` 授权；不写全局配置。Qoder v1.1.83 的 `--add-dir` 即使添加受信任目录也会弹确认，启动脚本因此使用会话级设置。

## 路由（启发式，非实测性能结论）

- 短机械、批处理 → `gfmodel`
- 简单但需推理、目标清楚的中等实现 → `dfmodel`
- 复杂诊断、架构、并发、跨模块设计 → 不委派，由主控自行完成；仅可把其中机械子任务拆出委派
- 两者都是 Flash 级模型：结果须由主控复跑验收命令，不以 Flash 自评为准
- 最终只报告所选模型与简短原因

## 会话与回退

- 所选模型不支持 Max 或 1000000 上下文：明确阻塞，不静默改用其他设置。
- 不安装、不改动套餐与付费配置。
