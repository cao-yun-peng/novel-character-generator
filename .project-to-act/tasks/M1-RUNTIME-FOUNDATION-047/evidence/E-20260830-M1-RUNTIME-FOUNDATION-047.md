# E-20260830-M1-RUNTIME-FOUNDATION-047

- 时间：2026-08-30，Asia/Shanghai。
- 用户请求：根据技术文档开始 M1 阶段实现。
- Git 基线：`a6c6d16a5731f83aded0345fc1de6aef00604025`；工作区包含用户既有未提交的契约、调研和治理变更，本任务未覆盖或清理这些变更。
- 运行时：Python `0.1.0.dev1`，要求 Python 3.11+，零第三方运行时依赖。
- Schema：`3.4.0-draft1`；M1 envelope、model input 与 model output 字段对齐测试通过。
- Provider 调用：0；本任务只建立 `M1Provider` 协议和严格请求边界，未冒充真实模型质量。
- 测试命令：`$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest discover -s tests -v`。
- 测试结果：退出状态 0；23 项通过，0 失败，0 跳过。覆盖重叠 Manifest、complete/truncated、原始 hash、Unicode code-point span、系统字段隔离、exact/describe/null、中文提示词规则、后缀归一、occurrence/relation、拒绝原因与 packet hash。
- 语法验证：9 个 Python 文件经 `ast.parse` 通过；因实际仓库目录与工作区配置拼写不一致导致目标目录无 `.pyc` 写权限，验证显式禁止 bytecode，不影响源代码执行。
- 项目台账：`init_project_management.py --validate` 返回 `valid: true`、0 issue。
- Git 检查：`git diff --check` 退出状态 0；只有仓库既有 LF/CRLF 提示，无空白错误。
- 产物 SHA-256：
  - `pyproject.toml`：`a23686e489991a855390c93633a65994ba5641e8a37c9d5c3eadbce333781e55`
  - `README.md`：`b5eaee3f64d2bbca856c98f03483310fce33ad11ef35132c08fefaba26e43a41`
  - `src/novel_character_generator/chunking.py`：`2aa9b09bf2654b171c11694abb82117ad3f3313cac83acd1a03ee7f326867b39`
  - `src/novel_character_generator/m1.py`：`083ceffe23f261cdf8cd7540538799f5aab7ba12177abebbedafea8cdc75ae0e`
  - `src/novel_character_generator/grounding.py`：`4e381830004854864db3de1cdde52bc9dc078c7c2016a2903f12ded842edf04b`
  - `src/novel_character_generator/text.py`：`e588af5c236b358d2976057f23cecfdc61bf8330565de04687a9a46f18a666cf`
  - `tests/test_chunking.py`：`3935e2cfd7645753c5e553e01ced90f3841b0a1ae08da284dcad47a2fd15dcec`
  - `tests/test_m1.py`：`582b0d23f1864a171e216905cf19395e28137a3953efd319f6660b8e3d5ece63`
  - `tests/test_contract_alignment.py`：`eab6b64e98492277ac108c17d33919de781246979c67aca5a6caca29cfb12290`
- 验收结论：M1 运行时基础任务完成；M1 功能整体仍为 `in_progress`，直到具体 Provider 和真实模型评测完成。
- 有效期：直到 M1 输入输出契约、hash/span 规则、提示词、Provider 边界或上述文件发生变化。

