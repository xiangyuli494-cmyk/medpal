# device —— 设备端模拟器

浏览器形态的设备端空壳，用来在没有树莓派时模拟 **7 寸 1024×600 横屏** 的陪诊机。

按 ADR-019：**机身不设实体按键**，所有交互都在屏内。设备端只做三件事：

1. 显示服务端下发的标题、正文、字幕；
2. 发送 `touch.event` / `text.input`；
3. 渲染 `turn_result`，不自己推进状态。

同一套页面在笔记本上是模拟器，在树莓派 4B + 7 寸屏上是真设备。

## 快速开始

```powershell
cd device
npm install
npm run dev
```

打开 `http://127.0.0.1:5176`。  
按 `?kiosk=1` 打开则隐藏联调工具条，只留设备画面：

```text
http://127.0.0.1:5176/?kiosk=1
```

设备端读取仓库根目录的 `.env`（`vite.config.js` 里 `envDir: '..'`）：

```bash
VITE_WS_BASE=ws://127.0.0.1:8090
VITE_SESSION_ID=s_001
VITE_DEVICE_ID=dev_001
VITE_EPISODE_ID=ep_001
VITE_ACCESSIBILITY_MODE=elder

VITE_USER_APP_URL=http://127.0.0.1:5173
VITE_FAMILY_APP_URL=http://127.0.0.1:5174
VITE_CONSOLE_URL=http://127.0.0.1:5175
```

## 启动联调服务

```powershell
conda activate medpal312

# 只在本机演示
python tools/mock_api.py
python tools/mock_ws.py

# 平板/树莓派通过局域网访问时
python tools/mock_api.py --host 0.0.0.0
python tools/mock_ws.py --host 0.0.0.0

# 或
powershell -ExecutionPolicy Bypass -File tools/dev.ps1 -BindHost 0.0.0.0
```

> mock 没有鉴权，只应在可信的 4G 热点/局域网里开放 `0.0.0.0`。

协议（`docs/api/ws-protocol.md`）的最小闭环：

```text
C→S session.hello
S→C session.ready
C→S touch.event { target:"primary", action:"tap" }
S→C turn_result
C→S ack { turn }
```

`turn_result.primary_label` 会更新屏内主操作按钮的文案；设备端不自己编按钮文案。

## 屏内控件

| 控件 | 上行 | 说明 |
| --- | --- | --- |
| 主操作 | `touch.event { target:"primary", action:"tap" }` | 文案由服务端 `primary_label` 下发 |
| 一键求助 | `touch.event { target:"sos", action:"tap" }` | 单击即触发 |
| 点位选择 | `touch.event { target:"spot", action:"tap" }` | 老人在屏上选点位 |
| 语音（文字代替） | `text.input { text }` | 麦克风选型前用文字输入代替 |
| 返回 / 菜单 / 设置 | 不上行 | 纯本地；设置页后续补音量、语速、高对比 |
| 选项胶囊 | `touch.event { target:"option:<slot_id>", action:"tap" }` | 服务端下发 slots 时出现 |

调试工具条里的旧四键映射：

| 旧键 | 现在映射 |
| --- | --- |
| `GREEN_DOWN` | `primary` |
| `GREEN_UP` | 本地返回 |
| `RED_LONG` | `sos` |
| `SIDE` | `spot` |

## 调用小组成员页面

顶部标签页：设备端 / 用户端 / 家属端 / 工作台。  
页面用 iframe 嵌入；禁止 iframe 时点“新窗口打开”。

从平板或树莓派通过 `http://<笔记本IP>:5176` 打开时，设备端会把 `127.0.0.1` 自动替换成当前主机名。  
对方开发服务器也必须监听 `0.0.0.0`：

```bash
npm run dev -- --host 0.0.0.0
```

按键会同时转发给嵌入页面：

```js
{ type: 'medpal:control', session: 's_001', target: 'primary', action: 'tap' }
```

文字输入：

```js
{ type: 'medpal:text', session: 's_001', text: '腿疼' }
```

### 为什么标签页是空白

当前仓库的 `frontend/user-app`、`frontend/family` 还是空目录，所以标签能切，但没有页面可加载。要看到内容，先启动对应成员的开发服务器：

```bash
# 用户端 / 家属端 / 工作台，分别监听 5173 / 5174 / 5175
npm run dev -- --host 0.0.0.0
```

排查顺序：

1. 用 `curl http://127.0.0.1:5173` 确认页面返回 200；
2. 看成员页地址栏里的 URL 是否正确；
3. 从平板/Pi 访问时，成员 dev server 必须监听 `0.0.0.0`；
4. 页面若设置 `X-Frame-Options`/CSP，iframe 会被拒，点“新窗口打开”；
5. `?kiosk=1` 会隐藏联调标签页，开发时不要带这个参数。

## kiosk 启动

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File tools/start-kiosk.ps1
# 或
powershell -ExecutionPolicy Bypass -File tools/start-kiosk.ps1 -Url http://127.0.0.1:5176
```

树莓派 / Linux：

```bash
./tools/start-kiosk.sh http://127.0.0.1:5176
```

两个脚本都会自动追加 `?kiosk=1`。

## 边界

- 不做状态机、不做话术、不做医学判断；
- 不直接访问数据库；
- 按钮只发命令，页面只渲染服务端返回；
- 设备端不自行推进状态节点（`docs/api/ws-protocol.md` §10）。
