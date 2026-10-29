import { COLORS, TYPE_LABEL, type NetNode } from '../data/network';
import type { Simulation } from '../sim/engine';
import { LockIcon } from './icons';

interface Props {
  node: NetNode;
  sim: Simulation;
  x: number;
  y: number;
  offset: number;
}

export function NodeTooltip({ node, sim, x, y, offset }: Props) {
  const status = sim.status(node.id);
  const p = sim.packet;
  const holding = p?.waiting && p.at === node.id;
  const relaying = p && !p.waiting && (p.at === node.id || p.to === node.id);

  let statusText = 'Online';
  let statusColor: string = COLORS.database;
  if (status === 'offline') [statusText, statusColor] = ['Offline (click to restore)', COLORS.offlineX];
  else if (status === 'jammed') [statusText, statusColor] = ['Jammed: RF interference', COLORS.offlineX];
  else if (holding) [statusText, statusColor] = ['Holding packet (store-and-forward)', COLORS.critical];
  else if (relaying) [statusText, statusColor] = ['Relaying packet', COLORS.relay];

  const flipBelow = y < 190;
  const isRelay = node.type === 'relay' || node.type === 'partner';
  const battColor = node.battery < 50 ? COLORS.gateway : COLORS.database;

  return (
    <div
      className="tooltip"
      style={{
        left: x,
        top: flipBelow ? y + offset : y - offset,
        transform: `translate(-50%, ${flipBelow ? '0' : '-100%'})`,
      }}
    >
      <div className="tooltip-head">
        <span className="tooltip-swatch" style={{ background: status === 'online' ? COLORS[node.type] : COLORS.offline }} />
        <div>
          <div className="tooltip-name">{node.label}</div>
          <div className="tooltip-type">
            {TYPE_LABEL[node.type]}
            {node.sublabel ? ` · ${node.sublabel}` : ''}
          </div>
        </div>
      </div>
      <dl className="tooltip-grid">
        <dt>Status</dt>
        <dd style={{ color: statusColor }}>{statusText}</dd>
        <dt>Battery</dt>
        <dd>
          <span className="bar">
            <span style={{ width: `${node.battery}%`, background: battColor }} />
          </span>
          {node.battery}%
        </dd>
        <dt>Link quality</dt>
        <dd>
          <span className="bar">
            <span style={{ width: `${node.linkQuality * 100}%`, background: COLORS.relay }} />
          </span>
          {Math.round(node.linkQuality * 100)}%
        </dd>
        {isRelay && (
          <>
            <dt>Payload</dt>
            <dd>
              <LockIcon size={11} /> Encrypted, unreadable
            </dd>
          </>
        )}
        {node.type === 'hub' && (
          <>
            <dt>Offline cache</dt>
            <dd>{sim.cache.size} documents</dd>
          </>
        )}
        {node.type === 'gateway' && (
          <>
            <dt>Uplink</dt>
            <dd>Satellite · internet</dd>
          </>
        )}
      </dl>
    </div>
  );
}
