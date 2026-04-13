# Pointer GPF V2

<p align="center">
  <img src="./pointer_gpf_logo.png" alt="PointerGPF logo" width="780" />
</p>

**简体中文（默认）** | [English](./README.en.md)

Pointer GPF 是一个面向 **Godot 灰盒测试** 的 MCP 工具链。

它当前的目标很明确：

- 帮你把 Godot 工程接入可执行的测试链路
- 帮你围绕 Godot 游戏 bug 做灰盒测试、复现与修复
- 帮你用受约束的自然语言和显式工具来驱动这些能力

它当前**不是**一个“什么都能理解、什么都能自动处理”的开放式代理。

## 它现在能做什么

当前 `main` 分支上的 V2 已经可以：

- 配置 Godot 可执行文件
- 向目标工程同步 V2 插件
- 对目标工程执行 `preflight`
- 生成项目本地 `basicflow.json` 与 `basicflow.meta.json`
- 分析为什么当前 `basicflow` 已 stale
- 运行基础测试流程 `run_basic_flow`
- 支持 `click`、`wait`、`check`、`closeProject`
- 在流程结束后验证 teardown 是否真的完成
- 拒绝同工程并发 flow、拒绝多编辑器冲突
- 提供一组**受约束的自然语言入口**

当前主线判断也已经调整为：

- `input isolation` 的进一步完善记为后期 TODO
- `basicflow` 的进一步补充增强记为后期 TODO
- 下一阶段主线回到 GPF 的核心产品能力

如果你想看这个方向文档，请读：

- [2026-04-14 GPF Core Direction](./docs/2026-04-14-gpf-core-direction.md)

当前自然语言入口支持的高频方向主要是：

- 跑基础测试流程
- 重新生成基础流程
- 分析基础流程为什么 stale
- 跑项目预检
- 配置 Godot 路径

## 它现在不是什么

当前 V2 **不承诺**这些能力：

- 开放域自然语言理解
- 任意宽泛请求的一步到位自动编排
- 自动修复一切工程问题
- 为了“更聪明”而无限扩张词表和行为

## 下一阶段主线

GPF 后续应该主要围绕这条链路继续开发：

1. 用户用自然语言描述游戏中的 bug
2. GPF 分析可能原因与受影响区域
3. GPF 定义“没有这个 bug 时应该成立”的显式断言
4. GPF 设计或更新能够触及该 bug 的测试流
5. GPF 自动运行测试流，确认 bug 可以复现
6. GPF 修改项目代码尝试修复
7. GPF 再次运行测试流与断言，确认修复生效

如果你想了解当前自然语言边界，请直接看：

- [如何命令 GPF](./docs/v2-how-to-command-gpf.md)
- [自然语言边界原则](./docs/v2-natural-language-boundary-principles.md)

## 推荐上手方式

最稳妥的起步顺序是：

1. 先读状态文档
2. 配置 Godot 路径
3. 跑项目预检
4. 查看当前支持的命令边界
5. 再决定是生成 basicflow 还是直接运行已有 basicflow

### 1. 给使用者的阅读入口

如果你是项目使用者、维护者、测试者，建议先读这些：

- [V2 状态](./docs/v2-status.md)
- [V2 架构](./docs/v2-architecture.md)
- [V2 交接说明](./docs/v2-handoff.md)

它们分别回答：

- 当前项目已经做到哪一步
- 当前系统是怎么组织的
- 新对话或新协作者应该从哪里接手

### 2. 给编码助手 / AI 代理的阅读入口

如果你准备让编码助手继续开发、调试或验收，建议它先读：

- [docs/v2-status.md](./docs/v2-status.md)
- [docs/v2-how-to-command-gpf.md](./docs/v2-how-to-command-gpf.md)
- [docs/v2-natural-language-boundary-principles.md](./docs/v2-natural-language-boundary-principles.md)
- [docs/v2-handoff.md](./docs/v2-handoff.md)

这组文档更适合回答：

- 当前主线工作做到哪里
- 用户层命令边界是什么
- 自然语言支持不应该如何扩张
- 下一轮开发该从哪里继续

### 3. 运行固定回归

```powershell
python D:\AI\pointer_gpf\scripts\verify-v2-regression.py --project-root D:\AI\pointer_gpf_testgame
```

### 4. 查看当前支持的用户命令

```powershell
python -m v2.mcp_core.server --tool get_user_request_command_guide --project-root D:\AI\pointer_gpf_testgame
```

### 5. 典型命令

项目预检：

```powershell
python -m v2.mcp_core.server --tool preflight_project --project-root D:\AI\pointer_gpf_testgame
```

通过受约束自然语言触发项目预检：

```powershell
python -m v2.mcp_core.server --tool handle_user_request --project-root D:\AI\pointer_gpf_testgame --user-request "跑项目预检"
```

查看基础流程生成问题：

```powershell
python -m v2.mcp_core.server --tool get_basic_flow_generation_questions --project-root D:\AI\pointer_gpf_testgame
```

运行基础流程：

```powershell
python -m v2.mcp_core.server --tool run_basic_flow --project-root D:\AI\pointer_gpf_testgame
```

## 当前 release 形态

当前 V2 已经具备一条经过 smoke 验证的最小 release 路径：

- 构建源码 bundle zip
- 解包后运行 V2 单测
- 解包后运行 MCP 命令入口验证

相关文档与脚本：

- [docs/v2-release-and-install.md](./docs/v2-release-and-install.md)
- [scripts/build-v2-release.py](./scripts/build-v2-release.py)
- [scripts/verify-v2-release-package.py](./scripts/verify-v2-release-package.py)

这条路径当前证明的是：

- 用户拿到 zip 源码包后，可以解压并成功运行当前 V2

它当前还不是：

- 原生安装器
- pip 包
- 一键式 MCP 客户端集成安装

## 推荐阅读顺序

如果你是第一次接触这个仓库，建议按这个顺序读：

1. [docs/v2-status.md](./docs/v2-status.md)
2. [docs/v2-how-to-command-gpf.md](./docs/v2-how-to-command-gpf.md)
3. [docs/v2-natural-language-boundary-principles.md](./docs/v2-natural-language-boundary-principles.md)
4. [docs/v2-basic-flow-user-intent.md](./docs/v2-basic-flow-user-intent.md)
5. [docs/v2-basic-flow-staleness-and-generation.md](./docs/v2-basic-flow-staleness-and-generation.md)
6. [docs/v2-plugin-runtime-map.md](./docs/v2-plugin-runtime-map.md)

如果你只是想使用它，而不是继续开发它，可以优先读：

1. [docs/v2-status.md](./docs/v2-status.md)
2. [docs/v2-how-to-command-gpf.md](./docs/v2-how-to-command-gpf.md)

## 分支说明

当前仓库约定是：

- `main`：只维护 Pointer GPF V2
- `legacy/mcp`：保留旧系统，仅供参考

如果你想看旧版实现，请切到 `legacy/mcp`，但不要把旧系统逻辑重新混回 `main`。
