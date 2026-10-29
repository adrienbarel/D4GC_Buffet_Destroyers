import { motion } from 'framer-motion';
import { COLORS } from '../data/network';
import type { PayloadView } from '../sim/engine';
import { formatBytes } from '../sim/geometry';

interface Props {
  payload: PayloadView;
  anchorX: number;
  anchorY: number;
  onClose: () => void;
}

const HEADERS = {
  relay: { title: 'Decompressed on site', note: 'Received via encrypted relay mesh', color: COLORS.hub },
  cache: { title: 'Served from offline cache', note: 'No network needed', color: COLORS.database },
  drive: { title: 'Delivered by vehicle', note: 'Full original file, physical transport', color: COLORS.gateway },
};

export function PayloadViewer({ payload, anchorX, anchorY, onClose }: Props) {
  const { request, source } = payload;
  const h = HEADERS[source];

  const size =
    source === 'relay'
      ? `${request.compressed.label} → ${formatBytes(request.compressed.bytes * 3.1)} text`
      : source === 'drive'
        ? request.original.label
        : `${request.compressed.label} (local)`;
  const hops = source === 'cache' ? '0' : source === 'drive' ? 'n/a' : `${payload.hops} (round trip)`;
  const time = source === 'drive' ? `est. 3 h (sim ${payload.totalTime.toFixed(1)} s)` : `${payload.totalTime.toFixed(1)} s`;

  return (
    <motion.div
      className="payload"
      style={{ left: anchorX, top: anchorY, ['--accent' as string]: h.color }}
      initial={{ opacity: 0, scale: 0.92, x: -12, y: '-50%' }}
      animate={{ opacity: 1, scale: 1, x: 0, y: '-50%' }}
      exit={{ opacity: 0, scale: 0.95, x: -8, y: '-50%' }}
      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
      onClick={(e) => e.stopPropagation()}
    >
      <span className="payload-pointer" />
      <div className="payload-head">
        <div>
          <div className="panel-title" style={{ color: h.color }}>
            {h.title}
          </div>
          <div className="payload-doc">{request.title}</div>
          <div className="payload-note">{h.note}</div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>

      <div className="payload-meta">
        <div>
          <span>Size</span>
          <strong>{size}</strong>
        </div>
        <div>
          <span>Hops</span>
          <strong>{hops}</strong>
        </div>
        <div>
          <span>Total time</span>
          <strong>{time}</strong>
        </div>
      </div>

      <div className="payload-body">
        {request.payload.map((s) => (
          <section key={s.heading}>
            <h4>{s.heading}</h4>
            {s.lines.map((l) => (
              <p key={l}>{l}</p>
            ))}
          </section>
        ))}
      </div>
      <div className="payload-foot">Fictional placeholder content · not medical guidance</div>
    </motion.div>
  );
}
