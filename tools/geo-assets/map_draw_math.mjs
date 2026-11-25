// Pure 2D geometry helpers for map overlay drawing.
//
// Dependency-free on purpose: `render_map_scene.mjs` inlines this source into the headless
// page (with `export` keywords stripped), and Node unit tests import it directly. Points are
// screen-space `{x, y}` objects with y pointing down.

function pickOption(value, index, fallback) {
  if (Array.isArray(value)) return value[index] ?? fallback;
  return value ?? fallback;
}

function openRing(raw) {
  const ring = (raw || []).filter((p) => p && Number.isFinite(p.x) && Number.isFinite(p.y));
  if (ring.length > 1) {
    const a = ring[0];
    const b = ring[ring.length - 1];
    if (a.x === b.x && a.y === b.y) ring.pop();
  }
  return ring;
}

function ringLength(ring) {
  let len = 0;
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i];
    const b = ring[(i + 1) % ring.length];
    len += Math.hypot(b.x - a.x, b.y - a.y);
  }
  return len;
}

function walkRing(ring, start, dir, distance) {
  const n = ring.length;
  const out = [{ x: ring[start].x, y: ring[start].y }];
  let i = start;
  let remaining = distance;
  for (let step = 0; step < n && remaining > 0; step++) {
    const j = (i + dir + n) % n;
    const a = ring[i];
    const b = ring[j];
    const seg = Math.hypot(b.x - a.x, b.y - a.y);
    if (seg > 0 && seg >= remaining) {
      const t = remaining / seg;
      out.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
      return out;
    }
    out.push({ x: b.x, y: b.y });
    remaining -= seg;
    i = j;
  }
  return out;
}

/**
 * Partial perimeter paths for a border trace.
 *
 * Every ring is drawn by the same fraction of its own length, so all rings of a
 * MultiPolygon close together at `progress = 1`. With two heads, both start at the start
 * vertex and run in opposite directions, each covering half the drawn length.
 *
 * @param {Array<Array<{x:number,y:number}>>} rings rings in screen space (closing point optional)
 * @param {number} progress 0..1
 * @param {{heads?: 1|2, startIndex?: number|number[], direction?: 1|-1|Array<1|-1>}} [opts]
 *   `startIndex` and `direction` may be given per ring.
 * @returns {Array<Array<{x:number,y:number}>>} open polylines, or closed rings at progress 1
 */
export function perimeterPartialPaths(rings, progress, opts = {}) {
  const p = Math.max(0, Math.min(1, Number(progress) || 0));
  const heads = opts.heads === 1 ? 1 : 2;
  const out = [];
  if (p <= 0) return out;
  (rings || []).forEach((raw, ri) => {
    const ring = openRing(raw);
    const n = ring.length;
    if (n < 2) return;
    const startRaw = Math.round(Number(pickOption(opts.startIndex, ri, 0)) || 0);
    const start = ((startRaw % n) + n) % n;
    if (p >= 1) {
      const total = ringLength(ring);
      if (!(total > 0)) return;
      const closed = [];
      for (let k = 0; k <= n; k++) {
        const q = ring[(start + k) % n];
        closed.push({ x: q.x, y: q.y });
      }
      out.push(closed);
      return;
    }
    const total = ringLength(ring);
    if (!(total > 0)) return;
    const dir = Number(pickOption(opts.direction, ri, 1)) < 0 ? -1 : 1;
    if (heads === 1) {
      out.push(walkRing(ring, start, dir, p * total));
    } else {
      out.push(walkRing(ring, start, dir, (p * total) / 2));
      out.push(walkRing(ring, start, -dir, (p * total) / 2));
    }
  });
  return out;
}

/** Index of the ring vertex closest to `pt`. */
export function nearestVertexIndex(ring, pt) {
  let best = 0;
  let bestD = Infinity;
  (ring || []).forEach((q, i) => {
    const d = (q.x - pt.x) ** 2 + (q.y - pt.y) ** 2;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  });
  return best;
}

/** Shoelace area; positive for clockwise rings on screen (y down). */
export function signedArea(ring) {
  let sum = 0;
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i];
    const b = ring[(i + 1) % ring.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return sum / 2;
}

/**
 * Smallest upright rectangle with width/height ratio `aspect` that covers `bounds`, centred
 * on the bounds (used to cover-fit a flag over a territory).
 */
export function coverRect(bounds, aspect) {
  const bw = Math.max(1e-9, bounds.maxX - bounds.minX);
  const bh = Math.max(1e-9, bounds.maxY - bounds.minY);
  const a = Number.isFinite(aspect) && aspect > 0 ? aspect : 1;
  let w;
  let h;
  if (bw / bh > a) {
    w = bw;
    h = bw / a;
  } else {
    h = bh;
    w = bh * a;
  }
  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  return { x: cx - w / 2, y: cy - h / 2, w, h };
}

/**
 * Line width that follows the map scale: doubles per zoom level above `refZoom` when
 * `coupling` is 1, clamped to [minScale, maxScale] times `widthPx`. Without `refZoom` the
 * width stays constant on screen.
 */
export function scaledWidth(widthPx, zoom, refZoom = null, coupling = 1, minScale = 0.4, maxScale = 6) {
  if (
    refZoom === null ||
    refZoom === undefined ||
    refZoom === "" ||
    typeof refZoom === "boolean" ||
    !Number.isFinite(Number(refZoom))
  ) {
    return widthPx;
  }
  const scale = 2 ** ((Number(zoom) - Number(refZoom)) * Number(coupling ?? 1));
  if (!Number.isFinite(scale)) return widthPx;
  return widthPx * Math.max(minScale, Math.min(maxScale, scale));
}

/**
 * Leading edge of a linear wipe reveal across `bounds`. The mode names the travel direction:
 * "wipe_right" enters at the left edge, "wipe_left" at the right edge, "wipe_down" at the top,
 * and "wipe_up" at the bottom. `back` is the fully revealed side of the feathered edge and
 * `front` the fully hidden side, both measured along the travel axis (x when `horiz`).
 */
export function wipeFrontEdge(mode, progress, bounds, featherFrac = 0.08) {
  const horiz = mode === "wipe_left" || mode === "wipe_right";
  const lo = horiz ? bounds.minX : bounds.minY;
  const hi = horiz ? bounds.maxX : bounds.maxY;
  const feather = featherFrac * Math.max(1, hi - lo);
  const p = Math.max(0, Math.min(1, Number(progress) || 0));
  const fromLow = mode === "wipe_right" || mode === "wipe_down";
  const front = fromLow ? lo + p * (hi - lo + feather) : hi - p * (hi - lo + feather);
  const back = fromLow ? front - feather : front + feather;
  return { horiz, back, front };
}

// Radial zoom-blur amount for a frame: peaks on the first frame (in-cut) and the
// last frame (out-cut) and eases to zero over each window with a quadratic falloff.
// Returns the extra zoom fraction of the outermost blur copy, clamped to [0, 0.4].
export function cutBlurAmount(frame, totalFrames, fps, inS, outS, strength) {
  const s = Math.max(0, Math.min(0.4, Number(strength)));
  const total = Number(totalFrames);
  if (!Number.isFinite(s) || s <= 0 || !Number.isFinite(total) || total <= 0) return 0;
  const rate = Math.max(1, Number(fps) || 1);
  const side = (dist, windowS) => {
    if (!Number.isFinite(dist) || dist < 0) return 0;
    const w = Number(windowS) * rate;
    if (!Number.isFinite(w) || w <= 0) return 0;
    const x = dist / w;
    return x >= 1 ? 0 : s * (1 - x) * (1 - x);
  };
  const last = Math.max(0, total - 1);
  return Math.max(side(Number(frame), inS), side(last - Number(frame), outS));
}

// Cloth shading for a waving flag: gradient stops along the wave axis, each with a
// signed light value in [-amplitude, amplitude] (positive = highlight, negative =
// shadow). Two harmonics give an uneven ripple; the bands scroll towards higher
// offsets at "speed" cycles per second and repeat every 1 / speed seconds.
export function clothWaveStops(t, { amplitude = 0.22, cycles = 2.5, speed = 0.5, stops = 24 } = {}) {
  const ampRaw = Math.max(0, Math.min(0.6, Number(amplitude)));
  const amp = Number.isFinite(ampRaw) ? ampRaw : 0;
  const n = Math.max(2, Math.min(64, Math.round(Number(stops)) || 24));
  const c = Number.isFinite(Number(cycles)) ? Number(cycles) : 2.5;
  const v = Number.isFinite(Number(speed)) ? Number(speed) : 0.5;
  const time = Number.isFinite(Number(t)) ? Number(t) : 0;
  const out = [];
  for (let i = 0; i < n; i++) {
    const s = i / (n - 1);
    const ph = 2 * Math.PI * (c * s - v * time);
    const light = amp === 0 ? 0 : amp * (0.7 * Math.sin(ph) + 0.3 * Math.sin(2 * ph + 1.1));
    out.push({ offset: s, light });
  }
  return out;
}

function seededUnit(seed, k) {
  const x = Math.sin((seed + 1) * 12.9898 + k * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

// Radii of an organic, noise-edged reveal front sampled at "points" equal angles
// (index 0 at angle 0, counter-clockwise in screen space). The front never falls
// behind a plain radial reveal (min radius = progress * maxR), so it covers the
// bounds at progress 1; three seeded angular harmonics make the edge irregular and
// let it creep as it grows.
export function organicRevealRadii(progress, maxR, { points = 72, roughness = 0.22, seed = 1 } = {}) {
  const n = Math.max(8, Math.min(360, Math.round(Number(points)) || 72));
  const pRaw = Number(progress);
  const p = Number.isFinite(pRaw) ? Math.max(0, Math.min(1, pRaw)) : 0;
  const R = Math.max(0, Number(maxR) || 0);
  const rough = Math.max(0, Math.min(0.6, Number(roughness) || 0));
  const sd = Number.isFinite(Number(seed)) ? Number(seed) : 1;
  const base = (p * R) / (1 - rough);
  const harmonics = [
    { f: 3, w: 0.5 },
    { f: 5, w: 0.3 },
    { f: 8, w: 0.2 },
  ].map((h, k) => ({ ...h, ph: 2 * Math.PI * seededUnit(sd, k) + p * (1.5 + k) }));
  const out = [];
  for (let i = 0; i < n; i++) {
    const theta = (2 * Math.PI * i) / n;
    let noise = 0;
    for (const h of harmonics) noise += h.w * Math.sin(h.f * theta + h.ph);
    out.push(base * (1 + rough * noise));
  }
  return out;
}

function boxGap(a, b) {
  const dx = Math.max(0, a.minX - b.maxX, b.minX - a.maxX);
  const dy = Math.max(0, a.minY - b.maxY, b.minY - a.maxY);
  return Math.hypot(dx, dy);
}

function boxUnion(a, b) {
  return {
    minX: Math.min(a.minX, b.minX),
    minY: Math.min(a.minY, b.minY),
    maxX: Math.max(a.maxX, b.maxX),
    maxY: Math.max(a.maxY, b.maxY),
  };
}

// Group projected rings into landmass clusters: rings whose bounding boxes lie within
// gapFrac x the larger cluster's longest side join it, repeatedly, so an archipelago
// chains together while remote parts of a country (overseas regions, far islands)
// stay apart. Returns [{ bounds, area, rings: [ring indices] }], leading with the
// cluster whose bounds cover the most of the viewport ({ w, h } from the origin), or
// with the largest area when none is on screen. Non-finite points are ignored.
export function ringClusters(rings, { gapFrac = 0.5, viewport = null } = {}) {
  let clusters = [];
  (rings || []).forEach((ring, idx) => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const pts = (ring || []).filter((p) => p && Number.isFinite(p.x) && Number.isFinite(p.y));
    for (const p of pts) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    if (!Number.isFinite(minX)) return;
    clusters.push({ bounds: { minX, minY, maxX, maxY }, area: Math.abs(signedArea(pts)), rings: [idx] });
  });
  const size = (b) => Math.max(b.maxX - b.minX, b.maxY - b.minY);
  let merged = true;
  while (merged && clusters.length > 1) {
    merged = false;
    clusters.sort((a, b) => b.area - a.area);
    outer: for (let i = 0; i < clusters.length; i++) {
      for (let j = i + 1; j < clusters.length; j++) {
        const a = clusters[i];
        const b = clusters[j];
        if (boxGap(a.bounds, b.bounds) <= gapFrac * Math.max(size(a.bounds), size(b.bounds))) {
          clusters[i] = { bounds: boxUnion(a.bounds, b.bounds), area: a.area + b.area, rings: [...a.rings, ...b.rings] };
          clusters.splice(j, 1);
          merged = true;
          break outer;
        }
      }
    }
  }
  const visible = (b) => {
    if (!viewport) return 0;
    const w = Math.min(b.maxX, viewport.w) - Math.max(b.minX, 0);
    const h = Math.min(b.maxY, viewport.h) - Math.max(b.minY, 0);
    return w > 0 && h > 0 ? w * h : 0;
  };
  clusters = clusters.map((c) => ({ ...c, rings: [...c.rings].sort((x, y) => x - y) }));
  return clusters.sort((a, b) => visible(b.bounds) - visible(a.bounds) || b.area - a.area);
}

/**
 * Exterior and hole rings of a Polygon, MultiPolygon, Feature, FeatureCollection or feature list,
 * in their source coordinates. Rings with fewer than three positions are dropped; other geometry
 * types contribute nothing.
 *
 * @returns {{outer: Array<Array<number[]>>, inner: Array<Array<number[]>>}}
 */
export function polygonRings(geom) {
  const outer = [];
  const inner = [];
  const addPolygon = (rings) => {
    (rings || []).forEach((ring, i) => {
      if (!Array.isArray(ring) || ring.length < 3) return;
      (i === 0 ? outer : inner).push(ring);
    });
  };
  const collect = (g) => {
    if (!g) return;
    if (Array.isArray(g)) {
      for (const item of g) collect(item);
      return;
    }
    if (g.type === "Feature" || (!g.type && g.geometry)) collect(g.geometry);
    else if (g.type === "FeatureCollection") collect(g.features);
    else if (g.type === "GeometryCollection") collect(g.geometries);
    else if (g.type === "Polygon") addPolygon(g.coordinates);
    else if (g.type === "MultiPolygon") for (const poly of g.coordinates || []) addPolygon(poly);
  };
  collect(geom);
  return { outer, inner };
}

function clipPlane(verts, fn) {
  if (!verts || verts.length < 3) return [];
  const out = [];
  for (let i = 0; i < verts.length; i++) {
    const a = verts[i];
    const b = verts[(i + 1) % verts.length];
    const fa = fn(a);
    const fb = fn(b);
    const inA = fa >= 0;
    const inB = fb >= 0;
    if (inA && inB) {
      out.push(b);
    } else if (inA && !inB) {
      const t = Math.max(0, Math.min(1, fa / (fa - fb)));
      out.push({
        x: a.x + t * (b.x - a.x),
        y: a.y + t * (b.y - a.y),
        z: a.z + t * (b.z - a.z),
        w: a.w + t * (b.w - a.w),
      });
    } else if (!inA && inB) {
      const t = Math.max(0, Math.min(1, fa / (fa - fb)));
      out.push({
        x: a.x + t * (b.x - a.x),
        y: a.y + t * (b.y - a.y),
        z: a.z + t * (b.z - a.z),
        w: a.w + t * (b.w - a.w),
      });
      out.push(b);
    }
  }
  return out;
}

/**
 * Sutherland-Hodgman homogeneous clip-space polygon clipping against the camera
 * near frustum (`w >= eps` and `z + w >= 0`). Prevents perspective projection
 * wrap-around glitches when pitched maps traverse vertices behind the camera.
 *
 * @param {Array<{x:number,y:number,z:number,w:number}>} verts
 * @param {number} [eps=1e-4]
 * @returns {Array<{x:number,y:number,z:number,w:number}>}
 */
export function clipHomogeneousRing(verts, eps = 1e-4) {
  if (!Array.isArray(verts) || verts.length < 3) return [];
  const open = verts.filter(
    (v) => v && Number.isFinite(v.x) && Number.isFinite(v.y) && Number.isFinite(v.z) && Number.isFinite(v.w)
  );
  if (open.length > 1) {
    const f = open[0];
    const l = open[open.length - 1];
    if (f.x === l.x && f.y === l.y && f.z === l.z && f.w === l.w) open.pop();
  }
  if (open.length < 3) return [];
  const e = Number.isFinite(Number(eps)) && Number(eps) > 0 ? Number(eps) : 1e-4;
  const posW = clipPlane(open, (v) => v.w - e);
  if (posW.length < 3) return [];
  return clipPlane(posW, (v) => v.z + v.w);
}

function clipPolylineSegment(a, b, fn) {
  const fa = fn(a);
  const fb = fn(b);
  const inA = fa >= 0;
  const inB = fb >= 0;
  if (!inA && !inB) return null;
  if (inA && inB) return [a, b];
  const t = Math.max(0, Math.min(1, fa / (fa - fb)));
  const hit = {
    x: a.x + t * (b.x - a.x),
    y: a.y + t * (b.y - a.y),
    z: a.z + t * (b.z - a.z),
    w: a.w + t * (b.w - a.w),
  };
  return inA ? [a, hit] : [hit, b];
}

/**
 * Clip an open homogeneous clip-space polyline against the camera near frustum
 * (`w >= eps` and `z + w >= 0`). Returns an array of contiguous sub-polylines
 * (each length >= 2), splitting cleanly when the path exits and re-enters the frustum.
 *
 * @param {Array<{x:number,y:number,z:number,w:number}>} verts
 * @param {number} [eps=1e-4]
 * @returns {Array<Array<{x:number,y:number,z:number,w:number}>>}
 */
export function clipHomogeneousPolyline(verts, eps = 1e-4) {
  if (!Array.isArray(verts) || verts.length < 2) return [];
  const e = Number.isFinite(Number(eps)) && Number(eps) > 0 ? Number(eps) : 1e-4;
  const out = [];
  let cur = [];
  const pushVertex = (v) => {
    const prev = cur[cur.length - 1];
    if (
      !prev ||
      Math.abs(prev.x - v.x) > 1e-9 ||
      Math.abs(prev.y - v.y) > 1e-9 ||
      Math.abs(prev.z - v.z) > 1e-9 ||
      Math.abs(prev.w - v.w) > 1e-9
    ) {
      cur.push(v);
    }
  };
  for (let i = 0; i < verts.length - 1; i++) {
    const a = verts[i];
    const b = verts[i + 1];
    if (
      !a ||
      !b ||
      !Number.isFinite(a.w) ||
      !Number.isFinite(b.w) ||
      !Number.isFinite(a.x) ||
      !Number.isFinite(b.x)
    ) {
      if (cur.length >= 2) out.push(cur);
      cur = [];
      continue;
    }
    const segW = clipPolylineSegment(a, b, (v) => v.w - e);
    if (!segW) {
      if (cur.length >= 2) out.push(cur);
      cur = [];
      continue;
    }
    const segZ = clipPolylineSegment(segW[0], segW[1], (v) => v.z + v.w);
    if (!segZ) {
      if (cur.length >= 2) out.push(cur);
      cur = [];
      continue;
    }
    if (cur.length > 0) {
      const last = cur[cur.length - 1];
      const gap =
        Math.abs(last.x - segZ[0].x) > 1e-6 ||
        Math.abs(last.y - segZ[0].y) > 1e-6 ||
        Math.abs(last.w - segZ[0].w) > 1e-6;
      if (gap) {
        if (cur.length >= 2) out.push(cur);
        cur = [];
      }
    }
    pushVertex(segZ[0]);
    pushVertex(segZ[1]);
  }
  if (cur.length >= 2) out.push(cur);
  return out;
}
