import { LINKS, NODE_BY_ID } from '../data/network';

export const distance = (a: string, b: string) => {
  const p = NODE_BY_ID[a];
  const q = NODE_BY_ID[b];
  return Math.hypot(p.x - q.x, p.y - q.y);
};

const ADJ: Record<string, string[]> = {};
for (const [a, b] of LINKS) {
  (ADJ[a] ??= []).push(b);
  (ADJ[b] ??= []).push(a);
}

export const neighbours = (id: string) => ADJ[id] ?? [];

// Longer and weaker links cost more; the flat per-hop term favours fewer hops.
const linkCost = (a: string, b: string) =>
  distance(a, b) / ((NODE_BY_ID[a].linkQuality + NODE_BY_ID[b].linkQuality) / 2) + 40;

/** Dijkstra over nodes that are not blocked. Returns [from, …, to] or null. */
export function shortestPath(from: string, to: string, blocked: Set<string>): string[] | null {
  if (blocked.has(from) || blocked.has(to)) return null;
  if (from === to) return [from];

  const dist = new Map<string, number>([[from, 0]]);
  const prev = new Map<string, string>();
  const done = new Set<string>();

  for (;;) {
    let u: string | null = null;
    let best = Infinity;
    for (const [n, d] of dist) {
      if (!done.has(n) && d < best) {
        best = d;
        u = n;
      }
    }
    if (u === null) return null;
    if (u === to) break;
    done.add(u);
    for (const v of neighbours(u)) {
      if (blocked.has(v) || done.has(v)) continue;
      const nd = best + linkCost(u, v);
      if (nd < (dist.get(v) ?? Infinity)) {
        dist.set(v, nd);
        prev.set(v, u);
      }
    }
  }

  const path = [to];
  while (path[0] !== from) path.unshift(prev.get(path[0])!);
  return path;
}
