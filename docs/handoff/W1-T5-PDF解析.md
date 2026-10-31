# 模块：PDF 解析（按小节分段与页码锚点）

## 一句话
把文本型 PDF 拆成带页码锚点的块，供本体抽取与跨文档取证引用，对应赛题3 W1 任务 5.1。

## 数据流
PDF 文件 → PyMuPDF 逐页取文本 → 章节正则识别小节（第X章 / 一、 / 2.1）→ 生成 p{页}.s{节} 与 p{页}.t{表}.r{行} 锚点 → 返回 blocks 与 anchors，供 ingest_asset 消费。

## 我改了什么（人工修改点）
- PyMuPDF 改为函数内延迟导入，未装依赖时本模块仍可 import，不影响 skeleton 运行。
- 章节正则从只识别中文数字扩展为「第3章」这类阿拉伯数字也能识别。
- 测试用 PDF 的标题改成 ASCII，因 PyMuPDF 默认字体渲染不了中文，否则抽不到文字。
- 锚点格式对齐 mcp-contract §1.2 的 pdf_text 规则，不使用 text 模态的 s2.p1.c3 写法。
- `requirements-dev.txt` 补 `pymupdf>=1.24`（带 python<3.13 条件），否则 CI 装不上依赖、PDF 用例会被跳过。

## 怎么验证的
`pytest agent/tests/test_pdf_parse.py -q` 得到 4 passed；生成的 20 页 PDF 识别出 20 个小节且页码覆盖 1–20，每个块都带合法锚点；`ruff check agent` 通过；`python -B -m agent.skeleton` 仍输出 OK 5 steps，满足「加粗后 skeleton 仍绿」。
