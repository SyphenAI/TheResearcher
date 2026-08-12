/**
 * Lightweight word-level diff for side-by-side red/green highlighting.
 * Tokens keep whitespace so layout stays readable.
 */

export function tokenize(text) {
  const src = String(text || "");
  if (!src) return [];
  return src.match(/\S+|\s+/g) || [src];
}

/**
 * LCS-based token diff.
 * @returns {{ type: 'equal' | 'add' | 'del', value: string }[]}
 */
export function diffTokens(oldText, newText) {
  const a = tokenize(oldText);
  const b = tokenize(newText);
  const n = a.length;
  const m = b.length;

  // Cap pathological pairs (very long sections) with a simple fallback.
  if (n * m > 2_500_000) {
    if (oldText === newText) return [{ type: "equal", value: oldText }];
    return [
      { type: "del", value: oldText },
      { type: "add", value: newText },
    ];
  }

  const dp = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      if (a[i] === b[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const parts = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      parts.push({ type: "equal", value: a[i] });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      parts.push({ type: "del", value: a[i] });
      i += 1;
    } else {
      parts.push({ type: "add", value: b[j] });
      j += 1;
    }
  }
  while (i < n) {
    parts.push({ type: "del", value: a[i] });
    i += 1;
  }
  while (j < m) {
    parts.push({ type: "add", value: b[j] });
    j += 1;
  }
  return mergeAdjacent(parts);
}

function mergeAdjacent(parts) {
  if (!parts.length) return parts;
  const out = [{ ...parts[0] }];
  for (let k = 1; k < parts.length; k += 1) {
    const prev = out[out.length - 1];
    const cur = parts[k];
    if (prev.type === cur.type) prev.value += cur.value;
    else out.push({ ...cur });
  }
  return out;
}

/** Parts visible on the original (left) pane. */
export function originalParts(parts) {
  return parts.filter((p) => p.type === "equal" || p.type === "del");
}

/** Parts visible on the proposed (right) pane. */
export function proposedParts(parts) {
  return parts.filter((p) => p.type === "equal" || p.type === "add");
}

export function diffStats(parts) {
  let added = 0;
  let removed = 0;
  let equal = 0;
  for (const p of parts) {
    const words = (p.value.match(/\S+/g) || []).length;
    if (p.type === "add") added += words;
    else if (p.type === "del") removed += words;
    else equal += words;
  }
  return { added, removed, equal };
}
