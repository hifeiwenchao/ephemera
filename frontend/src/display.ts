import type { TtlSeconds } from "./types";
export const ttlOptions: { value: TtlSeconds; label: string }[] = [
  { value: null, label: "关闭" },
  { value: 3600, label: "1 小时" },
  { value: 86400, label: "1 天" },
  { value: 604800, label: "7 天" },
  { value: 2592000, label: "30 天" },
];
export const ttlLabel = (value: TtlSeconds) =>
  ttlOptions.find((option) => option.value === value)?.label || "关闭";
export const timeLabel = (date: string) =>
  new Date(date).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
export function dateLabel(date: string) {
  const value = new Date(date);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (value.toDateString() === today.toDateString()) return "今天";
  if (value.toDateString() === yesterday.toDateString()) return "昨天";
  return value.toLocaleDateString("zh-CN", {
    month: "long",
    day: "numeric",
    ...(value.getFullYear() !== today.getFullYear() ? { year: "numeric" } : {}),
  });
}
export function previewTime(date: string) {
  return new Date(date).toDateString() === new Date().toDateString()
    ? timeLabel(date)
    : dateLabel(date);
}
export function expirationLabel(date: string) {
  const minutes = Math.ceil((Date.parse(date) - Date.now()) / 60000);
  if (minutes < 60) return `${Math.max(1, minutes)}分钟`;
  if (minutes < 1440) return `${Math.ceil(minutes / 60)}小时`;
  return `${Math.ceil(minutes / 1440)}天`;
}
