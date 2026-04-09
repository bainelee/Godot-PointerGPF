# 权威需求基线（Source of Truth）

本目录用于存放并维护你通过自然语言描述、并经过整理确认后的核心需求信息。

这些文档是后续开发与验证时最优先遵守的基线：

- 实际需求（产品必须做什么）
- 用户实际体验需求（用户必须感受到什么）
- 实际使用场景与效果案例（在哪些场景验证、达成什么结果）

## 使用规则

1. 先更新本目录，再改代码或测试。
2. 需求冲突时，以本目录最新确认内容为准。
3. 每次实现完成后，按本目录逐项验收并记录结果。
4. 文档更新应尽量具体、可验证、可复现，避免抽象表述。

## 建议维护流程

1. 新增或调整需求 -> 更新对应文件。
2. 标注变更日期、原因、影响范围。
3. 对应代码提交或测试报告中引用本目录条目。
4. 发版前做一次全量核对，确保实现与这里一致。

## 目录说明

- `01-actual-product-requirements.md`：产品实际需求
- `02-user-experience-requirements.md`：用户实际体验需求
- `03-real-world-scenarios-and-case-studies.md`：实际使用场景与效果案例
- `requirements-index.json`：机器可读索引（由脚本自动生成）

## 自动转换生成

当上述 3 份核心需求文档更新后，执行以下命令生成最新索引：

```powershell
python "scripts/generate_requirements_index.py"
```

输出文件：

- `docs/authoritative-requirements/requirements-index.json`
