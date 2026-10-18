"""领域层：纯逻辑，零框架依赖。

约束（12 号 §2.3）：
- 不得 import django / requests / sqlalchemy / 任何 SDK；
- 不得读写数据库、不得发网络请求；
- 单元测试覆盖率要求 100%。
"""

__version__ = "0.1.0"
