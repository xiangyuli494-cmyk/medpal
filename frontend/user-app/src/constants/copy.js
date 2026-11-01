/**
 * 面向用户的通道与升级文案。
 *
 * 红线：这里的每一句都会被 tools/check_guard_words.py 扫描；
 * tests/copy.test.js 里还有一条同样的断言，改文案时两边一起过。
 */

export const ACCESSIBILITY_MODES = [
  { key: 'elder', label: '老人大字', hint: '默认通道，字号可再放大' },
  { key: 'standard', label: '标准', hint: '常规字号与操作' },
  { key: 'hearing', label: '听障', hint: '文字优先，不出声' },
  { key: 'vision', label: '视障', hint: '语音为主，等 T5 接音频' },
];

export const ESCALATION_COPY = {
  none: '',
  ask_again: '我没听清，请您再说一遍。',
  call_staff: '已帮您叫服务台，请原地稍等。',
  call_family: '正在联系您的家人。',
  sos: '已为您呼叫帮助，请原地别动。',
};

export const ESCALATION_LEVELS = ['none', 'ask_again', 'call_staff', 'call_family', 'sos'];

export const CONNECTION_LABELS = {
  idle: '未连接',
  connecting: '正在连接',
  open: '已连接',
  ready: '已连接',
  closed: '连接断开',
  error: '连接异常',
  mock: '演示模式',
};

/** 演示环境的说明文案，统一挂在这里 */
export const DISCLAIMERS = {
  demo: '演示环境：数据为自建样例，不代表真实就诊信息。',
  triage: '分诊仅作就诊参考，不能替代医生诊断。',
  family: '家属可见范围由您本人授权，撤销后即时不可见。',
};