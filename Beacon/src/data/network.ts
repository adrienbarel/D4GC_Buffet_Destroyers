// ─────────────────────────────────────────────────────────────────────────────
// All hardcoded demo data lives in this file: nodes, links, zones, requests,
// colours and timings. Edit freely: the simulation picks everything up from here.
// Coordinates are in SVG units on a VIEWBOX.width × VIEWBOX.height canvas.
// ─────────────────────────────────────────────────────────────────────────────

export const VIEWBOX = { width: 1400, height: 860 };

export const COLORS = {
  hub: '#0047FF',
  relay: '#7A00FF',
  partner: '#A35CFF',
  gateway: '#FF5A00',
  database: '#00A86B',
  offline: '#B0B0B0',
  offlineX: '#E5002B',
  link: '#D6D9DF',
  linkOff: '#ECEDF0',
  request: '#0047FF',
  response: '#FF5A00',
  fetch: '#00A86B',
  critical: '#E5002B',
  jam: '#E5002B',
  vehicle: '#1F2937',
  ink: '#0E1116',
  muted: '#6B7280',
} as const;

export type NodeType = 'hub' | 'relay' | 'partner' | 'gateway' | 'database';

export interface NetNode {
  id: string;
  label: string;
  sublabel?: string;
  type: NodeType;
  x: number;
  y: number;
  /** Fake battery level, 0–100 */
  battery: number;
  /** Fake link quality, 0–1 (also used as a routing weight) */
  linkQuality: number;
}

export const HUB_ID = 'H1';
export const GATEWAY_ID = 'G1';
export const DATABASE_ID = 'DB';

/** Node radius per type, in SVG units */
export const NODE_SIZE: Record<NodeType, number> = {
  hub: 30,
  gateway: 27,
  database: 21,
  relay: 16,
  partner: 6,
};

export const TYPE_LABEL: Record<NodeType, string> = {
  hub: 'Field Hub',
  relay: 'Relay node',
  partner: 'Partner relay',
  gateway: 'Gateway',
  database: 'Database',
};

export const NODES: NetNode[] = [
  // Dense forest
  { id: 'H1', label: 'Field Hub', sublabel: 'Mobile clinic · LoRa base', type: 'hub', x: 200, y: 450, battery: 92, linkQuality: 0.97 },
  { id: 'R1', label: 'Relay R1', sublabel: 'Tree-mounted · LoRa', type: 'relay', x: 380, y: 300, battery: 71, linkQuality: 0.82 },
  { id: 'R2', label: 'Relay R2', sublabel: 'Tree-mounted · LoRa', type: 'relay', x: 400, y: 600, battery: 64, linkQuality: 0.78 },

  // Middle mesh
  { id: 'R3', label: 'Relay R3', sublabel: 'Ridge mast · LoRa', type: 'relay', x: 540, y: 215, battery: 88, linkQuality: 0.9 },
  { id: 'R4', label: 'Relay R4', sublabel: 'Health post · solar', type: 'relay', x: 555, y: 450, battery: 95, linkQuality: 0.93 },
  { id: 'R5', label: 'Relay R5', sublabel: 'Village kiosk · LoRa', type: 'relay', x: 545, y: 690, battery: 58, linkQuality: 0.74 },
  { id: 'R6', label: 'Relay R6', sublabel: 'School roof · solar', type: 'relay', x: 705, y: 320, battery: 83, linkQuality: 0.88 },
  { id: 'R7', label: 'Relay R7', sublabel: 'LoRa · solar', type: 'relay', x: 715, y: 585, battery: 77, linkQuality: 0.86 },
  { id: 'R8', label: 'Relay R8', sublabel: 'Hilltop · LoRa', type: 'relay', x: 865, y: 200, battery: 69, linkQuality: 0.8 },
  { id: 'R9', label: 'Relay R9', sublabel: 'Partner clinic · solar', type: 'relay', x: 870, y: 445, battery: 90, linkQuality: 0.92 },
  { id: 'R10', label: 'Relay R10', sublabel: 'River crossing · LoRa', type: 'relay', x: 860, y: 700, battery: 45, linkQuality: 0.69 },
  { id: 'R11', label: 'Relay R11', sublabel: 'Water tower · LoRa', type: 'relay', x: 1015, y: 310, battery: 81, linkQuality: 0.87 },
  { id: 'R12', label: 'Relay R12', sublabel: 'Health post · solar', type: 'relay', x: 1020, y: 585, battery: 86, linkQuality: 0.89 },
  { id: 'R13', label: 'Relay R13', sublabel: 'Ridge mast · LoRa', type: 'relay', x: 1130, y: 190, battery: 74, linkQuality: 0.83 },
  { id: 'R14', label: 'Relay R14', sublabel: 'Market town · solar', type: 'relay', x: 1135, y: 440, battery: 93, linkQuality: 0.94 },
  { id: 'R15', label: 'Relay R15', sublabel: 'Partner clinic · LoRa', type: 'relay', x: 1130, y: 700, battery: 62, linkQuality: 0.79 },

  // Small partner relays (unlabelled dots, details on hover)
  { id: 'P1', label: 'Partner relay P1', sublabel: 'Community handset', type: 'partner', x: 470, y: 130, battery: 54, linkQuality: 0.7 },
  { id: 'P2', label: 'Partner relay P2', sublabel: 'Farm co-op radio', type: 'partner', x: 705, y: 120, battery: 66, linkQuality: 0.72 },
  { id: 'P3', label: 'Partner relay P3', sublabel: 'Church roof node', type: 'partner', x: 1010, y: 110, battery: 73, linkQuality: 0.75 },
  { id: 'P4', label: 'Partner relay P4', sublabel: 'Community handset', type: 'partner', x: 440, y: 790, battery: 38, linkQuality: 0.62 },
  { id: 'P5', label: 'Partner relay P5', sublabel: 'Motorbike courier', type: 'partner', x: 700, y: 800, battery: 49, linkQuality: 0.66 },
  { id: 'P6', label: 'Partner relay P6', sublabel: 'Fishing camp node', type: 'partner', x: 980, y: 810, battery: 57, linkQuality: 0.68 },
  { id: 'P7', label: 'Partner relay P7', sublabel: 'Herders’ repeater', type: 'partner', x: 1180, y: 95, battery: 81, linkQuality: 0.74 },
  { id: 'P8', label: 'Partner relay P8', sublabel: 'Teacher’s handset', type: 'partner', x: 630, y: 400, battery: 61, linkQuality: 0.71 },

  // Across the border
  { id: 'R16', label: 'Relay R16', sublabel: 'Border post · LoRa', type: 'relay', x: 1290, y: 690, battery: 80, linkQuality: 0.85 },
  { id: 'G1', label: 'Gateway G1', sublabel: 'Satellite uplink · internet', type: 'gateway', x: 1300, y: 465, battery: 99, linkQuality: 0.98 },
  { id: 'DB', label: 'Database', sublabel: 'Medical library · cloud', type: 'database', x: 1320, y: 250, battery: 100, linkQuality: 1 },
];

export const NODE_BY_ID: Record<string, NetNode> = Object.fromEntries(NODES.map((n) => [n.id, n]));

/** Undirected radio links between nodes */
export const LINKS: [string, string][] = [
  ['H1', 'R1'], ['H1', 'R2'], ['R1', 'R2'], ['R1', 'P1'], ['R1', 'R3'], ['R1', 'R4'],
  ['R2', 'R4'], ['R2', 'R5'], ['R2', 'P4'], ['P4', 'R5'],
  ['P1', 'R3'], ['R3', 'P2'], ['R3', 'R6'], ['R4', 'P8'], ['P8', 'R6'], ['P8', 'R7'],
  ['R4', 'R7'], ['R5', 'R7'], ['R5', 'P5'],
  ['P2', 'R8'], ['R6', 'R8'], ['R6', 'R9'], ['R7', 'R9'], ['R7', 'R10'], ['P5', 'R10'],
  ['R8', 'P3'], ['R8', 'R11'], ['R9', 'R11'], ['R9', 'R12'], ['R10', 'R12'], ['R10', 'P6'],
  ['P3', 'R13'], ['P3', 'P7'], ['R11', 'R13'], ['R11', 'R14'], ['R12', 'R14'], ['R12', 'R15'],
  ['P6', 'R15'], ['R13', 'P7'],
  ['R13', 'G1'], ['R14', 'G1'], ['R15', 'R16'], ['R16', 'G1'],
  ['G1', 'DB'],
];

// ── Map zones ────────────────────────────────────────────────────────────────

export const ZONES = {
  forest: {
    label: 'Dense forest',
    path: 'M 90 220 C 150 120, 340 100, 450 160 C 530 210, 500 330, 480 420 C 460 520, 520 650, 455 735 C 385 815, 185 805, 110 725 C 40 645, 60 520, 50 420 C 40 320, 50 270, 90 220 Z',
    labelPos: { x: 170, y: 352 },
    trees: [
      [115, 330], [140, 610], [290, 395], [300, 548], [335, 720], [250, 250], [460, 470], [210, 700],
    ] as [number, number][],
  },
  border: { x: 1210, label: 'Border' },
  neighbour: {
    label: 'Neighbouring country',
    sublabel: 'Internet available',
  },
};

/** Waypoints for the "drive there" vehicle, Gateway → Field Hub */
export const DRIVE_ROUTE: [number, number][] = [
  [1300, 465], [1240, 770], [985, 822], [700, 830], [480, 772], [300, 585], [200, 450],
];

// ── Requests ─────────────────────────────────────────────────────────────────

export interface PayloadSection {
  heading: string;
  lines: string[];
}

export interface RequestDef {
  id: string;
  title: string;
  docId: string;
  /** Already present in the hub's offline cache at start */
  cached: boolean;
  original: { label: string; bytes: number };
  compressed: { label: string; bytes: number };
  payload: PayloadSection[];
}

export const REQUESTS: RequestDef[] = [
  {
    id: 'malaria',
    title: 'Paediatric malaria protocol',
    docId: 'PRT-MAL-PAED-v3',
    cached: false,
    original: { label: '1.8 MB PDF', bytes: 1_887_437 },
    compressed: { label: '9.4 KB', bytes: 9_626 },
    payload: [
      { heading: '1 · Triage (placeholder)', lines: ['Check general danger signs listed in local guideline §2.', 'Record temperature, weight and onset of fever.'] },
      { heading: '2 · Testing (placeholder)', lines: ['Perform rapid diagnostic test per kit instructions.', 'Log result and lot number in the field register.'] },
      { heading: '3 · Treatment (placeholder)', lines: ['Select regimen from national weight-band table [—].', 'Dose: [see current national guideline]. Do not use this text.'] },
      { heading: '4 · Referral (placeholder)', lines: ['Refer if danger signs present or no improvement in [—] h.'] },
    ],
  },
  {
    id: 'lab',
    title: 'Lab result – patient #A-1042',
    docId: 'LAB-A1042-0917',
    cached: false,
    original: { label: '412 KB scanned report', bytes: 421_888 },
    compressed: { label: '1.1 KB', bytes: 1_126 },
    payload: [
      { heading: 'Patient (fictional)', lines: ['ID #A-1042 · sample collected day 3 · courier ref 0917'] },
      { heading: 'Result (placeholder)', lines: ['Panel A: [value] (ref. range [—])', 'Panel B: [value] (ref. range [—])', 'Comment: placeholder text for demo purposes only.'] },
      { heading: 'Validated by', lines: ['Remote lab technician (simulated)'] },
    ],
  },
  {
    id: 'consult',
    title: 'Specialist consult',
    docId: 'CNS-PED-22871',
    cached: false,
    original: { label: '2.6 MB case notes + images', bytes: 2_726_297 },
    compressed: { label: '6.3 KB', bytes: 6_451 },
    payload: [
      { heading: 'Reply from remote specialist (simulated)', lines: ['Thank you for the case summary. Based on the notes provided:'] },
      { heading: 'Suggested next steps (placeholder)', lines: ['• Repeat observation in [—] hours.', '• Consider [placeholder] if symptoms persist.', '• Schedule follow-up consult via next relay window.'] },
      { heading: 'Note', lines: ['Images were not transmitted; request "Drive there" for full files.'] },
    ],
  },
  {
    id: 'dosage',
    title: 'Drug dosage table',
    docId: 'TBL-DOSE-2026-02',
    cached: true,
    original: { label: '740 KB PDF', bytes: 757_760 },
    compressed: { label: '3.2 KB', bytes: 3_277 },
    payload: [
      { heading: 'Weight-band table (placeholder values)', lines: ['5–9 kg ........ [—]', '10–14 kg ...... [—]', '15–24 kg ...... [—]', '25–34 kg ...... [—]'] },
      { heading: 'Note', lines: ['All values intentionally blank. Fictional demo document.'] },
    ],
  },
];

export const REQUEST_BY_ID: Record<string, RequestDef> = Object.fromEntries(REQUESTS.map((r) => [r.id, r]));

// ── Beacon contents ──────────────────────────────────────────────────────────

export const BEACON = {
  hubId: 'FH-01',
  regionCode: 'RG-07',
  sizeBytes: 32,
  /** LoRa frame payload size used to count response frames */
  frameBytes: 222,
};

// ── Timing (seconds of simulated time at 1× speed) ───────────────────────────

export const TIMING = {
  perHopBase: 0.45,
  /** Additional seconds per SVG unit of link length */
  perUnit: 1 / 450,
  criticalFactor: 0.7,
  cacheCheck: 0.6,
  extract: 1.4,
  driveDuration: 14,
  gapBetweenJobs: 0.6,
  queueJumpDelay: 0.7,
  /** Fake real-world latency per hop, for the insights panel */
  latencyPerHop: 0.42,
};

export const JAM_RADIUS = 110;
