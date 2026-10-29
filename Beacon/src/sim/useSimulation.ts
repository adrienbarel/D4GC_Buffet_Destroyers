import { useEffect, useState } from 'react';
import { Simulation } from './engine';

/** Owns one Simulation instance and re-renders on every animation frame. */
export function useSimulation() {
  const [sim] = useState(() => new Simulation());
  const [, setFrame] = useState(0);

  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      sim.step(dt);
      setFrame((f) => (f + 1) % 1_000_000);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [sim]);

  return sim;
}
