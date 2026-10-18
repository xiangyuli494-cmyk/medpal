# backend/adapters —— 能力适配器

ASR / TTS / OCR / Push 四类外部能力。每一类都必须有真实现与假实现。

## 规则

1. 测试默认用 fakes.py，不联网、不花钱；
2. 真实现只在 W5 之后接，接一个验一个，回滚预案先写好；
3. 适配器抛的是 base.py 里定义的四类异常，不许把供应商的异常直接漏到业务层。

## 现在有什么

| 文件 | 内容 |
| --- | --- |
| base.py | 四个 Protocol 与五类异常、结果数据类 |
| fakes.py | FakeAsr / FailingAsr / FakeTts / FakeOcr / FakePush |

W3 补：FakeOCR 的剂量模糊样例、FakePush 的失败注入。
W5 补：DashScope 的 ASR / TTS / OCR 真实现。
