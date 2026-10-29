import { AnimatePresence } from 'framer-motion';
import { memo, useCallback, useRef, useState } from 'react';
import {
  COLORS,
  DRIVE_ROUTE,
  GATEWAY_ID,
  HUB_ID,
  JAM_RADIUS,
  LINKS,
  NODES,
  NODE_BY_ID,
  NODE_SIZE,
  VIEWBOX,
  ZONES,
} from '../data/network';
import type { Packet, Simulation } from '../sim/engine';
import { pointAlong } from '../sim/geometry';
import { LockGlyph, VehicleGlyph } from './icons';
import { NodeGlyph } from './NodeGlyph';
import { NodeTooltip } from './NodeTooltip';
import { PayloadViewer } from './PayloadViewer';

const GLOWS: Record<string, { color: string; blur: number; opacity: number }> = {
  hub: { color: COLORS.hub, blur: 10, opacity: 0.6 },
  relay: { color: COLORS.relay, blur: 6, opacity: 0.5 },
  partner: { color: COLORS.partner, blur: 4, opacity: 0.55 },
  gateway: { color: COLORS.gateway, blur: 9, opacity: 0.55 },
  database: { color: COLORS.database, blur: 7, opacity: 0.5 },
  'pk-request': { color: COLORS.request, blur: 5, opacity: 0.9 },
  'pk-response': { color: COLORS.response, blur: 5, opacity: 0.9 },
  'pk-fetch': { color: COLORS.fetch, blur: 5, opacity: 0.9 },
  'pk-critical': { color: COLORS.critical, blur: 5, opacity: 0.9 },
};

export const PACKET_COLOR: Record<Packet['kind'], string> = {
  request: COLORS.request,
  response: COLORS.response,
  fetch: COLORS.fetch,
};

const Defs = memo(function Defs() {
  return (
    <defs>
      {Object.entries(GLOWS).map(([id, g]) => (
        <filter key={id} id={`glow-${id}`} x="-150%" y="-150%" width="400%" height="400%">
          <feDropShadow dx={0} dy={0} stdDeviation={g.blur} floodColor={g.color} floodOpacity={g.opacity} />
          <feDropShadow dx={0} dy={0} stdDeviation={g.blur / 3} floodColor={g.color} floodOpacity={g.opacity * 0.7} />
        </filter>
      ))}
      <radialGradient id="jam-fill">
        <stop offset="0%" stopColor={COLORS.jam} stopOpacity={0.2} />
        <stop offset="70%" stopColor={COLORS.jam} stopOpacity={0.1} />
        <stop offset="100%" stopColor={COLORS.jam} stopOpacity={0.03} />
      </radialGradient>
      <linearGradient id="neighbour-fill" x1="0" x2="1">
        <stop offset="0%" stopColor={COLORS.gateway} stopOpacity={0.07} />
        <stop offset="100%" stopColor={COLORS.gateway} stopOpacity={0.02} />
      </linearGradient>
    </defs>
  );
});

const ZoneLayer = memo(function ZoneLayer() {
  const bx = ZONES.border.x;
  return (
    <g className="zones" pointerEvents="none">
      <rect x={bx} y={0} width={VIEWBOX.width - bx} height={VIEWBOX.height} rx={18} fill="url(#neighbour-fill)" />
      <text x={(bx + VIEWBOX.width) / 2} y={40} textAnchor="middle" className="zone-label tight" fill={COLORS.gateway}>
        {ZONES.neighbour.label}
      </text>
      <text x={(bx + VIEWBOX.width) / 2} y={57} textAnchor="middle" className="zone-sublabel" fill={COLORS.gateway}>
        {ZONES.neighbour.sublabel}
      </text>

      <path d={ZONES.forest.path} fill={COLORS.database} fillOpacity={0.06} stroke={COLORS.database} strokeOpacity={0.25} strokeDasharray="3 5" />
      {ZONES.forest.trees.map(([x, y], i) => (
        <g key={i} transform={`translate(${x} ${y})`} fill={COLORS.database} opacity={0.22}>
          <path d="M 0 -11 L 7 0 H 3.5 L 8.5 7 H -8.5 L -3.5 0 H -7 Z" />
          <rect x={-1.2} y={7} width={2.4} height={4} />
        </g>
      ))}
      <text x={ZONES.forest.labelPos.x} y={ZONES.forest.labelPos.y} textAnchor="middle" className="zone-label" fill={COLORS.database}>
        {ZONES.forest.label}
      </text>

      <line x1={bx} x2={bx} y1={24} y2={VIEWBOX.height - 24} stroke="#9AA1AC" strokeWidth={1.3} strokeDasharray="7 7" />
      <text x={bx - 10} y={VIEWBOX.height / 2} className="zone-label" fill="#8A919C" textAnchor="middle" transform={`rotate(-90 ${bx - 10} ${VIEWBOX.height / 2})`}>
        {ZONES.border.label}
      </text>
    </g>
  );
});

const LinkLayer = memo(function LinkLayer({ offline }: { offline: Set<string>; version: number }) {
  return (
    <g pointerEvents="none">
      {LINKS.map(([a, b]) => {
        const p = NODE_BY_ID[a];
        const q = NODE_BY_ID[b];
        const dead = offline.has(a) || offline.has(b);
        return (
          <line
            key={`${a}-${b}`}
            x1={p.x}
            y1={p.y}
            x2={q.x}
            y2={q.y}
            stroke={dead ? COLORS.linkOff : COLORS.link}
            strokeWidth={1.3}
            strokeDasharray={dead ? '3 5' : undefined}
          />
        );
      })}
    </g>
  );
});

function Segment({ a, b, color, active }: { a: string; b: string; color: string; active: boolean }) {
  const p = NODE_BY_ID[a];
  const q = NODE_BY_ID[b];
  return (
    <line
      x1={p.x}
      y1={p.y}
      x2={q.x}
      y2={q.y}
      stroke={color}
      strokeWidth={active ? 2.6 : 2.2}
      strokeOpacity={active ? 0.95 : 0.35}
      strokeLinecap="round"
      className={active ? 'path-active' : undefined}
    />
  );
}

function PathLayer({ packet }: { packet: Packet }) {
  const color = PACKET_COLOR[packet.kind];
  const segs: JSX.Element[] = [];
  for (let i = 0; i < packet.trail.length - 1; i++) {
    segs.push(<Segment key={`t${i}`} a={packet.trail[i]} b={packet.trail[i + 1]} color={color} active={false} />);
  }
  for (let i = 0; i < packet.path.length - 1; i++) {
    segs.push(<Segment key={`p${i}`} a={packet.path[i]} b={packet.path[i + 1]} color={color} active />);
  }
  return <g pointerEvents="none">{segs}</g>;
}

function packetPosition(p: Packet) {
  const a = NODE_BY_ID[p.at];
  if (!p.to) return { x: a.x, y: a.y };
  const b = NODE_BY_ID[p.to];
  const t = Math.min(Math.max(p.progress, 0), 1);
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

function PacketDot({ packet }: { packet: Packet }) {
  const { x, y } = packetPosition(packet);
  const color = PACKET_COLOR[packet.kind];
  return (
    <g transform={`translate(${x} ${y})`} pointerEvents="none">
      <circle r={13} fill={color} opacity={0.14} />
      {packet.critical && packet.kind !== 'fetch' && (
        <circle r={10} fill="none" stroke={COLORS.critical} strokeWidth={1.6} className="crit-ring" />
      )}
      <circle r={6} fill={color} filter={`url(#glow-pk-${packet.kind})`} />
      <circle r={2.3} fill="#fff" />
      {packet.kind !== 'fetch' && (
        <g transform="translate(12 -12)">
          <circle r={6.5} fill="#fff" stroke={color} strokeWidth={1} />
          <LockGlyph size={7} color={color} y={0.4} />
        </g>
      )}
    </g>
  );
}

function WaitingRing({ nodeId }: { nodeId: string }) {
  const n = NODE_BY_ID[nodeId];
  const r = NODE_SIZE[n.type] + 14;
  return (
    <g transform={`translate(${n.x} ${n.y})`} pointerEvents="none">
      <circle r={r} className="wait-ring" fill="none" stroke={COLORS.critical} strokeWidth={2} />
      <circle r={r} fill="none" stroke={COLORS.critical} strokeWidth={1.2} strokeDasharray="4 4" opacity={0.7} />
      <g transform={`translate(0 ${-r - 14})`}>
        <rect x={-84} y={-11} width={168} height={20} rx={10} fill="#fff" stroke={COLORS.critical} strokeOpacity={0.4} />
        <text textAnchor="middle" y={3.5} className="badge-text" fill={COLORS.critical}>
          Waiting · store-and-forward
        </text>
      </g>
    </g>
  );
}

function ExtractBadge() {
  const g = NODE_BY_ID[GATEWAY_ID];
  const r = NODE_SIZE.gateway + 12;
  return (
    <g transform={`translate(${g.x} ${g.y})`} pointerEvents="none">
      <circle r={r} fill="none" stroke={COLORS.gateway} strokeWidth={2} strokeDasharray="10 8" className="spin" />
      <g transform={`translate(0 ${-r - 14})`}>
        <rect x={-62} y={-11} width={124} height={20} rx={10} fill="#fff" stroke={COLORS.gateway} strokeOpacity={0.45} />
        <text textAnchor="middle" y={3.5} className="badge-text" fill={COLORS.gateway}>
          Extracting text…
        </text>
      </g>
    </g>
  );
}

function DriveLayer({ progress }: { progress: number }) {
  const pts = DRIVE_ROUTE.map(([x, y]) => `${x},${y}`).join(' ');
  const pos = pointAlong(DRIVE_ROUTE, progress);
  const flip = pos.dx < 0;
  return (
    <g pointerEvents="none">
      <polyline points={pts} fill="none" stroke={COLORS.vehicle} strokeOpacity={0.12} strokeWidth={9} strokeLinejoin="round" strokeLinecap="round" />
      <polyline points={pts} fill="none" stroke={COLORS.vehicle} strokeOpacity={0.55} strokeWidth={1.6} strokeDasharray="8 7" strokeLinejoin="round" className="path-active slow" />
      <g transform="translate(840 790)">
        <rect x={-150} y={-13} width={300} height={24} rx={12} fill="#fff" stroke={COLORS.vehicle} strokeOpacity={0.2} />
        <text textAnchor="middle" y={4} className="badge-text" fill={COLORS.vehicle}>
          Large file: physical delivery, est. 3 h
        </text>
      </g>
      <g transform={`translate(${pos.x} ${pos.y - 6}) scale(${flip ? -1.2 : 1.2} 1.2)`} filter="url(#glow-gateway)">
        <VehicleGlyph />
      </g>
    </g>
  );
}

interface Props {
  sim: Simulation;
  jamMode: boolean;
  onJamPlaced: () => void;
}

export function NetworkCanvas({ sim, jamMode, onJamPlaced }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [ghost, setGhost] = useState<{ x: number; y: number } | null>(null);

  const toSvg = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return null;
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const r = pt.matrixTransform(ctm.inverse());
    return { x: r.x, y: r.y };
  };

  /** SVG coords → pixel coords inside the wrapper (for HTML overlays) */
  const project = (x: number, y: number) => {
    const ctm = svgRef.current?.getScreenCTM();
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!ctm || !rect) return null;
    return { x: ctm.a * x + ctm.e - rect.left, y: ctm.d * y + ctm.f - rect.top, scale: ctm.a };
  };

  const onNodeClick = useCallback(
    (id: string, e: React.MouseEvent) => {
      if (jamMode) return; // let the click bubble up and place a jam zone
      e.stopPropagation();
      sim.toggleNode(id);
    },
    [sim, jamMode],
  );

  const handleClick = (e: React.MouseEvent) => {
    if (!jamMode) return;
    const p = toSvg(e.clientX, e.clientY);
    if (!p) return;
    sim.addJam(p.x, p.y);
    setGhost(null);
    onJamPlaced();
  };

  const handleMove = (e: React.MouseEvent) => {
    if (!jamMode) return;
    setGhost(toSvg(e.clientX, e.clientY));
  };

  const packet = sim.packet;
  const job = sim.active;
  const hovered = hoverId ? NODE_BY_ID[hoverId] : null;
  const hoverPos = hovered ? project(hovered.x, hovered.y) : null;
  const hubPos = sim.payload ? project(NODE_BY_ID[HUB_ID].x, NODE_BY_ID[HUB_ID].y) : null;

  return (
    <div ref={wrapRef} className={`canvas-wrap ${jamMode ? 'jam-mode' : ''}`}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEWBOX.width} ${VIEWBOX.height}`}
        preserveAspectRatio="xMidYMid meet"
        onClick={handleClick}
        onMouseMove={handleMove}
        onMouseLeave={() => setGhost(null)}
      >
        <Defs />
        <ZoneLayer />
        <LinkLayer offline={sim.offline} version={sim.topologyVersion} />

        {sim.vehicle && <DriveLayer progress={sim.vehicle.progress} />}
        {packet && <PathLayer packet={packet} />}

        {sim.jamZones.map((z) => (
          <g
            key={z.id}
            className="jam-zone"
            onClick={(e) => {
              if (jamMode) return;
              e.stopPropagation();
              sim.removeJam(z.id);
            }}
          >
            <title>Click to remove jamming zone</title>
            <circle cx={z.x} cy={z.y} r={z.r} fill="url(#jam-fill)" stroke={COLORS.jam} strokeWidth={1.5} strokeDasharray="6 5" />
            <circle cx={z.x} cy={z.y} r={z.r} fill="none" stroke={COLORS.jam} strokeWidth={1} className="jam-pulse" />
            <text x={z.x} y={z.y - z.r + 18} textAnchor="middle" className="zone-label" fill={COLORS.jam}>
              Jamming
            </text>
          </g>
        ))}

        {NODES.map((n, i) => (
          <NodeGlyph key={n.id} id={n.id} index={i} status={sim.status(n.id)} hovered={hoverId === n.id} onClick={onNodeClick} onHover={setHoverId} />
        ))}

        {job?.phase === 'extract' && <ExtractBadge />}
        {packet?.waiting && <WaitingRing nodeId={packet.at} />}
        {packet && <PacketDot packet={packet} />}

        {jamMode && ghost && (
          <circle cx={ghost.x} cy={ghost.y} r={JAM_RADIUS} fill={COLORS.jam} fillOpacity={0.06} stroke={COLORS.jam} strokeDasharray="4 6" pointerEvents="none" />
        )}
      </svg>

      {hovered && hoverPos && <NodeTooltip node={hovered} sim={sim} x={hoverPos.x} y={hoverPos.y} offset={(NODE_SIZE[hovered.type] + 10) * hoverPos.scale} />}

      <AnimatePresence>
        {sim.payload && hubPos && (
          <PayloadViewer
            key={sim.payload.jobId}
            payload={sim.payload}
            anchorX={hubPos.x + (NODE_SIZE.hub + 80) * hubPos.scale}
            anchorY={hubPos.y}
            onClose={() => sim.closePayload()}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
