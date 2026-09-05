/** Chinese display labels for machine enum values. Raw values remain visible for auditability. */

export const identityStatusLabels: Record<string, string> = {
  singleton: "独立人物",
  linked: "已关联",
  unresolved: "身份未决",
};

export const labelKindLabels: Record<string, string> = {
  proper_name: "姓名",
  title: "称号",
  descriptive_label: "描述性称呼",
};

export const labelStabilityLabels: Record<string, string> = {
  stable: "稳定",
  contextual: "随文变化",
};

export const canonicalLabelStatusLabels: Record<string, string> = {
  confirmed_name_like: "确认名称",
  provisional_description: "暂定描述",
};

export const exclusionReasonLabels: Record<string, string> = {
  future_observation: "未来观察（当前位置之后才出现）",
  different_life_stage: "不同生命阶段",
  different_form: "不同形态",
  different_life: "不同生命阶段",
  removed: "已被明确移除",
  replaced: "已被替换",
  expired_momentary: "瞬时状态已过期",
  uncertain_continuity: "连续性不确定",
  identity_unresolved: "身份未决",
  selector_no_match: "选择器无匹配",
  no_state_segment: "无匹配状态区间",
};

export const applicabilityStatusLabels: Record<string, string> = {
  active: "当前有效",
  provisional: "暂定",
  excluded: "不适用",
};

export const persistenceLabels: Record<string, string> = {
  persistent_until_changed: "持续至改变",
  scene: "场景内",
  momentary: "瞬时",
  unknown: "持续性未知",
};

export const changeLabels: Record<string, string> = {
  enter: "进入",
  exit: "退出",
  change: "变化",
};

export const dimensionLabels: Record<string, string> = {
  life: "生命阶段",
  form: "形态",
  scene: "场景",
  appearance: "外貌",
};

export const traitKindLabels: Record<string, string> = {
  stable_traits: "稳定特质",
  variant_traits: "变化特质",
  scene_overrides: "场景覆盖",
};

export function label(map: Record<string, string>, value: string | null | undefined): string {
  if (!value) return "—";
  return map[value] ?? value;
}
