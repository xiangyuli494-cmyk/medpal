# 小暖陪诊 · 用户端（uni-app）

用户端的**小程序与 H5 共用骨架**：一套 Vue 3 代码，分别编译到 H5 与微信小程序。

- 方向说明：[`docs/adr/ADR-020-用户端增加小程序预览形态.md`](../../docs/adr/ADR-020-用户端增加小程序预览形态.md)
- 页面与数据流：[`docs/specs/mini-program.md`](../../docs/specs/mini-program.md)
- 协议：[`docs/api/ws-protocol.md`](../../docs/api/ws-protocol.md)

> 本期**不做小程序上架**，只做开发者工具预览与体验版；H5 仍是主演示形态。这行口径来自
> `docs/plan/00-项目工期与范围基线.md` §3.3，ADR-020 没有改它。

## 快速开始

```powershell
conda activate medpal312   # 只跑前端时不需要，但保持一致
cd frontend/user-app
npm install

# H5，端口 5173（设备端 iframe 默认指向这个地址）
npm run dev:h5

# 微信小程序：产物在 dist/dev/mp-weixin，用微信开发者工具打开
npm run dev:mp-weixin
```

H5 构建：

```powershell
npm run build:h5
```

小程序构建：

```powershell
npm run build:mp-weixin
```

## 演示模式

默认 `VITE_DEMO_MODE=1`（仓库根目录 `.env`）：不连后端，用本地 mock 会话走完 11 个节点。
要连真实服务，设 `VITE_DEMO_MODE=0`，并确认：

```bash
VITE_API_BASE=http://127.0.0.1:8000/api/v1
VITE_WS_BASE=ws://127.0.0.1:8090
VITE_EPISODE_ID=ep_001
```

设备端与服务端联调时，5173 这个端口不要改，`device/src/member-pages.js` 默认指向它。

## 目录

```text
src/
├── api/           统一请求层，只用 VITE_API_BASE，页面不拼地址
├── components/    AppHeader / ElderButton / FlowBar / StepList
├── constants/     11 节点与 9 步对外换算、通道文案
├── mock/          演示陪诊单与 mock 会话脚本
├── pages/         home / session / journey / profile
├── services/      协议构造与解析、Socket 传输（真实 / mock）
├── stores/        pinia 会话状态
├── styles/        设计令牌与全局样式
└── utils/         存储与格式化
tests/             node --test 跑纯函数与文案红线
```

## 页面

| 页面 | 路径 | 作用 |
| --- | --- | --- |
| 首页 | `pages/home/index` | 输入陪诊单号、开始陪诊、进入进度 |
| 问小暖 | `pages/session/index` | 字幕、主操作、选项、文字输入、求助 |
| 陪诊进度 | `pages/journey/index` | 9 步进度、时间轴、待办 |
| 我的 | `pages/profile/index` | 字号三档、无障碍通道、家属可见开关 |

## 测试

```powershell
npm test
```

跑的是纯函数与文案扫描，不依赖 uni-app 运行时；UI 目前靠手工验证。

## 小程序约束

- 开发者工具里勾选「不校验合法域名」，否则 `http://127.0.0.1` 与 `ws://` 都会被拦；
- 正式体验版需要 HTTPS / WSS，域名须在小程序后台配置；
- `manifest.json` 的 `appid` 当前是 `touristappid`（测试号），换成真实 AppID 才能上传体验版；
- 小程序没有 `localStorage`，本项目统一走 `uni.setStorageSync`；
- 小程序端不做语音采集，`mic` 在骨架阶段用文字输入代替，等 T5 的音频适配器接入。