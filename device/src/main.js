import './style.css';
import { MEMBER_PAGES } from './member-pages.js';

const params = new URLSearchParams(location.search);
const KIOSK = params.get('kiosk') === '1';
const PROTOCOL_VERSION = '0.1';
const DEVICE_ID = params.get('device') || import.meta.env.VITE_DEVICE_ID || 'dev_001';
const EPISODE_ID = params.get('episode') || import.meta.env.VITE_EPISODE_ID || 'ep_001';
const ACCESSIBILITY_MODE =
  params.get('mode') || import.meta.env.VITE_ACCESSIBILITY_MODE || 'elder';
const requestedPage = params.get('page');

let sessionId = params.get('session') || import.meta.env.VITE_SESSION_ID || 's_001';
let currentPage = MEMBER_PAGES.some((page) => page.id === requestedPage)
  ? requestedPage
  : 'device';
if (KIOSK) currentPage = 'device';

let ws = null;
let reconnectTimer = 0;
let reconnectDelay = 1000;
let heartbeatTimer = 0;
let lastPong = Date.now();
let lastTurn = 0;
let primaryLabel = '主操作';

const STATE_LABELS = {
  ARRIVED: '抵达确认',
  BRIEFING: '行程播报',
  REGISTER: '取号挂号',
  WAITING: '候诊盯号',
  CONSULT: '进诊室',
  RECAP: '复述校验',
  PLAN: '检查规划',
  NAVIGATE: '执行与导航',
  PAY_AND_PICKUP: '缴费取药',
  REPORT: '看报告',
  HOME: '小结回家',
};

const ESCALATION_TEXT = {
  ask_again: '我没听清，您再说一遍。',
  call_staff: '已帮您叫服务台，请稍等。',
  call_family: '正在联系您的家人。',
  sos: '已为您呼叫帮助。',
};

const DEBUG_KEYS = {
  GREEN_DOWN: 'primary',
  GREEN_UP: 'back',
  RED_LONG: 'sos',
  SIDE: 'spot',
};

const els = {
  tabs: document.querySelector('#tabs'),
  wsDot: document.querySelector('#wsDot'),
  wsText: document.querySelector('#wsText'),
  clock: document.querySelector('#clock'),
  netState: document.querySelector('#netState'),
  screenTitle: document.querySelector('#screenTitle'),
  caption: document.querySelector('#caption'),
  flow: document.querySelector('#flow'),
  escalation: document.querySelector('#escalation'),
  options: document.querySelector('#options'),
  primary: document.querySelector('#primary'),
  sos: document.querySelector('#sos'),
  spot: document.querySelector('#spot'),
  mic: document.querySelector('#mic'),
  textForm: document.querySelector('#textForm'),
  textInput: document.querySelector('#textInput'),
  deviceStage: document.querySelector('#deviceStage'),
  memberStage: document.querySelector('#memberStage'),
  memberFrame: document.querySelector('#memberFrame'),
  memberUrl: document.querySelector('#memberUrl'),
  openMember: document.querySelector('#openMember'),
  eventLog: document.querySelector('#eventLog'),
  devbar: document.querySelector('.devbar'),
  devkeys: document.querySelector('.devkeys'),
};

function resolveLocalUrl(rawUrl) {
  if (!rawUrl) return rawUrl;
  try {
    const url = new URL(rawUrl);
    if (
      (url.hostname === '127.0.0.1' || url.hostname === 'localhost') &&
      location.hostname &&
      location.hostname !== 'localhost' &&
      location.hostname !== '127.0.0.1'
    ) {
      url.hostname = location.hostname;
    }
    return url.toString().replace(/\/$/, '');
  } catch {
    return rawUrl;
  }
}

function resolveWsBase() {
  const configured = import.meta.env.VITE_WS_BASE;
  if (!configured) {
    return `ws://${location.hostname || '127.0.0.1'}:8090`;
  }
  try {
    const url = new URL(configured);
    if (
      (url.hostname === '127.0.0.1' || url.hostname === 'localhost') &&
      location.hostname &&
      location.hostname !== 'localhost' &&
      location.hostname !== '127.0.0.1'
    ) {
      url.hostname = location.hostname;
    }
    return url.toString().replace(/\/$/, '');
  } catch {
    return configured;
  }
}

const WS_BASE = resolveWsBase();

function setStatus(text, tone = 'pending') {
  els.wsText.textContent = text;
  els.wsDot.dataset.tone = tone;
}

function logEvent(text, tone = '') {
  const item = document.createElement('div');
  const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  item.textContent = `${time}  ${text}`;
  if (tone) item.dataset.tone = tone;
  els.eventLog.prepend(item);
  while (els.eventLog.children.length > 6) {
    els.eventLog.lastElementChild.remove();
  }
}

function flash(element) {
  if (!element) return;
  element.classList.add('is-active');
  window.setTimeout(() => element.classList.remove('is-active'), 100);
}

function sendJson(payload) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
    return true;
  }
  logEvent(`WS 未连接，未发送 ${payload.type}`, 'warn');
  return false;
}

function sendHello() {
  sendJson({
    type: 'session.hello',
    protocol_version: PROTOCOL_VERSION,
    device_id: DEVICE_ID,
    episode_id: EPISODE_ID,
    client: 'device',
    accessibility_mode: ACCESSIBILITY_MODE,
  });
}

function postToMember(payload) {
  const page = MEMBER_PAGES.find((item) => item.id === currentPage);
  if (!page?.url || els.memberStage.hidden) return;
  try {
    const targetOrigin = new URL(resolveLocalUrl(page.url)).origin;
    els.memberFrame.contentWindow?.postMessage(payload, targetOrigin);
  } catch {
    // 对方页面地址不合法时忽略
  }
}

function sendControl(target, action = 'tap') {
  logEvent(`control ${target} / ${action}`);
  const button = { primary: els.primary, sos: els.sos, spot: els.spot }[target];
  flash(button);
  sendJson({ type: 'touch.event', session: sessionId, target, action });
  postToMember({
    type: 'medpal:control',
    session: sessionId,
    target,
    action,
  });
  window.dispatchEvent(
    new CustomEvent('medpal:control', {
      detail: { session: sessionId, target, action },
    }),
  );
}

function sendText(text) {
  const value = (text || '').trim();
  if (!value) return;
  logEvent(`text.input：${value}`);
  sendJson({ type: 'text.input', session: sessionId, text: value });
  postToMember({ type: 'medpal:text', session: sessionId, text: value });
}

function localBack() {
  logEvent('本地返回：只退一屏，不产生上行消息');
  setEscalation('none');
}

function renderOptions(slots) {
  els.options.replaceChildren();
  if (!slots) {
    els.options.hidden = true;
    return;
  }

  const items = Array.isArray(slots)
    ? slots
    : Object.entries(slots).map(([id, label]) => ({ id, label }));

  for (const item of items) {
    const id = item?.id ?? item?.slot_id ?? item?.key;
    if (id == null) continue;
    const label = item?.label ?? item?.text ?? String(id);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'option';
    button.textContent = String(label);
    button.addEventListener('click', () => sendControl(`option:${id}`));
    els.options.append(button);
  }
  els.options.hidden = els.options.children.length === 0;
}

function setEscalation(level) {
  if (!level || level === 'none') {
    els.escalation.hidden = true;
    els.escalation.textContent = '';
    els.escalation.dataset.level = '';
    return;
  }
  els.escalation.textContent = ESCALATION_TEXT[level] || '需要帮助，请稍等。';
  els.escalation.dataset.level = level;
  els.escalation.hidden = false;
}

function setState(state) {
  if (!state) return;
  els.screenTitle.textContent = STATE_LABELS[state] || state;
}

function handleTurn(data) {
  const caption = data.caption?.text || data.text || '（服务端没有下发字幕）';
  els.caption.textContent = caption;

  const label = data.primary_label || data.dialog?.primary_label;
  if (label) {
    primaryLabel = String(label);
    els.primary.textContent = primaryLabel;
  }

  if (data.flow) {
    const step = data.flow.step || '';
    setState(step);
    const index = data.flow.step_index ?? '?';
    const total = data.flow.total ?? '?';
    const why = data.flow.why || '';
    els.flow.textContent = `${STATE_LABELS[step] || step || '未知节点'} · 第 ${index}/${total} 步${why ? ` · ${why}` : ''}`;
  }

  renderOptions(data.slots || data.dialog?.slots);
  setEscalation(data.escalation?.level || 'none');

  lastTurn = Number(data.turn || lastTurn);
  if (lastTurn) {
    sendJson({ type: 'ack', session: sessionId, turn: lastTurn });
  }
  logEvent(`turn_result：${caption}`);
}

function handleMessage(raw) {
  if (typeof raw !== 'string') return;

  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    logEvent('收到非 JSON 消息', 'warn');
    return;
  }

  switch (data.type) {
    case 'session.ready':
      sessionId = data.session_id || sessionId;
      setState(data.state);
      logEvent(`会话就绪：${data.state || 'unknown'}，session=${sessionId}`);
      break;

    case 'turn_result':
      handleTurn(data);
      break;

    case 'dialog.reply':
      els.caption.textContent = data.text || els.caption.textContent;
      if (data.primary_label) {
        primaryLabel = String(data.primary_label);
        els.primary.textContent = primaryLabel;
      }
      renderOptions(data.slots);
      logEvent('收到 dialog.reply');
      break;

    case 'caption.update':
      els.caption.textContent = data.text || els.caption.textContent;
      break;

    case 'asr.final':
      els.caption.textContent = data.text || els.caption.textContent;
      logEvent(`ASR：${data.text || ''}（${data.confidence ?? '?'}）`);
      break;

    case 'state.transition':
      setState(data.to);
      els.flow.textContent = `${STATE_LABELS[data.from] || data.from || '?'} → ${STATE_LABELS[data.to] || data.to || '?'}`;
      logEvent(`状态跃迁：${data.from} → ${data.to}`);
      break;

    case 'escalation.notice': {
      const level =
        data.level ||
        (data.target === 'both'
          ? 'sos'
          : data.target === 'family'
            ? 'call_family'
            : 'call_staff');
      setEscalation(level);
      logEvent(`升级：${level}`, 'warn');
      break;
    }

    case 'guard.blocked':
      logEvent(`红线拦截：${data.rule_id || data.action || 'unknown'}`, 'warn');
      break;

    case 'task.updated':
      logEvent(`任务 ${data.task_id || '?'} → ${data.state || '?'}`);
      break;

    case 'pong':
      lastPong = Date.now();
      break;

    case 'error':
      handleError(data);
      break;

    default:
      logEvent(`收到 ${data.type || '未知消息'}`);
  }
}

function handleError(data) {
  const code = String(data.code || '');
  logEvent(`服务端错误：${code || data.message || 'unknown'}`, 'bad');
  if (code.includes('ASR')) {
    els.caption.textContent = '刚才没听清，您再说一遍。';
  } else if (code.includes('SESSION_EXPIRED')) {
    els.caption.textContent = '我们重新开始，之前的记录还在。';
  } else if (code.includes('TTS')) {
    els.caption.textContent = '没有声音，您看屏幕上的字。';
  } else {
    els.caption.textContent = '网络不太好，正在重新连接。';
  }
}

function startHeartbeat() {
  window.clearInterval(heartbeatTimer);
  lastPong = Date.now();
  heartbeatTimer = window.setInterval(() => {
    if (ws?.readyState !== WebSocket.OPEN) return;
    if (Date.now() - lastPong > 45000) {
      logEvent('心跳超时，重连', 'warn');
      ws.close();
      return;
    }
    sendJson({ type: 'ping' });
  }, 15000);
}

function scheduleReconnect() {
  window.clearTimeout(reconnectTimer);
  reconnectTimer = window.setTimeout(connectWs, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, 30000);
}

function connectWs() {
  window.clearTimeout(reconnectTimer);
  setStatus('连接中…', 'pending');

  try {
    ws = new WebSocket(WS_BASE);
  } catch {
    setStatus('连接失败', 'bad');
    scheduleReconnect();
    return;
  }

  ws.addEventListener('open', () => {
    reconnectDelay = 1000;
    setStatus('已连接', 'ok');
    logEvent(`WS 已连接 ${WS_BASE}`);
    sendHello();
    startHeartbeat();
  });
  ws.addEventListener('message', (event) => handleMessage(event.data));
  ws.addEventListener('close', () => {
    window.clearInterval(heartbeatTimer);
    setStatus('未连接，重连中', 'bad');
    scheduleReconnect();
  });
  ws.addEventListener('error', () => setStatus('连接失败', 'bad'));
}

function renderTabs() {
  for (const page of MEMBER_PAGES) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'tab';
    button.dataset.page = page.id;
    button.textContent = page.name;
    button.addEventListener('click', () => selectPage(page.id));
    els.tabs.append(button);
  }
}

function selectPage(pageId) {
  if (KIOSK) pageId = 'device';
  const page = MEMBER_PAGES.find((item) => item.id === pageId) ?? MEMBER_PAGES[0];
  currentPage = page.id;

  for (const tab of els.tabs.querySelectorAll('.tab')) {
    tab.classList.toggle('is-active', tab.dataset.page === page.id);
  }

  const isLocal = page.kind === 'local';
  els.deviceStage.hidden = !isLocal;
  els.memberStage.hidden = isLocal;

  if (isLocal) {
    els.memberFrame.removeAttribute('src');
    delete els.memberFrame.dataset.url;
    return;
  }

  const pageUrl = resolveLocalUrl(page.url);
  els.memberUrl.textContent = pageUrl;
  els.openMember.href = pageUrl;
  if (els.memberFrame.dataset.url !== pageUrl) {
    els.memberFrame.dataset.url = pageUrl;
    els.memberFrame.src = pageUrl;
  }
  logEvent(`加载联调页面：${page.name} ${pageUrl}`);
}

function fitDevice() {
  const chrome = KIOSK
    ? 16
    : els.devbar.offsetHeight + els.devkeys.offsetHeight + 16;
  const scale = Math.min(
    (window.innerWidth - 16) / 1024,
    (window.innerHeight - chrome) / 600,
    1.5,
  );
  document.documentElement.style.setProperty(
    '--device-scale',
    String(Math.max(scale, 0.25)),
  );
}

function updateClock() {
  els.clock.textContent = new Date().toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
  });
}

function updateNetState() {
  els.netState.textContent = navigator.onLine ? '联网' : '离线';
}

window.addEventListener('resize', fitDevice);
window.addEventListener('online', updateNetState);
window.addEventListener('offline', updateNetState);

els.primary.addEventListener('click', () => sendControl('primary'));
els.sos.addEventListener('click', () => sendControl('sos'));
els.spot.addEventListener('click', () => sendControl('spot'));
els.mic.addEventListener('click', () => {
  els.textInput.focus();
  logEvent('麦克风未接入，使用文字输入（ADR-019）');
});
els.textForm.addEventListener('submit', (event) => {
  event.preventDefault();
  sendText(els.textInput.value);
  els.textInput.value = '';
  els.textInput.focus();
});

for (const button of document.querySelectorAll('[data-local]')) {
  button.addEventListener('click', () => {
    const action = button.dataset.local;
    if (action === 'back') {
      localBack();
    } else {
      logEvent(`${action === 'menu' ? '主菜单' : '设置'}：本地占位，不上行`);
    }
  });
}

for (const button of document.querySelectorAll('[data-debug]')) {
  button.addEventListener('click', () => {
    const target = DEBUG_KEYS[button.dataset.debug];
    if (target === 'back') {
      localBack();
    } else if (target) {
      sendControl(target);
    }
  });
}

document.body.classList.toggle('kiosk', KIOSK);
window.medpalDevice = {
  sendControl,
  sendText,
  get session() {
    return sessionId;
  },
  get episode() {
    return EPISODE_ID;
  },
};

renderTabs();
selectPage(currentPage);
updateClock();
setInterval(updateClock, 1000);
updateNetState();
logEvent(`设备模拟器启动，episode=${EPISODE_ID}，session=${sessionId}`);
connectWs();
fitDevice();
