/**
 * Deterministic binary SFNT (TrueType/OpenType) metadata reader extracting
 * typographic family names (`name` table) and weight ranges (`fvar` / `OS/2`).
 */

import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";

const ttfMetadataCache = new Map();

/**
 * Parse binary SFNT `fvar`, `OS/2`, and `name` tables for a local font file.
 * @param {string} filePath
 * @returns {{ familyName: string | null, weightAxis: { isVariable: boolean, minWeight: number, maxWeight: number } | null }}
 */
export function readTtfMetadata(filePath) {
  try {
    if (!existsSync(filePath)) {
      return { familyName: null, weightAxis: null };
    }
    const stat = statSync(filePath);
    if (!stat.isFile()) {
      return { familyName: null, weightAxis: null };
    }
    const cacheKey = `${resolve(filePath)}::${stat.mtimeMs}::${stat.size}`;
    const cached = ttfMetadataCache.get(cacheKey);
    if (cached) return cached;

    const buf = readFileSync(filePath);
    let weightAxis = null;
    let familyName = null;
    if (buf.length >= 12) {
      const numTables = buf.readUInt16BE(4);
      let fvarOff = 0;
      let os2Off = 0;
      let nameOffset = 0;
      let nameLength = 0;
      for (let i = 0; i < numTables; i += 1) {
        const rec = 12 + i * 16;
        if (rec + 16 > buf.length) break;
        const tag = buf.toString("ascii", rec, rec + 4);
        if (tag === "fvar") fvarOff = buf.readUInt32BE(rec + 8);
        else if (tag === "OS/2") os2Off = buf.readUInt32BE(rec + 8);
        else if (tag === "name") {
          nameOffset = buf.readUInt32BE(rec + 8);
          nameLength = buf.readUInt32BE(rec + 12);
        }
      }
      if (fvarOff && fvarOff + 12 <= buf.length) {
        const axesOff = buf.readUInt16BE(fvarOff + 4);
        const axisCount = buf.readUInt16BE(fvarOff + 8);
        const axisSize = buf.readUInt16BE(fvarOff + 10);
        for (let i = 0; i < axisCount; i += 1) {
          const off = fvarOff + axesOff + i * axisSize;
          if (off + 16 > buf.length) break;
          const axisTag = buf.toString("ascii", off, off + 4);
          if (axisTag === "wght") {
            const minW = Math.max(1, Math.min(1000, Math.round(buf.readInt32BE(off + 4) / 65536)));
            const maxW = Math.max(minW, Math.min(1000, Math.round(buf.readInt32BE(off + 12) / 65536)));
            weightAxis = { isVariable: true, minWeight: minW, maxWeight: maxW };
            break;
          }
        }
      }
      if (!weightAxis && os2Off && os2Off + 6 <= buf.length) {
        const w = Math.max(100, Math.min(1000, buf.readUInt16BE(os2Off + 4)));
        weightAxis = { isVariable: false, minWeight: w, maxWeight: w };
      }
      if (nameOffset && nameOffset + 6 <= buf.length && nameLength >= 6) {
        const count = buf.readUInt16BE(nameOffset + 2);
        const strOffset = nameOffset + buf.readUInt16BE(nameOffset + 4);
        let fallbackName = null;
        for (let i = 0; i < count; i += 1) {
          const rec = nameOffset + 6 + i * 12;
          if (rec + 12 > buf.length) break;
          const platformId = buf.readUInt16BE(rec);
          const nameId = buf.readUInt16BE(rec + 6);
          if (nameId !== 1 && nameId !== 16) continue;
          const len = buf.readUInt16BE(rec + 8);
          const off = strOffset + buf.readUInt16BE(rec + 10);
          if (off + len > buf.length) continue;
          if ((platformId === 3 || platformId === 0) && len % 2 !== 0) continue;
          const slice = Buffer.from(buf.subarray(off, off + len));
          const decoded =
            platformId === 3 || platformId === 0
              ? slice.swap16().toString("utf16le").replace(/\0/g, "").trim()
              : slice.toString("latin1").trim();
          if (!decoded) continue;
          if (nameId === 16) {
            familyName = decoded;
            break;
          }
          fallbackName ??= decoded;
        }
        familyName ??= fallbackName;
      }
    }
    const meta = { familyName, weightAxis };
    ttfMetadataCache.set(cacheKey, meta);
    return meta;
  } catch {
    return { familyName: null, weightAxis: null };
  }
}

/**
 * Convenience helper returning only the SFNT `wght` axis or `OS/2` static weight info.
 * @param {string} filePath
 */
export function readTtfWeightAxis(filePath) {
  return readTtfMetadata(filePath).weightAxis;
}
