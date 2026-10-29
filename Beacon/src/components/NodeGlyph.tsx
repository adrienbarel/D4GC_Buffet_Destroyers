import { memo } from 'react';
import { COLORS, NODE_BY_ID, NODE_SIZE, type NodeType } from '../data/network';
import type { NodeStatus } from '../sim/engine';
import { hexPoints } from '../sim/geometry';

interface Props {
  id: string;
  status: NodeStatus;
  hovered: boolean;
  index: number;
  onClick: (id: string, e: React.MouseEvent) => void;
  onHover: (id: string | null) => void;
}

function InnerMark({ type }: { type: NodeType }) {
  switch (type) {
    case 'hub':
      return (
        <g fill="none" stroke="#fff" strokeLinecap="round">
          <circle r={3.6} fill="#fff" stroke="none" />
          <path d="M -8 -6 A 10 10 0 0 0 -8 6 M 8 -6 A 10 10 0 0 1 8 6" strokeWidth={2} />
        </g>
      );
    case 'gateway':
      return (
        <g fill="none" stroke="#fff" strokeWidth={1.7}>
          <circle r={8.5} />
          <ellipse rx={3.6} ry={8.5} />
          <line x1={-8.5} x2={8.5} />
        </g>
      );
    case 'database':
      return (
        <g fill="none" stroke="#fff" strokeWidth={1.6}>
          <ellipse cy={-5} rx={6.5} ry={2.4} />
          <path d="M -6.5 -5 V 5 A 6.5 2.4 0 0 0 6.5 5 V -5 M -6.5 0 A 6.5 2.4 0 0 0 6.5 0" />
        </g>
      );
    case 'relay':
      return <circle r={2.6} fill="#fff" />;
    default:
      return null;
  }
}

export const NodeGlyph = memo(function NodeGlyph({ id, status, hovered, index, onClick, onHover }: Props) {
  const node = NODE_BY_ID[id];
  const r = NODE_SIZE[node.type];
  const off = status !== 'online';
  const color = off ? COLORS.offline : COLORS[node.type];
  const isDot = node.type === 'partner';
  const big = node.type === 'hub' || node.type === 'gateway';
  const delay = `${-(index * 0.37) % 3.2}s`;

  return (
    <g
      className={`node ${off ? 'is-off' : ''}`}
      transform={`translate(${node.x} ${node.y})`}
      onClick={(e) => onClick(id, e)}
      onMouseEnter={() => onHover(id)}
      onMouseLeave={() => onHover(null)}
    >
      {/* generous hit area */}
      <circle r={Math.max(r + 8, 16)} fill="transparent" />

      {!off &&
        (isDot ? (
          <circle className="halo" r={r * 2.2} fill={color} style={{ animationDelay: delay }} />
        ) : (
          <polygon className="halo" points={hexPoints(0, 0, r * 1.42)} fill={color} style={{ animationDelay: delay }} />
        ))}

      {hovered &&
        (isDot ? (
          <circle r={r + 5} fill="none" stroke={color} strokeWidth={1.4} />
        ) : (
          <polygon points={hexPoints(0, 0, r + 6)} fill="none" stroke={color} strokeWidth={1.4} />
        ))}

      {isDot ? (
        <circle r={r} fill={color} filter={off ? undefined : `url(#glow-${node.type})`} />
      ) : (
        <>
          <polygon points={hexPoints(0, 0, r)} fill={color} filter={off ? undefined : `url(#glow-${node.type})`} />
          <polygon points={hexPoints(0, 0, r * 0.66)} fill="none" stroke="#fff" strokeOpacity={0.45} strokeWidth={1.2} />
          {!off && <InnerMark type={node.type} />}
        </>
      )}

      {off && (
        <g stroke={COLORS.offlineX} strokeWidth={isDot ? 2 : 2.6} strokeLinecap="round">
          <line x1={-r * 0.55 - 2} y1={-r * 0.55 - 2} x2={r * 0.55 + 2} y2={r * 0.55 + 2} />
          <line x1={r * 0.55 + 2} y1={-r * 0.55 - 2} x2={-r * 0.55 - 2} y2={r * 0.55 + 2} />
        </g>
      )}

      {!isDot && (
        <g className="node-label" textAnchor="middle">
          <text y={r + (big ? 22 : 18)} className={`label-name ${big ? 'big' : ''}`} fill={off ? COLORS.muted : COLORS.ink}>
            {node.label}
          </text>
          {node.sublabel && (
            <text y={r + (big ? 38 : 32)} className="label-sub">
              {off ? (status === 'jammed' ? 'Jammed' : 'Offline') : node.sublabel}
            </text>
          )}
        </g>
      )}
    </g>
  );
});
