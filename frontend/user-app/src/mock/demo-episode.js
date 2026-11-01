/**
 * 演示陪诊单：与 tools/mock_api.py 的 /episodes/ep_001 同形。
 *
 * 只用于 VITE_DEMO_MODE=1；字段名与 docs/specs/domain-model.md §3 对齐。
 * 数据为自建样例，不含任何真实患者信息。
 */

export const DEMO_EPISODE = {
  id: 'ep_001',
  status: 'ARRIVED',
  staff_contact: 'stf_01',
  patient: {
    salutation: '王阿姨',
    age_range: '65–70',
  },
  timeline: [
    { at: '2026-10-27T08:30:00+08:00', type: 'text', source: 'system', text: '服务台登记完成，设备已绑定' },
  ],
  tasks: [
    { id: 't_001', title: '抽血（空腹）', type: 'exam', status: 'pending', owner: 'system' },
    { id: 't_002', title: 'B 超检查', type: 'exam', status: 'pending', owner: 'system' },
    { id: 't_003', title: '缴费取药', type: 'payment', status: 'pending', owner: 'system' },
  ],
};

/** 返回一份深拷贝，避免页面改到常量 */
export function createDemoEpisode(episodeId = 'ep_001') {
  return {
    ...structuredCloneSafe(DEMO_EPISODE),
    id: episodeId || DEMO_EPISODE.id,
  };
}

function structuredCloneSafe(value) {
  if (typeof structuredClone === 'function') return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}