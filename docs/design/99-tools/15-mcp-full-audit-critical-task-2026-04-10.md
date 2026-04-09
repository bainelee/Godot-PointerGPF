# MCP 全面审查关键任务文档（2026-04-10）

## 文档目的

本文件用于固化一次“旧项目同步 / 当前仓库实现 / release 生效面”三方一致性审查结果，并作为后续修复执行与信息补充的唯一任务底稿。

审查范围对应：

1. 旧项目来源：`D:/GODOT_Test/old-archives-sp`（基线提交 `522744d`）
2. 当前仓库：`D:/AI/pointer_gpf`
3. release 生效面：`mcp/version_manifest.json` 指向的 stable 包

---

## 最高优先级审查结论

- 当前仓库代码与本地测试结果总体可运行，但 **release 包与仓库能力严重不一致**。
- 存在可阻断发布的 `P0` 问题：用户通过标准安装/更新路径拿到的能力显著少于仓库声明能力。
- 审计脚本与文档产物存在口径偏差，容易误导后续决策。
- 发布治理新增硬约束：**所有 PointerGPF 相关文件必须统一位于单一根目录（建议 `pointer_gpf/`）下，不得散落到项目根目录与其他路径，确保用户工作区整洁**。

---

## 问题清单（按严重级别）

## P0

### 0) 发布结构不满足“单目录整合”硬约束

- 标题：gpf 相关文件未完全收敛到单一目录
- 严重级别：P0
- 证据：
  - 当前发布与仓库结构同时存在根级与分散路径：`mcp/`、`install/`、`godot_plugin_template/`、`docs/`、`examples/`、`gtr.config.json`。
  - 需求要求“所有 gpf 相关文件全部整合在一个文件夹下”。
- 影响范围：
  - 用户工作区出现多目录扩散，安装后可见面不整洁，且后续更新/回滚与清理成本增加。
- 修复建议：
  - 统一发布根为 `pointer_gpf/`，所有运行、脚本、模板、文档、legacy 资产全部置于该目录下。
  - `pointer-gpf.cmd` 与安装脚本只作为薄入口，最终定位到 `pointer_gpf/` 内部实现。
  - 更新 `version_manifest`、workflow、文档与测试断言，保证路径口径一致。
- 是否阻断 release：是

### 1) stable 发布包工具面严重缩水，核心工具不可用

- 标题：stable 包工具面与仓库能力不一致
- 严重级别：P0
- 证据：
  - 仓库运行时工具清单（38 项）：
    - `python mcp/server.py --tool get_mcp_runtime_info --args "{}"`
  - 发布包运行时工具清单（14 项）：
    - 从 `mcp/version_manifest.json` 的 `channels.stable.artifact.url` 下载 zip 后执行同命令
  - 发布包缺失关键工具：
    - `run_game_flow` / `start_stepwise_flow` / `pull_cursor_chat_plugin` / `run_game_basic_test_flow`
  - 发布包直接调用示例：
    - `UNSUPPORTED_TOOL: run_game_flow`
- 影响范围：
  - 标准安装与更新链路用户无法使用文档与 CI 中声明的关键能力
- 修复建议：
  - 立即发布新版本并回填 manifest
  - 发布前新增“解包后工具清单断言 + 关键工具调用冒烟”
- 是否阻断 release：是

### 2) release 打包清单缺失 legacy 运行依赖

- 标题：发布包未包含 legacy 执行链核心目录
- 严重级别：P0
- 证据：
  - `.github/workflows/release-package.yml` 未打包：
    - `tools/game-test-runner/**`
    - `flows/**`
    - `addons/test_orchestrator/**`
  - 按当前 workflow 逻辑模拟打包后，关键路径不存在：
    - `tools/game-test-runner/mcp/server.py`
    - `flows/internal/contract_force_fail_invalid_scene.json`
- 影响范围：
  - legacy bridge 在 release 环境中无法完整执行
- 修复建议：
  - 扩展 release 打包清单，至少纳入 `tools/game-test-runner/**` + `flows/**`
  - 增加解包后 `run_game_flow` dry-run 验证步骤
- 是否阻断 release：是

## P1

### 3) 旧工具面兼容不完整：缺 `check_test_runner_environment`

- 标题：基线工具面存在 1 项未映射到根 MCP
- 严重级别：P1
- 证据：
  - 根 MCP 调用失败：
    - `python mcp/server.py --tool check_test_runner_environment --args "{}"`
  - legacy 子服务器调用成功：
    - `python tools/game-test-runner/mcp/server.py --tool check_test_runner_environment --args "{}"`
- 影响范围：
  - 旧调用方迁移到根 MCP 时存在功能断点
- 修复建议：
  - 将该工具纳入根 MCP legacy bridge 清单，或明确废弃并发布迁移公告
- 是否阻断 release：否（若明确不承诺此工具）；是（若承诺全量兼容）

### 4) gap 审计脚本统计口径偏差

- 标题：`mcp_gap_audit.py` 将动态桥接工具误判为缺失
- 严重级别：P1
- 证据：
  - `scripts/mcp_gap_audit.py` 对新工具面提取只匹配 `_tool_` 静态映射
  - 根 MCP 实际通过 `_build_legacy_bridge_tool_map()` 动态注入 legacy 工具
  - `docs/mcp-gap-analysis-2026-04-10.json/.md` 与实时 `get_mcp_runtime_info` 结果不一致
- 影响范围：
  - 差异报告失真，影响修复优先级判断
- 修复建议：
  - 审计改为“运行时工具清单 + 静态路径清单”双通道对比
- 是否阻断 release：否

## P2

### 5) 通用性约束仍有具体游戏语义泄漏

- 标题：legacy 语义在 flow 与模板中暴露较多
- 严重级别：P2
- 证据：
  - `flows/suites/regression/gameplay/**` 中大量 `slot0` / `roomId` / `new_game` 等
  - `tools/game-test-runner/mcp/chat_progress_templates.json` 中存在固定业务语义步骤名
  - `godot_plugin_template/addons/pointer_gpf/plugin.cfg` 描述包含 `GameplayFlow`
- 影响范围：
  - 新项目接入时对“全类型 Godot”目标产生理解偏差
- 修复建议：
  - 将默认通用资产与 legacy fixture 显式分层并标注用途
- 是否阻断 release：否

---

## 功能对照表（旧项目 / 当前实现 / release 生效 / 结论）

| 功能项 | 旧项目（522744d） | 当前实现（仓库） | release 生效（stable） | 结论 |
| --- | --- | --- | --- | --- |
| Legacy MCP 工具面 | 有 | 基本有（缺 1 项） | 大量缺失 | 不一致 |
| `run_game_flow` | 有 | 可调用 | 不可调用 | 不一致 |
| `start_stepwise_flow` | 有 | 可调用 | 不可调用 | 不一致 |
| `pull_cursor_chat_plugin` | 有 | 可调用 | 不可调用 | 不一致 |
| `run_game_basic_test_flow`（新） | 无 | 可调用 | 不可调用 | 不一致 |
| `tools/game-test-runner/**` 资产 | 有 | 有 | 打包未包含 | 不一致 |
| `flows/**` 资产 | 有 | 有 | 打包未包含 | 不一致 |

---

## 核心准则符合度评分（0-100）

- 通用性（全类型 Godot）：`70`
- 工具/契约/运行链一致性：`62`
- 打包/发布生效一致性：`20`
- 证据可复验性：`85`
- 综合分：`59`

---

## 已执行验证（证据命令）

### 指定测试（全部通过）

- `python -m unittest tests.test_mcp_transport_protocol -v`
- `python -m unittest tests.test_flow_execution_runtime -v`
- `python -m unittest tests.test_mcp_gap_audit tests.test_legacy_tool_surface tests.test_legacy_runner_pipeline tests.test_flow_assets_contract tests.test_legacy_stepwise_fixloop_live tests.test_godot_test_orchestrator_packaging tests.test_ci_legacy_coverage tests.test_restoration_status_document -v`

### release 生效面核查（关键）

- `powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" -CheckUpdateOnly`
- 下载 stable zip 后：
  - 检查关键文件是否存在
  - 执行 `python mcp/server.py --tool get_mcp_runtime_info --args "{}"`
  - 执行 `python mcp/server.py --tool run_game_flow --args "{}"`（结果为 `UNSUPPORTED_TOOL`）

---

## 最小修复清单（立即执行）

1. 先完成“单目录整合”改造：发布包内容全部进入 `pointer_gpf/`（含 `mcp/`、`install/`、`godot_plugin_template/`、`tools/game-test-runner/`、`flows/`、必要文档与配置）。
2. 修复 `release-package.yml` 打包范围，补齐 legacy 执行依赖目录。
3. 发布新版本并更新 `mcp/version_manifest.json`（URL/SHA/size）。
4. 给 release 增加“解包后工具清单断言 + legacy 调用冒烟”。
5. 根 MCP 补齐或明确废弃 `check_test_runner_environment`。
6. 更新 gap 审计脚本与 `docs/mcp-gap-analysis-2026-04-10.*` 口径。

---

## 完整修复清单（中长期）

1. 建立“仓库能力 vs release 能力”自动一致性门禁（CI 阻断）。
2. 增加 legacy 工具面快照断言（逐项验证，防回退）。
3. 建立“单目录洁净规则”自动检查（禁止新增根级 gpf 文件扩散）。
4. 梳理并分层通用资产与 legacy fixture，统一文档入口说明。
5. 在实施状态文档中增加“release 实测证据”固定章节。

---

## 已确认约束（2026-04-10）

1. 单目录名称确认：`pointer_gpf/`。
2. 允许保留根目录最小入口文件（例如 `pointer-gpf.cmd`）；
   除入口外，所有 gpf 相关实现与资产必须收纳到 `pointer_gpf/` 内。

---

## 已完成实施进展（本轮）

- 单目录发布结构已接入 release workflow（打包阶段将载荷置于 `pointer_gpf/`，并与 `zip_layout: pointer_gpf_root` 口径一致）。
- root 入口兼容转发已完成（根目录 `pointer-gpf.cmd` 等薄入口指向 `pointer_gpf/` 内脚本与实现）。
- `install/update-mcp.ps1` 已支持 `pointer_gpf` 载荷识别与关键目录同步（含 `tools/game-test-runner`、`flows` 等 legacy 资产路径）。
- legacy 缺口 `check_test_runner_environment` 已在根 MCP 工具面补齐（与 `get_mcp_runtime_info` 所列工具一致）。
- **仍待执行事项**：发布新版本 release 包，并回填 `mcp/version_manifest.json` 中的 `url` / `sha256` / `size_bytes`（使远端 stable 与仓库能力一致；可用 `scripts/verify-release-manifest-artifact.py` 对发布后产物做门禁验证）。

---

## 待补充信息（剩余）

请补充以下信息，便于生成最终修复执行版：

1. 你希望保留的 legacy 工具最小集合（是否必须包含 `check_test_runner_environment`）。
2. release 包预期最小目录清单（是否必须包含 `tools/game-test-runner/**`、`flows/**`、`addons/test_orchestrator/**`）。
3. 对“全类型 Godot 通用性”的口径偏好（是否允许默认携带 gameplay 示例）。
4. 计划发布时间窗口（决定修复优先级和是否 hotfix）。

