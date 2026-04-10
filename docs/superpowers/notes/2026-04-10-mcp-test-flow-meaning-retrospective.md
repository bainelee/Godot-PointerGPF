# MCP 测试流意义复盘记录

> 记录日期：2026-04-10  
> 性质：对 PointerGPF 中「通过 MCP 驱动的基础测试流程」的定位与价值说明，供后续计划与验收对照。

## 1. 在本项目里「MCP 测试流」指什么

在仓库语境中，**MCP 测试流**主要指工具链上的这条固定路径：

1. **`design_game_basic_test_flow`**：在目标 Godot 工程上，依据项目上下文与约定策略，生成（或更新）一份**可执行**的基础测试流程定义（flow），落盘到工程约定的 `pointer_gpf/generated_flows/` 等路径。
2. **`run_game_basic_test_flow`**（及按当前状态变体）：按 flow 中的步骤，通过 **adapter / 文件桥**（`pointer_gpf/tmp/command.json` ↔ `response.json`）驱动编辑器或运行态执行动作，并产出**可核查**的运行结果与报告。

它不是「只生成 JSON 说明文档」，而是要求：**设计结果能被同一条 MCP 执行路径真正跑起来**，并在失败时返回结构化阻塞信息（例如门控未通过时的 `RUNTIME_GATE_FAILED` 等），而不是静默占位。

## 2. 单步语义：每一步在真实游戏 / 编辑器里的含义

执行测试流时，**每一个步骤**在理想模型上应满足下面闭环（与设计、实现、验收口径一致）：

1. **MCP（经执行器 + 适配层）向实际 Godot 进程发出一个具体动作**  
   例如打开某场景、点击某 UI、等待若干帧、读取节点状态、截图等——对应 adapter 契约里的一种 **可观察** 行为，而不是「空转」或仅改本地 JSON。

2. **等待该动作在运行态或编辑器态产生结果**  
   通过文件桥 `command.json` → `response.json`（或等价通道）拿到 **引擎侧回执**：成功/失败、错误信息、以及步骤约定要带回的数据（如节点路径、截图路径等）。

3. **根据 flow 中本步的「预期」做判定**  
   判定可以体现在：响应字段校验、与上一步状态的差异、后续步骤的前置条件等。**未满足预期**时应停止或按 `fail_fast` 策略结束本 run，并留下可核查证据，而不是默默进入下一步。

4. **再进入下一步**  
   只有当前步在契约意义上「已完成且符合预期」（或明确记录为允许的跳过/可选步），才继续下一命令。

因此：**流程里的每一条记录都应对应真实世界中的一件事**——在编辑器或 `play_mode` 下能被玩家或自动化同样复述其意图；禁止把无操作含义的占位步写进「可执行基础测试流程」并当作通过。

> 说明：具体一步能映射到哪些 `action`、预期如何编码，以当前 `mcp/adapter_contract_v1.json` 与 flow schema 为准；上述四条是**语义要求**，用于评审 flow 设计与执行器行为是否「一步一义」。

## 3. 为什么要做这条流（意义）

- **把代理工作锚定在真实运行态**  
  流程强制与 **`play_mode`（运行门禁）** 挂钩：未进入可响应的运行态时，应明确失败并给出 `blocking_point`、`next_actions`、`engine_bootstrap` 等字段，避免「看起来执行了、实际没有进游戏」的误判。

- **可重复的机器可读契约**  
  Flow 定义 + 执行器 + 插件桥接，使「打开场景、执行步骤、截图/断言」等行为有统一入口，便于 CI（smoke/integration）、跨工程脚本（如 `verify-cross-project.ps1`）和人工排障共用同一语义。

- **对用户可见的执行证据**  
  约定在 shell 侧输出**三阶段**语义（开始执行 / 执行结果 / 验证结论）及时间戳前缀，便于日志审查与自动化截取；流程结束需有**收尾关闭**语义（停止 Play、回到编辑器空闲态，默认保留编辑器进程）。

- **与产品目标一致**  
  PointerGPF 的定位是「面向 Godot 灰盒自动化的 MCP 工具包」；基础测试流是其中**从上下文 → 种子流程 → 真实执行 → 产物校验**的关键一段，把 README 里描述的 automation boundary 落到可验证步骤上。

## 4. 与 `examples/godot_minimal`（含 FPS 计划）的关系

`docs/superpowers/plans/2026-04-10-godot-minimal-fps-mcp-example.md` 中的改造目标，是把示例工程做成 **MCP 工具链回归与演示** 用的靶子：足够的场景数量、稳定的节点路径（如文档/MCP 提示中的 `UI/UI1` 等前缀）、菜单 → 关卡切换等，便于 **打开场景、查节点、跑流程、截图** 等动作有稳定抓手。

因此：**MCP 测试流**是「通用执行管道」；**godot_minimal 的 FPS/UI 拆分**是「让管道在示例工程上有足够厚的可测表面」——二者是管道与样例工程的关系，不要混为一谈。

## 5. 验收时建议对照的要点

- 是否走了 **真实执行**（非仅静态检查或空桥接）。  
- **每一步**是否可说明：发了什么动作、等了什么回执、用什么条件算符合预期；是否存在无含义的填充步。  
- 门控未通过时是否 **立即停止** 并返回可验证失败载荷。  
- 日志中是否能看到 **三阶段** 用户向语义行（见根目录 README 中 Executable basic flow 小节）。  
- 是否执行 **closeProject / 等效收尾**，并有 `project_close` 类证据（以当前契约为准）。  
- 可选：`scripts/assert-mcp-artifacts.ps1 -ValidateExecutionPipeline` 等脚本是否与本次变更一致通过。

## 6. 相关文档索引

| 文档 | 用途 |
|------|------|
| `README.md` / `README.zh-CN.md` | 工具列表与 Executable basic flow 政策摘要 |
| `docs/superpowers/plans/2026-04-09-mcp-basic-flow-runtime-execution.md` | 基础流程全链路执行的计划与文件职责 |
| `docs/mcp-real-runtime-input-contract-design.md` | 运行时输入契约与门控设计讨论 |
| `docs/mcp-implementation-status.md` | 实现状态矩阵 |
| `docs/superpowers/plans/2026-04-10-godot-minimal-fps-mcp-example.md` | 示例工程 MCP 向改造计划 |
| `.cursor/rules/gpf-runtime-test-mandatory-play-mode.mdc` | 代理侧强制执行规则（Play 门禁与收尾） |

---

*本文件为复盘记录；若实现与本文描述不一致，以代码与 adapter 契约为准，并应回写更新本记录或状态矩阵。*
