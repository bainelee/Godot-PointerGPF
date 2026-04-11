# Godot 资源 UID 漂移与假性 MCP 故障

## 结论

在 `D:\AI\pointer_gpf_testgame` 的这次联调里，MCP 一开始表现为：

- `StartButton` 点击后没有稳定进入关卡
- `node_visible:Crosshair` 等待失败
- 早期看起来像是 MCP 没有正确点击、没有正确切场景，或者 Godot 插件没有正常工作

但真实根因里，有一部分并不在 MCP，而是在 **Godot 资源 UID 漂移**：

- `.tscn` 里记录的 `ext_resource uid=...`
- 与磁盘上对应脚本的 `.gd.uid`
- 已经不一致

Godot 会打印：

- `ext_resource, invalid UID: ... - using text path instead: ...`

这类问题会制造一种很糟糕的假象：

- 场景切换过程产生警告或连锁错误
- MCP 只看到“切场景后的目标节点不存在”
- 用户会误以为“是 MCP 没点到”或者“插件又坏了”

## 本次实际命中的失配

这次已经确认并修正了 3 处：

1. `scenes/enemies/test_enemy.tscn`
- 原脚本 UID：`uid://d0mywfj3gjm5`
- 实际脚本 UID：`uid://cefjlh7ubfb7p`

2. `scenes/player/fps_controller.tscn`
- 原脚本 UID：`uid://bdhvabgdiujd7`
- 实际脚本 UID：`uid://b0cefojgt15wx`

3. `scenes/projectiles/bullet.tscn`
- 原脚本 UID：`uid://cxw47pmkanm5s`
- 实际脚本 UID：`uid://kkiuhdt8gm4`

对应修复文件：

- [test_enemy.tscn](/D:/AI/pointer_gpf_testgame/scenes/enemies/test_enemy.tscn)
- [fps_controller.tscn](/D:/AI/pointer_gpf_testgame/scenes/player/fps_controller.tscn)
- [bullet.tscn](/D:/AI/pointer_gpf_testgame/scenes/projectiles/bullet.tscn)

## 本次真实现象链

在修复前，外部测试工程运行时出现了这些表象：

1. `enter_game` 看起来成功
2. 但后续 `feature_wait_1`
   - `hint='node_visible:Crosshair'`
   - `reason='node not found'`
3. 再继续收窄后，发现并不是纯粹“没点到按钮”，而是：
   - `StartButton` 触发了 `change_scene_to_file`
   - 但 `game_level` 加载阶段伴随资源 UID 警告和运行错误
   - 导致 `Crosshair` 没有稳定进入运行树

## 为什么这会误导 MCP 排障

因为 MCP/插件最终看到的是“运行态证据”而不是编辑器里的完整语义：

- flow 看到的是：目标节点不存在
- runner 看到的是：等待/断言失败
- 用户看到的是：像是 MCP 主路径坏了

但 Godot 编辑器控制台里真正更早的信号是：

- 场景资源引用失配
- 切场景期间加载链不干净

这就是典型的 **false MCP failure**：

- 表面是自动测试失败
- 根因是被测工程资源状态不一致

## 这次联调的关键验证结果

在修正上述 3 个 UID 之后，真实执行：

- `run_game_basic_test_flow_by_current_state`

得到的关键结果是：

- `launch_game` 通过
- `enter_game` 通过
- `feature_wait_1: node_visible:Crosshair` 通过
- `feature_assert_1: node_visible:Crosshair` 通过
- `snapshot_end` 通过
- 整体 `status: passed`

并且收尾也通过：

- `project_close.acknowledged: true`
- `project_close.play_running_by_runtime_gate: false`
- `project_close.debug_game_teardown_ok: true`

这说明：

- 至少这一次案例里，MCP 主链失败并不主要是因为 MCP 本身
- 被测工程资源 UID 漂移修正后，主路径恢复正常

## 对 PointerGPF 的工程含义

这类问题不应该被简单归类成“用户环境问题”。

更合理的结论是：

1. PointerGPF 当前很容易把“被测工程资源错误”表现成“MCP 流程失败”
2. 所以诊断层必须明确区分：
   - MCP/插件协议错误
   - 运行态节点查找错误
   - Godot 资源加载/UID 漂移错误
3. 如果不做这层区分，模型会在错误方向上反复修 MCP

## 后续建议

### 1. 增加资源一致性预检

在针对外部 Godot 工程运行 flow 前，增加一个轻量预检：

- 扫描 `.tscn` 里的 `ext_resource type="Script" uid="..."`
- 对照目标脚本 `.gd.uid`
- 若不一致，提前报告

输出应直接指明：

- 场景文件
- 资源路径
- tscn 中 UID
- 磁盘上 UID

### 2. 把这类问题归类为“被测工程资源错误”

不要把它混成：

- `TARGET_NOT_FOUND`
- `runtime gate failed`
- `bridge unstable`

更好的分类应类似：

- `PROJECT_RESOURCE_UID_MISMATCH`

### 3. 运行期报错要尽量带正文

这次很多时间浪费在：

- `runtime_diagnostics.json` 只有 backtrace，没有错误正文

后续应优先增强 Godot 插件侧诊断，把 engine log 的正文一并带回。

## 给后续模型/开发者的直接规则

如果出现这些现象：

- 点击“开始游戏”后切场景目标节点始终不存在
- 关卡 HUD / Crosshair / Player 节点始终不出现
- Godot 控制台出现 `invalid UID`

优先检查：

1. 目标 `.tscn` 的 `ext_resource uid`
2. 对应 `.gd.uid`
3. 资源是否在复制/迁移/重命名后被 Godot 重新生成过 UID

不要第一时间继续修改 MCP 的点击逻辑、等待时间、或流程规则。

