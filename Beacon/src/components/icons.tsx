import { COLORS } from '../data/network';

/** Small padlock drawn in SVG units, centred on (x, y) */
export function LockGlyph({ x = 0, y = 0, size = 8, color = COLORS.ink }: { x?: number; y?: number; size?: number; color?: string }) {
  const s = size / 8;
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <path d="M -2.4 -1 V -2.6 A 2.4 2.4 0 0 1 2.4 -2.6 V -1" fill="none" stroke={color} strokeWidth={1.3} />
      <rect x={-3.6} y={-1.2} width={7.2} height={5.4} rx={1.1} fill={color} />
    </g>
  );
}

export function LockIcon({ size = 12, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="-5 -5 10 10" aria-hidden style={{ display: 'inline-block', verticalAlign: '-1px' }}>
      <LockGlyph size={9} color={color} y={0.6} />
    </svg>
  );
}

/** Simple side-view field vehicle, facing right, centred on origin */
export function VehicleGlyph({ color = COLORS.vehicle, accent = COLORS.gateway }: { color?: string; accent?: string }) {
  return (
    <g>
      <rect x={-16} y={-10} width={21} height={12} rx={2} fill={color} />
      <path d="M 5 -6 H 11 L 16 -1 V 2 H 5 Z" fill={color} />
      <path d="M 7 -4.5 H 10.4 L 13.4 -1.4 H 7 Z" fill="#fff" opacity={0.85} />
      <rect x={-13} y={-7} width={15} height={2.6} rx={1} fill={accent} />
      <circle cx={-9} cy={3} r={3.6} fill={color} stroke="#fff" strokeWidth={1.4} />
      <circle cx={10} cy={3} r={3.6} fill={color} stroke="#fff" strokeWidth={1.4} />
    </g>
  );
}
