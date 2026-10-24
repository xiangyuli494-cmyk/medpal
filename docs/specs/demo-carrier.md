# 演示载体方案（W2）

> 责任人：T2（设备端与嵌入式）  
> 状态：W2 草稿，W6 前复核  
> 依据：ADR-014（硬件为条件交付）、ADR-018（手持借出式）、ADR-019（硬件收敛为树莓派 4B + 7 寸屏）、`docs/specs/device-ia.md`、`device/README.md`

---

## 1. 结论

| 项 | 决策 |
| --- | --- |
| 主演示载体 | 笔记本 + 平板/笔记本浏览器，双机备份 |
| 目标设备 | Raspberry Pi 4B 4GB + 7 寸 1024×600 IPS 电容触摸屏 |
| 交互形态 | 横屏触摸，**机身不设实体按键**（ADR-019） |
| 定位 | C4 条件交付 / 答辩加分项；不承担主流程 |
| 开发模拟器 | `device/`（Vite + 原生 JS），笔记本上运行 |
| 真机运行 | Pi 只跑 Chromium kiosk；Python 后端在笔记本上 |
| 网络 | 4G 随身 WiFi 或笔记本热点；不用医院 WiFi |
| 麦克风/音箱 | 型号未选定；选型前用屏内文字输入和预置短语代替 |

如果要把树莓派改成主演示设备，需先改 ADR-014 并重评 W6 前的镜像、音频、供电风险；当前不这样做。

---

## 2. 硬件 BOM（ADR-019）

硬件清单只有七项：

| 项 | 规格 | 数量 | 说明 |
| --- | --- | --- | --- |
| 主控 | Raspberry Pi 4 Model B 4GB | 1 | 跑 Chromium kiosk |
| 屏幕 | 7 寸 1024×600 IPS 电容触摸屏 | 1 | 横屏；电容触控 |
| 外壳 | 亚克力风扇外壳 | 1 | 散热与固定 |
| 存储 | 32GB TF 卡 + 读卡器 | 1 套 | 系统 + Chromium |
| 电源 | Type-C 开关电源 5V/3A | 1 | 借出时打开，归还时关闭 |
| 线材 | Micro-HDMI 线 + 1m 网线 | 1 套 | 屏幕与网络 |
| 散热 | 散热片 | 1 套 | 长时间 kiosk |
| 音频 | USB 麦克风 + USB 小音箱/耳机 | 待选型 | 未选定前用文字输入代替 |

**不采购**：

- 五个实体键（ADR-019 取消）；
- 震动马达（C3 取消）；
- 读卡器 / 身份证核验；
- 蓝牙信标；
- 电池（整机不带电池，Type-C 开关电源供电）；
- 3D 打印外壳（C6 取消）。

---

## 3. 端口与地址

| 服务 | 端口 | 地址 |
| --- | --- | --- |
| 后端 API | 8000 | `http://<笔记本IP>:8000/api/v1` |
| WebSocket（计划） | 8000 | `ws://<笔记本IP>:8000/ws/session/{episode_id}` |
| WebSocket（W1 mock） | 8090 | `ws://<笔记本IP>:8090` |
| 用户端 | 5173 | `http://<笔记本IP>:5173` |
| 家属端 | 5174 | `http://<笔记本IP>:5174` |
| 工作台 | 5175 | `http://<笔记本IP>:5175` |
| 设备端 | 5176 | `http://<笔记本IP>:5176` |

设备画面按 1024×600 横屏设计，在 7 寸屏上按 1:1 或等比缩放显示。

---

## 4. 启动顺序

### 4.1 笔记本（服务器 + 开发机）

```powershell
conda activate medpal312
cd D:\project\medpal

# W1/W2 mock（设备端联调用；平板/Pi 访问时用 --host 0.0.0.0）
python tools/mock_api.py --host 0.0.0.0
python tools/mock_ws.py --host 0.0.0.0

# 设备端模拟器
cd device
npm install
npm run dev
```

设备端：`http://127.0.0.1:5176`。  
kiosk 形态：`http://127.0.0.1:5176/?kiosk=1`，会隐藏联调工具条。

### 4.2 平板 / 树莓派（只做屏幕）

浏览器打开：

```text
http://<笔记本IP>:5176
```

树莓派 kiosk：

```bash
./tools/start-kiosk.sh http://<笔记本IP>:5176
```

Windows 备份机：

```powershell
powershell -ExecutionPolicy Bypass -File tools/start-kiosk.ps1 -Url http://127.0.0.1:5176
```

两个脚本都会自动追加 `?kiosk=1`。

### 4.3 小组成员页面

设备端顶部标签页可嵌入：

- 用户端：`VITE_USER_APP_URL`，默认 `http://127.0.0.1:5173`
- 家属端：`VITE_FAMILY_APP_URL`，默认 `http://127.0.0.1:5174`
- 工作台：`VITE_CONSOLE_URL`，默认 `http://127.0.0.1:5175`

对方开发服务器必须监听 `0.0.0.0`：

```bash
npm run dev -- --host 0.0.0.0
```

设备端按键转发给嵌入页面：

```js
{ type: 'medpal:control', session: 's_001', target: 'primary', action: 'tap' }
```

---

## 5. 网络

| 项 | 方案 |
| --- | --- |
| 现场网络 | 4G 随身 WiFi 或笔记本热点 |
| 不使用 | 医院 WiFi、宿舍网 |
| IP | 笔记本与平板/Pi 同网段；启动前用 `ipconfig` 确认 |
| 端口 | 8000 / 8090 / 5173-5176 需互通 |

如果从平板/Pi 访问，`mock_api.py` / `mock_ws.py` 需要监听局域网：加 `--host 0.0.0.0`，或用 `tools/dev.ps1 -BindHost 0.0.0.0`。mock 没有鉴权，只应在可信热点里开放。

---

## 6. 备份与降级

| 场景 | 动作 |
| --- | --- |
| 平板/Pi 黑屏或触摸失灵 | 3 秒内切备用笔记本，打开同一 URL |
| 笔记本后端崩溃 | 切备用笔记本；或直接用 `demo/v4.html` 离线演示 |
| WS 断开 | 设备端显示“未连接，重连中”，本地仍记录控件事件 |
| 网络断开 | 切笔记本热点；仍不行则用 `demo/v4.html` |
| 电源中断 | Pi 用备用电源，或切笔记本；整机不带电池 |
| 小组成员页面打不开 | 点“新窗口打开”，或直接在对应端口打开 |
| 麦克风/音箱未到 | 用屏内文字输入与预置短语 |

离线兜底：`demo/v4.html` 单文件，双击即可，不依赖后端。

---

## 7. 验收清单

- [ ] `device/` 在 5176 启动，1024×600 横屏；
- [ ] 四个主要控件（primary / sos / spot / mic）可点击，事件日志有记录；
- [ ] `session.hello` 后收到 `session.ready`；
- [ ] `touch.event` 后收到 `turn_result`，字幕与 `primary_label` 正确渲染；
- [ ] 文字输入发送 `text.input` 并收到 `turn_result`；
- [ ] 用户端/家属端/工作台标签能加载或给出明确提示；
- [ ] `tools/start-kiosk.ps1` / `.sh` 能全屏启动、无地址栏；
- [ ] `?kiosk=1` 隐藏联调工具条；
- [ ] Pi 4B 上 Chromium 能打开同一页面（C4 触发时）；
- [ ] 备用机能打开同一 URL；
- [ ] `demo/v4.html` 离线兜底可用；
- [ ] 现场负责人、备用机、电源、支架已确认。

---

## 8. 风险

| 风险 | 处置 |
| --- | --- |
| Pi 采购/到货延迟 | 主演示仍用平板/笔记本，C4 不阻塞 M3/M4 |
| 7 寸屏字太小 | 1024×600 横屏按设备 IA 排；必要时切 10 寸平板 |
| Pi 音频底噪/回声 | 用 USB 麦克风/音箱；未选型前用文字输入 |
| 平板浏览器地址栏露出 | 用屏幕固定 / Fully Kiosk / kiosk 脚本 |
| 小组成员页面跨域 iframe 被拒 | 用“新窗口打开”，或改用链接跳转 |
| 现场网络不稳 | 4G 热点 + 离线 `v4.html` |
