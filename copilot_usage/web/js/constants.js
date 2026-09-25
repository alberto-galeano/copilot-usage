import { addDays } from "./format.js";

export const TIERS = ["high", "medium", "low"];
export const TIER_LABEL = { high: "High", medium: "Medium", low: "Low" };
export const MEASURE_OPTIONS = [["aic", "Spend"], ["calls", "Calls"], ["prompts", "Prompts"]];
export const MEASURE_TEXT = {
  aic: { unit: "AIC", noun: "spend", what: "AI credits" },
  calls: { unit: "calls", noun: "calls", what: "Model calls" },
  prompts: { unit: "prompts", noun: "prompts", what: "Prompts you sent" },
};
export const MIX_SLICES = 6;
export const RANGES = [
  { id: "today", label: "Today", start: now => now },
  { id: "7d", label: "Last 7 days", start: now => addDays(now, -6) },
  { id: "30d", label: "Last 30 days", start: now => addDays(now, -29) },
  { id: "month", label: "This month", start: now => new Date(now.getFullYear(), now.getMonth(), 1) },
  { id: "all", label: "All time", start: () => null },
];
export const MEASURES = ["aic", "calls", "prompts", "in", "out", "cache", "cache_write", "reasoning", "ms", "out_timed",
  "premium", "c_input", "c_cache_read", "c_cache_write", "c_output", "saved", "itl", "itl_n", "filtered"];
export const TOKEN_KINDS = [["c_cache_read", "Cache reads"], ["c_cache_write", "Cache writes"], ["c_output", "Output"], ["c_input", "Fresh input"]];
export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const SESSIONS_SHOWN = 12;
export const PLOT = { top: 8, right: 8, bottom: 24, left: 44 };
