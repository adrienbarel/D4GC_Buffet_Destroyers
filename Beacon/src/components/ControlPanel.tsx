import { AnimatePresence, motion } from 'framer-motion';
import { memo, useState } from 'react';
import { REQUESTS } from '../data/network';
import type { DeliveryMode, Phase, Priority, Simulation } from '../sim/engine';

const PHASE_LABEL: Record<Phase, string> = {
  queued: 'Queued',
  cache: 'Checking cache',
  request: 'Beacon en route',
  fetch: 'Gateway ↔ database',
  extract: 'Extracting text',
  response: 'Response en route',
  drive: 'Vehicle en route',
};

interface QueueItem {
  id: number;
  title: string;
  priority: Priority;
  status: string;
  active: boolean;
}

const QueueList = memo(
  function QueueList({ items }: { items: QueueItem[]; sig: string }) {
    return (
      <ul className="queue">
        <AnimatePresence initial={false}>
          {items.map((it) => (
            <motion.li
              key={it.id}
              layout
              className={`queue-item ${it.active ? 'active' : ''} ${it.priority}`}
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: 24 }}
              transition={{ type: 'spring', stiffness: 420, damping: 34 }}
            >
              <span className={`chip ${it.priority}`}>{it.priority === 'critical' ? 'CRITICAL' : 'Normal'}</span>
              <span className="queue-title">{it.title}</span>
              <span className="queue-status">{it.status}</span>
            </motion.li>
          ))}
        </AnimatePresence>
        {items.length === 0 && <li className="queue-empty">No requests in flight</li>}
      </ul>
    );
  },
  (a, b) => a.sig === b.sig,
);

interface Props {
  sim: Simulation;
  jamMode: boolean;
  onToggleJam: () => void;
}

export function ControlPanel({ sim, jamMode, onToggleJam }: Props) {
  const [requestId, setRequestId] = useState(REQUESTS[0].id);
  const [priority, setPriority] = useState<Priority>('normal');
  const [mode, setMode] = useState<DeliveryMode>('relay');
  const [speed, setSpeed] = useState(sim.speed);

  const items: QueueItem[] = [];
  if (sim.active) {
    const a = sim.active;
    items.push({
      id: a.id,
      title: a.request.title,
      priority: a.priority,
      status: sim.packet?.waiting ? 'Waiting · no route' : PHASE_LABEL[a.phase],
      active: true,
    });
  }
  for (const j of sim.queue) {
    items.push({ id: j.id, title: j.request.title, priority: j.priority, status: 'Queued', active: false });
  }
  const sig = items.map((i) => `${i.id}:${i.status}`).join('|');

  return (
    <div className="panel control">
      <div className="panel-title">Control</div>

      <div className="field">
        <label className="field-label" htmlFor="req">
          Request
        </label>
        <div className="send-row">
          <select id="req" value={requestId} onChange={(e) => setRequestId(e.target.value)}>
            {REQUESTS.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title}
                {sim.cache.has(r.id) ? '  (cached)' : ''}
              </option>
            ))}
          </select>
          <button className={`btn primary ${priority === 'critical' ? 'critical' : ''}`} onClick={() => sim.sendRequest(requestId, priority, mode)}>
            Send request
          </button>
        </div>
      </div>

      <div className="field-row">
        <div className="field">
          <span className="field-label">Priority</span>
          <div className="segmented">
            <button className={priority === 'normal' ? 'on' : ''} onClick={() => setPriority('normal')}>
              Normal
            </button>
            <button className={priority === 'critical' ? 'on critical' : ''} onClick={() => setPriority('critical')}>
              CRITICAL
            </button>
          </div>
        </div>
        <div className="field speed">
          <span className="field-label">
            Speed <strong>{speed.toFixed(2).replace(/0$/, '')}×</strong>
          </span>
          <input
            type="range"
            min={0.25}
            max={3}
            step={0.25}
            value={speed}
            onChange={(e) => {
              const v = Number(e.target.value);
              setSpeed(v);
              sim.speed = v;
            }}
          />
        </div>
      </div>

      <div className="field">
        <span className="field-label">Delivery mode</span>
        <div className="segmented full">
          <button className={mode === 'relay' ? 'on' : ''} onClick={() => setMode('relay')}>
            Compressed text via relays
          </button>
          <button className={mode === 'drive' ? 'on' : ''} onClick={() => setMode('drive')}>
            Drive there (large file)
          </button>
        </div>
      </div>

      <div className="btn-row">
        <button className={`btn jam ${jamMode ? 'armed' : ''}`} onClick={onToggleJam}>
          {jamMode ? 'Click map to place… (Esc)' : 'Jam zone'}
        </button>
        <button
          className="btn ghost"
          onClick={() => {
            sim.reset();
          }}
        >
          Reset
        </button>
      </div>

      <p className="hint">Click any node to take it offline · click again to restore · click a jam zone to clear it</p>

      <div className="field-label queue-label">Queue</div>
      <QueueList items={items} sig={sig} />
    </div>
  );
}
