import { NODES, TIMING } from '../data/network';
import type { Simulation } from '../sim/engine';
import { formatBytes } from '../sim/geometry';

export function InsightsPanel({ sim }: { sim: Simulation }) {
  const online = NODES.length - sim.offline.size;
  const hops = sim.currentHops();
  // fake but plausible: per-hop airtime + gateway overhead, with a little jitter
  const jitter = Math.sin(sim.time * 1.7) * 0.06 + Math.sin(sim.time * 0.43) * 0.05;
  const latency = hops === null ? null : hops * TIMING.latencyPerHop + 0.35 + jitter;

  const stats = [
    { label: 'Nodes online', value: `${online}`, unit: `/ ${NODES.length}`, warn: online < NODES.length },
    { label: 'Hops on path', value: hops === null ? '—' : String(hops), unit: hops === null ? 'no route' : '' },
    { label: 'Est. latency', value: latency === null ? '—' : latency.toFixed(2), unit: latency === null ? '' : 's' },
    { label: 'Bytes sent', value: formatBytes(sim.stats.bytesSent), unit: '' },
    { label: 'Bytes received', value: formatBytes(sim.stats.bytesReceived), unit: '' },
    { label: 'Compression', value: sim.stats.ratio === null ? '—' : `${Math.round(sim.stats.ratio)}:1`, unit: '' },
  ];

  return (
    <div className="panel insights">
      <div className="panel-title">Network insights</div>
      <div className="stat-grid">
        {stats.map((s) => (
          <div key={s.label} className="stat">
            <div className={`stat-value ${s.warn ? 'warn' : ''}`}>
              {s.value}
              {s.unit && <span className="stat-unit">{s.unit}</span>}
            </div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
