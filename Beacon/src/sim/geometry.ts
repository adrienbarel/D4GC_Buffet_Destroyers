/** Pointy-top hexagon points around (cx, cy) */
export function hexPoints(cx: number, cy: number, r: number) {
  const pts: string[] = [];
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 180) * (60 * i - 90);
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return pts.join(' ');
}

/** Position and heading at fraction t (0–1) along a polyline */
export function pointAlong(points: [number, number][], t: number) {
  const segs: number[] = [];
  let total = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const len = Math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]);
    segs.push(len);
    total += len;
  }
  let d = Math.min(Math.max(t, 0), 1) * total;
  for (let i = 0; i < segs.length; i++) {
    if (d <= segs[i] || i === segs.length - 1) {
      const f = segs[i] === 0 ? 0 : Math.min(d / segs[i], 1);
      const [x1, y1] = points[i];
      const [x2, y2] = points[i + 1];
      return { x: x1 + (x2 - x1) * f, y: y1 + (y2 - y1) * f, dx: x2 - x1 };
    }
    d -= segs[i];
  }
  const [x, y] = points[points.length - 1];
  return { x, y, dx: -1 };
}

export const formatBytes = (n: number) => {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
};

export const formatClock = (t: number) => {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`;
};
