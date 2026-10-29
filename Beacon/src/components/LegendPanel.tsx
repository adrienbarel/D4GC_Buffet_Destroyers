import { COLORS } from '../data/network';
import { hexPoints } from '../sim/geometry';
import { LockGlyph } from './icons';

const Hex = ({ color, r = 7, glow = true }: { color: string; r?: number; glow?: boolean }) => (
  <polygon points={hexPoints(11, 11, r)} fill={color} style={glow ? { filter: `drop-shadow(0 0 3px ${color})` } : undefined} />
);

const ITEMS: { label: string; icon: JSX.Element }[] = [
  { label: 'Field Hub', icon: <Hex color={COLORS.hub} r={9} /> },
  { label: 'Relay node', icon: <Hex color={COLORS.relay} r={7} /> },
  { label: 'Partner relay', icon: <circle cx={11} cy={11} r={4} fill={COLORS.partner} style={{ filter: `drop-shadow(0 0 3px ${COLORS.partner})` }} /> },
  { label: 'Gateway', icon: <Hex color={COLORS.gateway} r={8.5} /> },
  { label: 'Database', icon: <Hex color={COLORS.database} r={7.5} /> },
  {
    label: 'Offline node',
    icon: (
      <>
        <Hex color={COLORS.offline} glow={false} />
        <path d="M 7.5 7.5 L 14.5 14.5 M 14.5 7.5 L 7.5 14.5" stroke={COLORS.offlineX} strokeWidth={1.8} strokeLinecap="round" />
      </>
    ),
  },
  { label: 'Active path', icon: <line x1={1} y1={11} x2={21} y2={11} stroke={COLORS.hub} strokeWidth={2.2} className="path-active" /> },
  {
    label: 'Encrypted packet',
    icon: (
      <>
        <circle cx={8} cy={12} r={4} fill={COLORS.request} style={{ filter: `drop-shadow(0 0 3px ${COLORS.request})` }} />
        <LockGlyph x={16.5} y={7} size={7} color={COLORS.request} />
      </>
    ),
  },
];

export function LegendPanel() {
  return (
    <div className="panel legend">
      <div className="brand">
        <svg width={22} height={22} viewBox="0 0 22 22">
          <Hex color={COLORS.hub} r={10} />
          <circle cx={11} cy={11} r={3} fill="#fff" />
        </svg>
        <div>
          <div className="brand-name">Beacon</div>
          <div className="brand-sub">Low-bandwidth relay network</div>
        </div>
      </div>
      <div className="panel-title">Legend</div>
      <ul className="legend-list">
        {ITEMS.map((it) => (
          <li key={it.label}>
            <svg width={22} height={22} viewBox="0 0 22 22" overflow="visible">
              {it.icon}
            </svg>
            <span>{it.label}</span>
          </li>
        ))}
        <li>
          <svg width={22} height={22} viewBox="0 0 22 22">
            <circle cx={8} cy={11} r={4} fill={COLORS.response} style={{ filter: `drop-shadow(0 0 3px ${COLORS.response})` }} />
            <circle cx={17} cy={11} r={3} fill={COLORS.fetch} />
          </svg>
          <span>Response / DB fetch</span>
        </li>
      </ul>
    </div>
  );
}
