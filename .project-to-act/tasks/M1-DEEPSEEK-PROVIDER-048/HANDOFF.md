# M1-DEEPSEEK-PROVIDER-048

DeepSeek Responses API 适配器已经完成。默认使用 `deepseek-v4-flash` 和 `json_schema`，支持环境配置、HTTPS 限制、脱敏 trace、有界重试、错误分类及 `probe-deepseek-m1` 显式探测命令；Provider 输出仍通过原有 M1 严格校验和 grounding。

本任务只使用 fake transport 测试，真实 API 调用为 0。下一步由用户在本机设置 `DEEPSEEK_API_KEY` 后执行一次低成本 smoke；Key 不应发送到聊天或写入项目文件。smoke 成功后进入 M1 shadow 评测，不能以单次成功替代质量 Gate。
