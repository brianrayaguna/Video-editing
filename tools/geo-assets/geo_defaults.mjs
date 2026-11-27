/**
 * Neutral, episode-agnostic geospatial defaults and environment-variable parsers
 * shared across offline cartography tools.
 */

export const DEFAULT_MAP_CENTER = Object.freeze([0, 0]);
export const DEFAULT_DEM_ZOOMS = Object.freeze([4, 5, 6, 7]);
export const DEFAULT_DEM_BOUNDS = Object.freeze([-180, -85, 180, 85]);

/**
 * Parse a `"lng,lat"` environment value or return a copy of `fallback` (`[0, 0]`).
 */
export function parseCenterEnv(raw, fallback = DEFAULT_MAP_CENTER) {
  if (raw == null || String(raw).trim() === "") {
    return [...fallback];
  }
  const parts = String(raw)
    .split(",")
    .map((s) => Number(s.trim()));
  if (
    parts.length !== 2 ||
    !Number.isFinite(parts[0]) ||
    !Number.isFinite(parts[1]) ||
    parts[0] < -180 ||
    parts[0] > 180 ||
    parts[1] < -90 ||
    parts[1] > 90
  ) {
    throw new Error(
      `Invalid CENTER "${raw}": expected "lng,lat" within [-180,180] and [-90,90].`
    );
  }
  return parts;
}

/**
 * Parse a required `"minLon,minLat,maxLon,maxLat"` bounding-box string.
 */
export function parseBboxEnv(raw) {
  if (raw == null || String(raw).trim() === "") {
    throw new Error(
      'Missing required BBOX env var: pass BBOX="minLon,minLat,maxLon,maxLat" (e.g. BBOX="-10,35,5,45").'
    );
  }
  const parts = String(raw)
    .split(",")
    .map((s) => Number(s.trim()));
  if (parts.length !== 4 || !parts.every(Number.isFinite)) {
    throw new Error(
      `Invalid BBOX "${raw}": expected four finite numbers "minLon,minLat,maxLon,maxLat".`
    );
  }
  const [minLon, minLat, maxLon, maxLat] = parts;
  if (
    minLon < -180 ||
    maxLon > 180 ||
    minLon >= maxLon ||
    minLat < -85.0511 ||
    maxLat > 85.0511 ||
    minLat >= maxLat
  ) {
    throw new Error(
      `Invalid BBOX "${raw}": require -180 <= minLon < maxLon <= 180 and -85.0511 <= minLat < maxLat <= 85.0511.`
    );
  }
  return parts;
}
