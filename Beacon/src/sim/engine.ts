import {
  BEACON,
  DATABASE_ID,
  GATEWAY_ID,
  HUB_ID,
  JAM_RADIUS,
  LINKS,
  NODES,
  NODE_BY_ID,
  REQUESTS,
  REQUEST_BY_ID,
  TIMING,
  type RequestDef,
} from '../data/network';
import { encodeBeacon, type BeaconInfo } from './beacon';
import { distance, shortestPath } from './graph';

export type Priority = 'normal' | 'critical';
export type DeliveryMode = 'relay' | 'drive';
export type Phase = 'queued' | 'cache' | 'request' | 'fetch' | 'extract' | 'response' | 'drive';
export type PacketKind = 'request' | 'response' | 'fetch';
export type NodeStatus = 'online' | 'offline' | 'jammed';
export type LogKind = 'info' | 'ok' | 'warn' | 'error' | 'crit' | 'cache' | 'beacon' | 'muted';

export interface Job {
  id: number;
  request: RequestDef;
  priority: Priority;
  mode: DeliveryMode;
  phase: Phase;
  startedAt: number;
  hops: number;
  /** Sim time at which a critical job overtakes normal jobs in the queue */
  jumpAt: number | null;
}

export interface Packet {
  kind: PacketKind;
  /** Node the packet is at (or departed from, while in flight) */
  at: string;
  /** Next hop while in flight, null while sitting at `at` */
  to: string | null;
  progress: number;
  /** -1 while bouncing back from a node that went offline mid-hop */
  dir: 1 | -1;
  dest: string;
  /** Planned route; path[0] === at and path[1] === to */
  path: string[];
  /** Nodes already visited */
  trail: string[];
  waiting: boolean;
  bouncedFrom: string | null;
  critical: boolean;
}

export interface LogEntry {
  id: number;
  t: number;
  kind: LogKind;
  text: string;
  beacon?: BeaconInfo;
}

export interface JamZone {
  id: number;
  x: number;
  y: number;
  r: number;
}

export interface PayloadView {
  jobId: number;
  request: RequestDef;
  source: 'cache' | 'relay' | 'drive';
  hops: number;
  totalTime: number;
}

export interface Stats {
  bytesSent: number;
  bytesReceived: number;
  ratio: number | null;
}

export const shortName = (id: string) => {
  const n = NODE_BY_ID[id];
  if (n.type === 'hub') return 'Hub';
  if (n.type === 'gateway') return 'Gateway';
  if (n.type === 'database') return 'Database';
  return n.id;
};

const MAX_LOG = 300;

export class Simulation {
  time = 0;
  speed = 1;
  manualOffline = new Set<string>();
  jamZones: JamZone[] = [];
  offline = new Set<string>();
  queue: Job[] = [];
  active: Job | null = null;
  packet: Packet | null = null;
  vehicle: { progress: number } | null = null;
  phaseTimer = 0;
  idleGap = 0;
  log: LogEntry[] = [];
  stats: Stats = { bytesSent: 0, bytesReceived: 0, ratio: null };
  payload: PayloadView | null = null;
  cache = new Set<string>();
  bestRoute: string[] | null = null;
  /** Bumped whenever topology changes, so memoised layers know to redraw */
  topologyVersion = 0;
  private nextId = 1;

  constructor() {
    this.reset();
  }

  reset() {
    this.time = 0;
    this.manualOffline = new Set();
    this.jamZones = [];
    this.queue = [];
    this.active = null;
    this.packet = null;
    this.vehicle = null;
    this.phaseTimer = 0;
    this.idleGap = 0;
    this.log = [];
    this.stats = { bytesSent: 0, bytesReceived: 0, ratio: null };
    this.payload = null;
    this.cache = new Set(REQUESTS.filter((r) => r.cached).map((r) => r.id));
    this.recomputeOffline();
    this.addLog('info', `Network initialised · ${NODES.length} nodes, ${LINKS.length} links`);
    this.addLog('muted', `Offline cache holds ${this.cache.size} document(s)`);
    if (this.bestRoute) this.addLog('muted', `Best route Hub → Gateway: ${this.bestRoute.length - 1} hops`);
  }

  // ── Public controls ───────────────────────────────────────────────────────

  sendRequest(requestId: string, priority: Priority, mode: DeliveryMode) {
    const request = REQUEST_BY_ID[requestId];
    const job: Job = {
      id: this.nextId++,
      request,
      priority,
      mode,
      phase: 'queued',
      startedAt: 0,
      hops: 0,
      jumpAt: null,
    };
    const busy = this.active !== null || this.queue.length > 0;
    this.queue.push(job);
    const tag = priority === 'critical' ? 'CRITICAL' : 'normal';
    this.addLog(priority === 'critical' ? 'crit' : 'info', `Queued: '${request.title}' (${tag}, ${mode === 'relay' ? 'compressed text' : 'drive there'})`);
    if (priority === 'critical' && this.queue.some((j) => j !== job && j.priority === 'normal')) {
      job.jumpAt = this.time + TIMING.queueJumpDelay;
    }
    if (!busy) this.idleGap = 0;
  }

  toggleNode(id: string) {
    if (this.isJammed(id)) {
      this.addLog('warn', `${shortName(id)} is inside a jamming zone, remove the zone to restore it`);
      return;
    }
    const before = new Set(this.offline);
    if (this.manualOffline.has(id)) {
      this.manualOffline.delete(id);
      this.addLog('ok', `${shortName(id)} back online`);
    } else {
      this.manualOffline.add(id);
      this.addLog('error', `${shortName(id)} taken offline`);
    }
    this.topologyChanged(before);
  }

  addJam(x: number, y: number) {
    const before = new Set(this.offline);
    this.jamZones.push({ id: this.nextId++, x, y, r: JAM_RADIUS });
    this.recomputeOffline();
    const hit = [...this.offline].filter((n) => !before.has(n));
    this.addLog('error', `Jamming zone activated: ${hit.length ? `${hit.map(shortName).join(', ')} knocked out` : 'no nodes affected'}`);
    this.topologyChanged(before);
  }

  removeJam(id: number) {
    const before = new Set(this.offline);
    this.jamZones = this.jamZones.filter((z) => z.id !== id);
    this.recomputeOffline();
    const back = [...before].filter((n) => !this.offline.has(n));
    this.addLog('ok', `Jamming zone cleared${back.length ? `: ${back.map(shortName).join(', ')} restored` : ''}`);
    this.topologyChanged(before);
  }

  closePayload() {
    this.payload = null;
  }

  // ── Queries ───────────────────────────────────────────────────────────────

  isJammed(id: string) {
    const n = NODE_BY_ID[id];
    return this.jamZones.some((z) => Math.hypot(n.x - z.x, n.y - z.y) <= z.r);
  }

  status(id: string): NodeStatus {
    if (this.isJammed(id)) return 'jammed';
    if (this.manualOffline.has(id)) return 'offline';
    return 'online';
  }

  /** Hop count of the path the current packet is on, or the idle best route */
  currentHops(): number | null {
    const p = this.packet;
    if (p && p.kind !== 'fetch') return p.trail.length - 1 + Math.max(p.path.length - 1, 0);
    return this.bestRoute ? this.bestRoute.length - 1 : null;
  }

  // ── Main loop ─────────────────────────────────────────────────────────────

  step(realDt: number) {
    const dt = realDt * this.speed;
    this.time += dt;
    this.processQueueJumps();

    if (!this.active) {
      if (this.queue.length) {
        this.idleGap -= dt;
        if (this.idleGap <= 0) this.startNext();
      }
      return;
    }

    const job = this.active;
    switch (job.phase) {
      case 'cache':
        this.phaseTimer -= dt;
        if (this.phaseTimer <= 0) this.afterCacheCheck(job);
        break;

      case 'request':
        if (this.advancePacket(dt) === 'arrived') {
          this.addLog('ok', `Beacon reached Gateway after ${job.hops} hops`);
          this.addLog('info', `Gateway decrypts beacon → docId ${job.request.docId}, querying database`);
          job.phase = 'fetch';
          this.packet = this.makePacket('fetch', GATEWAY_ID, DATABASE_ID, job);
        }
        break;

      case 'fetch':
        if (this.advancePacket(dt) === 'arrived') {
          if (this.packet!.dest === DATABASE_ID) {
            this.addLog('muted', `Database: '${job.request.title}' found (${job.request.original.label})`);
            this.packet = this.makePacket('fetch', DATABASE_ID, GATEWAY_ID, job);
          } else {
            this.packet = null;
            job.phase = 'extract';
            this.phaseTimer = TIMING.extract;
            this.addLog('info', 'Gateway extracting text and compressing…');
          }
        }
        break;

      case 'extract':
        this.phaseTimer -= dt;
        if (this.phaseTimer <= 0) {
          const { original, compressed } = job.request;
          this.stats.ratio = original.bytes / compressed.bytes;
          if (job.mode === 'relay') {
            this.addLog('ok', `Extracted text: ${original.label} → ${compressed.label} compressed text`);
            const frames = Math.ceil(compressed.bytes / BEACON.frameBytes);
            this.addLog('beacon', `Response beacon: ${compressed.label} in ${frames} LoRa frames, encrypted`, encodeBeacon(job.id + 1000, job.request.docId, job.priority === 'critical', 'RSP'));
            job.phase = 'response';
            this.packet = this.makePacket('response', GATEWAY_ID, HUB_ID, job);
          } else {
            this.addLog('warn', `Large file: physical delivery, est. 3 h, vehicle dispatched with full ${original.label}`);
            job.phase = 'drive';
            this.vehicle = { progress: 0 };
          }
        }
        break;

      case 'response':
        if (this.advancePacket(dt) === 'arrived') {
          this.stats.bytesReceived += job.request.compressed.bytes;
          this.addLog('ok', `Response received at Field Hub (${job.hops} hops total), decompressed on site`);
          this.addLog('cache', `'${job.request.title}' stored in offline cache for future requests`);
          this.cache.add(job.request.id);
          this.finish(job, 'relay');
        }
        break;

      case 'drive':
        this.vehicle!.progress += dt / TIMING.driveDuration;
        if (this.vehicle!.progress >= 1) {
          this.addLog('ok', `Vehicle arrived at Field Hub: full ${job.request.original.label} delivered`);
          this.cache.add(job.request.id);
          this.finish(job, 'drive');
        }
        break;

      case 'queued':
        break;
    }
  }

  // ── Internals ─────────────────────────────────────────────────────────────

  private addLog(kind: LogKind, text: string, beacon?: BeaconInfo) {
    this.log.push({ id: this.nextId++, t: this.time, kind, text, beacon });
    if (this.log.length > MAX_LOG) this.log.splice(0, this.log.length - MAX_LOG);
  }

  private recomputeOffline() {
    this.offline = new Set(this.manualOffline);
    for (const n of NODES) if (this.isJammed(n.id)) this.offline.add(n.id);
    this.bestRoute = shortestPath(HUB_ID, GATEWAY_ID, this.offline);
    this.topologyVersion++;
  }

  private route(from: string, to: string) {
    return shortestPath(from, to, this.offline);
  }

  private processQueueJumps() {
    for (const job of this.queue) {
      if (job.jumpAt === null || this.time < job.jumpAt) continue;
      job.jumpAt = null;
      const firstNormal = this.queue.findIndex((j) => j.priority === 'normal');
      const idx = this.queue.indexOf(job);
      if (firstNormal !== -1 && firstNormal < idx) {
        const overtaken = this.queue.slice(firstNormal, idx).filter((j) => j.priority === 'normal');
        this.queue.splice(idx, 1);
        this.queue.splice(firstNormal, 0, job);
        this.addLog('crit', `CRITICAL '${job.request.title}' overtakes ${overtaken.map((j) => `'${j.request.title}'`).join(', ')} in queue`);
      }
      return;
    }
  }

  private startNext() {
    const job = this.queue.shift()!;
    job.phase = 'cache';
    job.startedAt = this.time;
    this.active = job;
    this.payload = null;
    this.phaseTimer = TIMING.cacheCheck;
    this.addLog(job.priority === 'critical' ? 'crit' : 'info', `Processing '${job.request.title}'${job.priority === 'critical' ? ' [CRITICAL]' : ''}: checking offline cache…`);
  }

  private afterCacheCheck(job: Job) {
    if (this.cache.has(job.request.id)) {
      this.addLog('cache', `Cache hit: '${job.request.title}' served from offline cache, no network needed`);
      this.finish(job, 'cache');
      return;
    }
    this.addLog('warn', `Cache miss: '${job.request.title}' not stored locally`);
    const beacon = encodeBeacon(job.id, job.request.docId, job.priority === 'critical');
    this.addLog('beacon', `Request beacon sent (${BEACON.sizeBytes} bytes, encrypted)`, beacon);
    this.stats.bytesSent += BEACON.sizeBytes;
    job.phase = 'request';
    this.packet = this.makePacket('request', HUB_ID, GATEWAY_ID, job);
  }

  private finish(job: Job, source: PayloadView['source']) {
    this.payload = {
      jobId: job.id,
      request: job.request,
      source,
      hops: job.hops,
      totalTime: this.time - job.startedAt,
    };
    this.active = null;
    this.packet = null;
    this.vehicle = null;
    this.idleGap = TIMING.gapBetweenJobs;
  }

  private makePacket(kind: PacketKind, from: string, to: string, job: Job): Packet {
    const p: Packet = {
      kind,
      at: from,
      to: null,
      progress: 0,
      dir: 1,
      dest: to,
      path: [from],
      trail: [from],
      waiting: false,
      bouncedFrom: null,
      critical: job.priority === 'critical',
    };
    this.planNext(p);
    return p;
  }

  /** Pick a route from the packet's current node, or start store-and-forward waiting. */
  private planNext(p: Packet, brokenNode?: string) {
    const np = this.route(p.at, p.dest);
    if (!np) {
      p.waiting = true;
      p.to = null;
      p.path = [p.at];
      const why = brokenNode ? `${shortName(brokenNode)} offline, ` : '';
      this.addLog('error', `${why}no route from ${shortName(p.at)} to ${shortName(p.dest)}: holding packet (store-and-forward)`);
      return;
    }
    if (brokenNode) this.addLog('warn', `${shortName(brokenNode)} offline → rerouting via ${shortName(np[1])}`);
    p.path = np;
    p.to = np[1];
    p.progress = 0;
    p.dir = 1;
  }

  private hopDuration(a: string, b: string, critical: boolean) {
    return (TIMING.perHopBase + distance(a, b) * TIMING.perUnit) * (critical ? TIMING.criticalFactor : 1);
  }

  private advancePacket(dt: number): 'arrived' | null {
    const p = this.packet;
    if (!p) return null;

    if (p.waiting) {
      const np = this.route(p.at, p.dest);
      if (!np) return null;
      p.waiting = false;
      p.path = np;
      p.to = np[1];
      p.progress = 0;
      this.addLog('ok', `Route restored: ${shortName(p.at)} releases stored packet via ${shortName(np[1])}`);
    }
    if (!p.to) return null;

    p.progress += (p.dir * dt) / this.hopDuration(p.at, p.to, p.critical);

    if (p.dir === -1 && p.progress <= 0) {
      const broken = p.bouncedFrom ?? undefined;
      p.bouncedFrom = null;
      p.progress = 0;
      p.to = null;
      this.planNext(p, broken);
      return null;
    }

    if (p.dir === 1 && p.progress >= 1) {
      const from = p.at;
      const to = p.to;
      p.at = to;
      p.to = null;
      p.progress = 0;
      p.trail.push(to);
      p.path = p.path.slice(1);
      if (p.kind !== 'fetch') {
        this.active!.hops++;
        const q = (NODE_BY_ID[from].linkQuality + NODE_BY_ID[to].linkQuality) / 2;
        const rssi = Math.round(-58 - (1 - q) * 55 - Math.random() * 5);
        this.addLog('muted', `${shortName(from)} → ${shortName(to)} hop ok · RSSI ${rssi} dBm`);
      } else {
        this.addLog('muted', `${shortName(from)} → ${shortName(to)} ${to === DATABASE_ID ? 'query sent' : 'document returned'}`);
      }
      if (to === p.dest) return 'arrived';

      const broken = p.path.find((n) => this.offline.has(n));
      if (broken || this.offline.has(p.at)) this.planNext(p, broken);
      else p.to = p.path[1];
    }
    return null;
  }

  /** React immediately when nodes go down while a packet is in flight. */
  private topologyChanged(before: Set<string>) {
    this.recomputeOffline();
    const p = this.packet;
    if (!p || p.waiting || !p.to || p.dir === -1) return;
    const newlyOff = [...this.offline].filter((n) => !before.has(n));
    if (!newlyOff.length) return;

    if (this.offline.has(p.to)) {
      p.dir = -1;
      p.bouncedFrom = p.to;
      this.addLog('warn', `${shortName(p.to)} went offline mid-hop: packet returning to ${shortName(p.at)}`);
      return;
    }
    const broken = p.path.slice(2).find((n) => this.offline.has(n));
    if (!broken) return;
    const np = this.route(p.to, p.dest);
    if (np) {
      p.path = [p.at, ...np];
      this.addLog('warn', `${shortName(broken)} offline → rerouting via ${shortName(np[1] ?? p.dest)}`);
    } else {
      this.addLog('error', `${shortName(broken)} offline: no alternative route beyond ${shortName(p.to)}`);
    }
  }
}
