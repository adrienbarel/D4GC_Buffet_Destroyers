import { useEffect, useState } from 'react';
import { ControlPanel } from './components/ControlPanel';
import { EventLog } from './components/EventLog';
import { InsightsPanel } from './components/InsightsPanel';
import { LegendPanel } from './components/LegendPanel';
import { NetworkCanvas } from './components/NetworkCanvas';
import { useSimulation } from './sim/useSimulation';

export default function App() {
  const sim = useSimulation();
  const [jamMode, setJamMode] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setJamMode(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const lastId = sim.log.length ? sim.log[sim.log.length - 1].id : 0;

  return (
    <div className="app">
      <main className="stage">
        <NetworkCanvas sim={sim} jamMode={jamMode} onJamPlaced={() => setJamMode(false)} />
        <div className="banner">
          <span className="banner-dot" />
          Concept demo – simulated data
        </div>
        <div className="stage-left top">
          <LegendPanel />
        </div>
        <div className="stage-left bottom">
          <InsightsPanel sim={sim} />
        </div>
      </main>
      <aside className="sidebar">
        <ControlPanel sim={sim} jamMode={jamMode} onToggleJam={() => setJamMode((j) => !j)} />
        <EventLog entries={sim.log} lastId={lastId} />
      </aside>
    </div>
  );
}
