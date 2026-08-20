/**
 * Format API timestamps in the user's local timezone.
 * Naive ISO strings from the API are treated as UTC.
 */
export function formatLocalDateTime(value, options) {
  if (!value) return "";
  const s = String(value).trim();
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(s);
  const normalized = hasTz ? s : `${s}Z`;
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString(undefined, options);
}

export function formatLocalDate(value) {
  return formatLocalDateTime(value, {
    year: "numeric",
    month: "numeric",
    day: "numeric",
  });
}
