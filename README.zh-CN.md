# Pointer GPF V2

本仓库现在把 `main` 视为干净的 V2 主线。

## `main` 当前包含什么

- [v2](/D:/AI/pointer_gpf/v2) 下的 V2 Godot MCP 重建实现
- [docs](/D:/AI/pointer_gpf/docs) 下的 V2 文档
- [scripts](/D:/AI/pointer_gpf/scripts) 下的 V2 固定回归脚本

V2 当前范围刻意保持收敛：

- 配置 Godot 可执行文件
- 向目标工程同步插件
- 执行 preflight
- 生成项目级 `basicflow.json` + `basicflow.meta.json`
- 运行最小和交互式 file-bridge flow
- 支持 `click`、`wait`、`check`、`closeProject`
- 在 `closeProject` 后验证收尾
- 拒绝同工程并发 flow 与多编辑器冲突

## 推荐阅读入口

- 状态：[docs/v2-status.md](/D:/AI/pointer_gpf/docs/v2-status.md)
- 架构：[docs/v2-architecture.md](/D:/AI/pointer_gpf/docs/v2-architecture.md)
- 交接：[docs/v2-handoff.md](/D:/AI/pointer_gpf/docs/v2-handoff.md)
- V2 包目录：[v2/README.md](/D:/AI/pointer_gpf/v2/README.md)

## 固定回归命令

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame
```

## Legacy 分支

旧 MCP 系统已经保存在 `legacy/mcp` 分支中，只作为参考。
以后默认只维护 `main`。
