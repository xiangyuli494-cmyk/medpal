/**
 * 11 个状态节点与对外 9 步的换算。
 *
 * 来源：docs/specs/domain-model.md §2.1 – §2.3、docs/api/ws-protocol.md §4.1。
 * 换算只在展示层做，不上 wire；协议的 flow.total 恒为 11。
 */

/** 11 节点，顺序与状态机一致 */
export const STATUS_ORDER = [
  'ARRIVED',
  'BRIEFING',
  'REGISTER',
  'WAITING',
  'IN_ROOM',
  'RECAP',
  'PLAN_EXAMS',
  'NAVIGATE',
  'PAY_AND_PICKUP',
  'REPORT',
  'HOME',
];

/** 节点中文名，界面只读这里 */
export const STATUS_LABELS = {
  ARRIVED: '抵达确认',
  BRIEFING: '行程播报',
  REGISTER: '取号挂号',
  WAITING: '候诊盯号',
  IN_ROOM: '进诊室',
  RECAP: '复述校验',
  PLAN_EXAMS: '检查规划',
  NAVIGATE: '执行与导航',
  PAY_AND_PICKUP: '缴费取药',
  REPORT: '看报告',
  HOME: '小结回家',
};

/** 对外 9 步的标题；第 9 步合并缴费与看报告 */
export const PUBLIC_STEPS = [
  { key: 'ARRIVED', label: '抵达确认' },
  { key: 'BRIEFING', label: '行程播报' },
  { key: 'REGISTER', label: '取号挂号' },
  { key: 'WAITING', label: '候诊盯号' },
  { key: 'IN_ROOM', label: '进诊室' },
  { key: 'RECAP', label: '复述校验' },
  { key: 'PLAN_EXAMS', label: '检查规划' },
  { key: 'NAVIGATE', label: '执行与导航' },
  { key: 'PAY_AND_PICKUP', label: '缴费取药 · 看报告' },
];

/** 对外总步数，固定 9，对应基线 §2 的「对外讲 9 步」 */
export const PUBLIC_TOTAL = PUBLIC_STEPS.length;

/** 9 步合并的两个节点 */
const MERGED_INTO_LAST = new Set(['PAY_AND_PICKUP', 'REPORT']);

export function statusLabel(step) {
  return STATUS_LABELS[step] || '陪诊中';
}

/**
 * 把服务端 flow 换算出对外步序。
 *
 * @param {{step?: string, step_index?: number, total?: number}} flow
 * @returns {{index: number, total: number, label: string, done: boolean}}
 */
export function toPublicStep(flow) {
  const step = flow?.step;
  const rawIndex = Number(flow?.step_index);

  if (step === 'HOME') {
    return { index: PUBLIC_TOTAL, total: PUBLIC_TOTAL, label: '已完成', done: true };
  }

  if (MERGED_INTO_LAST.has(step)) {
    return { index: PUBLIC_TOTAL, total: PUBLIC_TOTAL, label: statusLabel(step), done: false };
  }

  const fallbackIndex = STATUS_ORDER.indexOf(step) + 1;
  const index = Number.isFinite(rawIndex) && rawIndex >= 1 ? rawIndex : fallbackIndex;
  const safeIndex = Math.min(Math.max(index, 1), PUBLIC_TOTAL);

  return {
    index: safeIndex,
    total: PUBLIC_TOTAL,
    label: statusLabel(STATUS_ORDER[safeIndex - 1]),
    done: false,
  };
}

/**
 * 9 步列表在进度页的状态：done / current / upcoming。
 *
 * @param {number} publicIndex 1–9，来自 toPublicStep
 * @param {boolean} done 是否已到最后
 */
export function buildStepList(publicIndex, done = false) {
  return PUBLIC_STEPS.map((item, position) => {
    const index = position + 1;
    let state = 'upcoming';
    if (done || index < publicIndex) state = 'done';
    else if (index === publicIndex) state = done ? 'done' : 'current';
    return { ...item, index, state };
  });
}