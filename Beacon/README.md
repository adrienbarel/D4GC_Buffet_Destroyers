# Beacon: relay network concept demo

An interactive, **fully simulated** visualisation of a low-bandwidth relay network for humanitarian field missions. A field hub in a dense forest sends a tiny encrypted request beacon across a mesh of LoRa-style relays to an internet gateway across the border. The gateway fetches the document, compresses it to text, and sends it back.

There is no real networking, backend or API. Everything is hardcoded, and the app is meant for presenting the idea.

## Run it

Requires Node.js 18+.

```bash
npm install
npm run dev
```

Vite opens the app at http://localhost:5173. For a production build use `npm run build`, then `npm run preview`.

## What to try

| Action | What happens |
| --- | --- |
| **Send request** | Cache check → 32-byte encrypted beacon → hop-by-hop routing → gateway ↔ database fetch → text extraction → response beacon → payload viewer at the hub |
| Pick **Drug dosage table** | Already cached: served instantly, no network |
| Send the same request twice | The second one comes from the offline cache (responses are cached on arrival) |
| **Click a node** mid-route | The packet bounces back or reroutes along another path (see the event log) |
| Take R13, R14 and R16 offline | No route exists. The packet waits at the last reachable node (store-and-forward) until you click a node to bring it back |
| **CRITICAL** priority with normal requests queued | The critical request visibly overtakes the queue |
| **Drive there (large file)** | A vehicle travels the road from gateway to hub instead of a response packet |
| **Jam zone** → click the map | A red jamming circle knocks out every node inside it. Click the circle to clear it |
| **Hover** a node | Tooltip with type, status, battery and link quality. Relays show the payload as encrypted and unreadable |
| **Speed** slider | 0.25× – 3× simulation speed |

## Where to edit the data

Everything hardcoded lives in **[`src/data/network.ts`](src/data/network.ts)**:

- `NODES`: id, label, sublabel, type (`hub` · `relay` · `partner` · `gateway` · `database`), x/y position on a 1400 × 860 canvas, fake battery and link quality
- `LINKS`: undirected `[a, b]` node-id pairs (the mesh)
- `REQUESTS`: dropdown entries: title, docId, whether cached at start, original and compressed sizes, and the fictional payload text shown at the hub
- `ZONES`: forest outline, border x-position and zone labels
- `DRIVE_ROUTE`: waypoints for the vehicle in drive-there mode
- `COLORS`, `NODE_SIZE`, `TIMING`, `JAM_RADIUS`, `BEACON`: look and pacing

The hub, gateway and database are referenced by `HUB_ID`, `GATEWAY_ID` and `DATABASE_ID`.

## Code structure

```
src/
  data/network.ts          all hardcoded data
  sim/
    engine.ts              Simulation class: jobs, queue, packets, rerouting, logging
    graph.ts               adjacency + Dijkstra over online nodes
    beacon.ts              fake 32-byte encrypted beacon (hex + decoded view)
    geometry.ts            hexagons, polyline interpolation, formatting
    useSimulation.ts       requestAnimationFrame loop → React re-render
  components/
    NetworkCanvas.tsx      SVG map: zones, links, paths, jam zones, packets, vehicle
    NodeGlyph.tsx          one node (hexagon/dot, glow, pulse, offline X, labels)
    NodeTooltip.tsx        hover card
    PayloadViewer.tsx      result card anchored at the hub
    LegendPanel.tsx        top-left legend
    InsightsPanel.tsx      bottom-left live stats
    ControlPanel.tsx       request controls + animated queue
    EventLog.tsx           timestamped monospace log
```

All content is fictional placeholder text. It is not medical guidance and does not represent any real organisation.
