## PointerGPF Release Notes

### English

This release keeps PointerGPF focused on practical Godot automation through MCP:

- Stable MCP runtime and transport compatibility
- Clear plugin lifecycle tools for target Godot projects
- Project-context and flow-seed generation for agent workflows
- Figma-to-game UI compare and approval-gated fix suggestion loop

#### Quick update

```powershell
powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" -ForceRemote
```

#### Agent tasks

- Read `docs/quickstart.md` and `docs/configuration.md`
- Run `install/start-mcp.ps1` and `get_mcp_runtime_info`
- Execute project-specific MCP tools as requested

#### Human-only checks

- Confirm MCP server is enabled in Cursor panel
- Confirm status dot is green and tools are visible
- Review approval-gated actions before applying UI fix plans

---

### 中文（简体）

本次版本继续围绕 Godot + MCP 的可落地自动化能力：

- 稳定的 MCP 运行时与传输兼容性
- 清晰的插件生命周期工具（安装/启用/更新/检查）
- 面向 Agent 的项目画像与 flow seed 生成
- Figma 到游戏 UI 的对比与“人工授权”修复建议闭环

#### 快速更新

```powershell
powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" -ForceRemote
```

#### 交给 Agent 执行

- 先阅读 `docs/quickstart.md` 与 `docs/configuration.md`
- 执行 `install/start-mcp.ps1` 与 `get_mcp_runtime_info`
- 按需求运行项目级 MCP 工具

#### 你需要亲自动手（不可替代的人类操作）

- 在 Cursor 面板确认 MCP 服务已开启
- 确认状态点为绿色、工具可见
- 涉及 UI 修复授权门禁时，由你做最终批准

