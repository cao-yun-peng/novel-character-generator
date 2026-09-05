# E-20260905-CACHE-CONTINUATION-078

- 时间：2026-09-05（Asia/Shanghai）。运行时：0.1.0.dev28；领域 Schema：3.27.0-draft1。
- 范围：promotion、identity、rescue、transition 的请求指纹预检和 promotion Grounding 恢复。
- 验证命令：`E:/BaiduNetdiskDownload/miniconda/conda/python.exe -m pytest -q -p no:cacheprovider`。
- 退出状态：0；结果：211 passed、19 subtests passed，3.88 秒；真实 Provider 调用 0。
- 环境：默认 Python 3.12 未安装 pytest；使用既有 Conda Python。沙箱内 pytest 临时目录被拒绝，获工具授权后在沙箱外验证；关闭 pytest cacheprovider 避免旧缓存目录权限警告。
- 回归：四阶段续跑、损坏 Grounding 重新计算、缺失/变化指纹拒绝，M3 缺失前置任务时先检测后置缓存不兼容且零调用。
- 代码版本：工作区含用户既有未提交修改；本证据以同目录 source-hashes.json 的 SHA-256 绑定实际文件，不用 HEAD 冒充工作区版本。
- 有效期：上述实现、请求策略或测试依赖变化前；变更后重验。
- 限制：无真实小说下游结果再生成，无统一旧缓存迁移验收，无模型质量 Gate；rescue 仅按当前动态轮预检。

- 附加验收：`python -m compileall -q src tests` 退出 0；`git diff --check` 退出 0；project-to-act `--validate` 返回 valid=true、issues=[]。
