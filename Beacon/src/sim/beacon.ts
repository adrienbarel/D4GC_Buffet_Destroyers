import { BEACON } from '../data/network';

export interface BeaconInfo {
  hex: string;
  decoded: Record<string, string>;
}

function hashString(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

function mulberry32(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Builds a fake 32-byte encrypted beacon: 4 header bytes (magic, version, flags)
 * followed by pseudo-random "ciphertext + auth tag" derived from the inputs.
 */
export function encodeBeacon(seed: number, docId: string, critical: boolean, kind: 'REQ' | 'RSP' = 'REQ'): BeaconInfo {
  const rand = mulberry32(hashString(docId) ^ (seed * 2654435761));
  const bytes = [0xbe, 0xac, 0x01, (critical ? 0x80 : 0x00) | (kind === 'RSP' ? 0x01 : 0x00)];
  while (bytes.length < BEACON.sizeBytes) bytes.push(Math.floor(rand() * 256));
  return {
    hex: bytes.map((b) => b.toString(16).padStart(2, '0').toUpperCase()).join(' '),
    decoded: {
      hubId: BEACON.hubId,
      regionCode: BEACON.regionCode,
      docId,
      priority: critical ? 'CRITICAL' : 'NORMAL',
    },
  };
}
