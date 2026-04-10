# PointerGPF 运行态诊断桥（runtime_diagnostics.json）

## 目的

在 `run_game_basic_test_flow` 等待 `pointer_gpf/tmp/response.json` 时，若游戏内已出现脚本/桥接错误但桥接未返回，MCP 可通过**并行读取**本文件尽快失败，而不是空等到 `step_timeout`。

## 路径与 schema

- **相对路径**：`pointer_gpf/tmp/runtime_diagnostics.json`（与 `runtime_gate.json` 同目录）
- **schema id**：`pointer_gpf.runtime_diagnostics.v1`
- **机器可读契约**：`mcp/adapter_contract_v1.json` → `runtime_diagnostics`

### 最小 JSON 形状

```json
{
  "schema": "pointer_gpf.runtime_diagnostics.v1",
  "updated_at": "2026-04-10T12:00:00Z",
  "source": "game_runtime",
  "severity": "info",
  "summary": "",
  "items": [
    {
      "kind": "bridge_error",
      "message": "",
      "file": "",
      "line": 0,
      "stack": ""
    },
    {
      "kind": "engine_log_error",
      "message": "",
      "file": "",
      "line": 0,
      "stack": ""
    }
  ]
}
```

- `source`：`game_runtime` | `editor` | `external_godot_tools`
- `severity`：`info` | `warning` | `error` | `fatal`
- MCP **快速失败**：当 `severity` 为 `error` 或 `fatal` 时，`FlowRunner` 可在仍有 `step_timeout` 余量时中止等待并返回 `ENGINE_RUNTIME_STALLED`。

## 写入建议（插件 / 外部工具）

1. **刷新频率**：与游戏帧率解耦，建议 0.2s～0.25s 批量写一次；MCP 侧轮询间隔建议 **≤250ms**（默认约 120ms）。
2. **原子性**：先写入同目录 `runtime_diagnostics.json.tmp`，再替换目标文件，避免 MCP 读到半截 JSON。
3. **外部 Godot Tools**：若编辑器/LSP 能导出诊断，可写入**同一 schema**，`source` 填 `external_godot_tools`，无需改 MCP 协议。

## 与错误码关系

- `ENGINE_RUNTIME_STALLED`：MCP 在等待桥接响应时观测到 `error`/`fatal` 诊断快照。
- `ENGINE_DIAGNOSTICS_FATAL`：保留给未来「仅诊断、未进入 flow 步骤」的显式工具错误路径（契约层预留）。

## 能力边界

参考实现通过 Godot 4.5+ 的 **`OS.add_logger` + `Logger._log_error`**，将走引擎 `_log_error` 路径的 GDScript 报错（含常见栈信息）写入 `items`（`kind=engine_log_error`），与 `bridge_error` 一并参与 `severity` 计算。

仍**不保证**覆盖：仅走标准输出、主线程已无法执行写入、或未触发 `_log_error` 的故障。此类情况仍依赖 `step_timeout` / `TIMEOUT` 与人工查看 Godot 输出。
