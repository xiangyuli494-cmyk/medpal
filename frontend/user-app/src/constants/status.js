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
 * 节点在 11 节点线上的 1-based 序号；未知节点返回 null。
 * flow.stepIndex 与对外 9 步序号是两套编号，不能混用。
 */
export function toWireIndex(step) {
  const position = STATUS_ORDER.indexOf(step);
  return position >= 0 ? position + 1 : null;
}

/**
 * 把服务端 flow 换算出对外步序。
 *
 * 前 8 个节点以 step 为准推算（step_index 只给未知节点兜底）：
 * step 是枚举校验过的语义字段，两者万一不一致，序号应跟着 step 走，
 * 否则会出现「第 9 步 · 抵达确认」这种序号和标签打架的界面。
 *
 * @param {{step?: string, step_index?: number, total?: number}} flow
 * @returns {{index: number, total: number, label: string, done: boolean}}
 */
export function toPublicStep(flow) {
  const step = flow?.step;

  if (step === 'HOME') {
    return { index: PUBLIC_TOTAL, total: PUBLIC_TOTAL, label: '已完成', done: true };
  }

  if (MERGED_INTO_LAST.has(step)) {
    // 缴费取药与看报告共用第 9 步，展示名也必须是同一个，
    // 否则进度条会从「缴费取药」跳到「看报告」，和下面的步骤列表对不上。
    return {
      index: PUBLIC_TOTAL,
      total: PUBLIC_TOTAL,
      label: PUBLIC_STEPS[PUBLIC_TOTAL - 1].label,
      done: false,
    };
  }

  const wireIndex = toWireIndex(step);
  if (wireIndex !== null) {
    return {
      index: wireIndex,
      total: PUBLIC_TOTAL,
      label: statusLabel(step),
      done: false,
    };
  }

  // 未知节点（如兜底子状态不在 11 节点枚举里）：按 step_index 兜底，越界夹到 1–9
  const rawIndex = Number(flow?.step_index);
  const fallback = Number.isFinite(rawIndex) && rawIndex >= 1 ? Math.trunc(rawIndex) : 1;
  return {
    index: Math.min(Math.max(fallback, 1), PUBLIC_TOTAL),
    total: PUBLIC_TOTAL,
    label: '陪诊中',
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