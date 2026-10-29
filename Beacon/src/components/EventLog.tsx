import { memo, useEffect, useRef } from 'react';
import type { LogEntry } from '../sim/engine';
import { formatClock } from '../sim/geometry';
import { LockIcon } from './icons';

interface Props {
  entries: LogEntry[];
  /** id of the newest entry, used to skip re-renders between log writes */
  lastId: number;
}

export const EventLog = memo(
  function EventLog({ entries }: Props) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const stick = useRef(true);

    useEffect(() => {
      const el = scrollRef.current;
      if (el && stick.current) el.scrollTop = el.scrollHeight;
    });

    return (
      <div className="panel log">
        <div className="panel-title">Event log</div>
        <div
          className="log-scroll"
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
          }}
        >
          {entries.map((e) => (
            <div key={e.id} className={`log-line k-${e.kind}`}>
              <span className="log-time">[{formatClock(e.t)}]</span> <span className="log-text">{e.text}</span>
              {e.beacon && (
                <div className="beacon">
                  <div className="beacon-head">
                    <LockIcon size={11} /> AES-encrypted · {e.beacon.hex.split(' ').length} bytes
                  </div>
                  <div className="beacon-hex">{e.beacon.hex}</div>
                  <div className="beacon-decoded">
                    <span className="beacon-tag">decoded at endpoints only</span>
                    {'{ '}
                    {Object.entries(e.beacon.decoded).map(([k, v], i, arr) => (
                      <span key={k}>
                        {k}: <b>"{v}"</b>
                        {i < arr.length - 1 ? ', ' : ''}
                      </span>
                    ))}
                    {' }'}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  },
  (a, b) => a.lastId === b.lastId,
);
