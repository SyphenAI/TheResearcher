/** Month-level scholar date helpers (YYYY-MM). */

export function toMonthValue(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

export function addMonths(date, delta) {
  const d = new Date(date.getFullYear(), date.getMonth(), 1);
  d.setMonth(d.getMonth() + delta);
  return d;
}

/** Presets -> { from, to } as YYYY-MM or empty strings. */
export function scholarDatePreset(preset) {
  const now = new Date();
  const to = toMonthValue(now);
  if (preset === "clear") return { from: "", to: "" };
  if (preset === "6m") return { from: toMonthValue(addMonths(now, -5)), to };
  if (preset === "ytd") return { from: `${now.getFullYear()}-01`, to };
  if (preset === "1y") return { from: toMonthValue(addMonths(now, -11)), to };
  if (preset === "2y") return { from: toMonthValue(addMonths(now, -23)), to };
  if (preset === "3y") return { from: toMonthValue(addMonths(now, -35)), to };
  if (preset === "5y") return { from: toMonthValue(addMonths(now, -59)), to };
  if (preset === "10y") return { from: toMonthValue(addMonths(now, -119)), to };
  return { from: "", to: "" };
}

/** Append date_from / date_to (YYYY or YYYY-MM) onto URLSearchParams. */
export function appendScholarDateParams(params, dateFrom, dateTo) {
  const yf = String(dateFrom || "").trim();
  const yt = String(dateTo || "").trim();
  if (/^\d{4}(-\d{2})?(-\d{2})?$/.test(yf)) params.set("date_from", yf);
  if (/^\d{4}(-\d{2})?(-\d{2})?$/.test(yt)) params.set("date_to", yt);
  return params;
}
