"""tests package —— 单元测试和集成测试。

红线（project_rules.md §4）：
  - 测试不得真实联网、不得真实加载模型
  - 用 engine_stub 断言调用顺序 load→set_ref→tts→产物校验
"""
