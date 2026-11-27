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
      !Number.isFinite(b.x) ||
      !Number.isFinite(a.y) ||
      !Number.isFinite(b.y) ||
      !Number.isFinite(a.z) ||
      !Number.isFinite(b.z)
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

function clampUnit(u) {
  const n = Number(u);
  if (!Number.isFinite(n) || n <= 0) return 0;
  if (n >= 1) return 1;
  return n;
}

/**
 * Unit-domain cubic Bezier easing curve solver using Newton-Raphson iteration
 * with a deterministic bisection fallback.
 */
export function cubicBezier(x1, y1, x2, y2) {
  const rawX1 = Number(x1);
  const cx1 = Number.isFinite(rawX1) ? Math.max(0, Math.min(1, rawX1)) : 0;
  const cy1 = Number.isFinite(Number(y1)) ? Number(y1) : 0;
  const rawX2 = Number(x2);
  const cx2 = Number.isFinite(rawX2) ? Math.max(0, Math.min(1, rawX2)) : 1;
  const cy2 = Number.isFinite(Number(y2)) ? Number(y2) : 1;
  const sampleX = (t) => ((3 * (cx1 - cx2) + 1) * t + 3 * (cx2 - 2 * cx1)) * t * t + 3 * cx1 * t;
  const sampleY = (t) => ((3 * (cy1 - cy2) + 1) * t + 3 * (cy2 - 2 * cy1)) * t * t + 3 * cy1 * t;
  const slopeX = (t) => (3 * (3 * (cx1 - cx2) + 1) * t + 6 * (cx2 - 2 * cx1)) * t + 3 * cx1;
  return (u) => {
    const x = clampUnit(u);
    if (x === 0) return 0;
    if (x === 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) {
      const err = sampleX(t) - x;
      if (Math.abs(err) < 1e-7) return sampleY(t);
      const d = slopeX(t);
      if (Math.abs(d) < 1e-6) break;
      const next = t - err / d;
      if (next < 0 || next > 1) break;
      t = next;
    }
    let lo = 0;
    let hi = 1;
    t = x;
    for (let i = 0; i < 20; i++) {
      const err = sampleX(t) - x;
      if (Math.abs(err) < 1e-7) break;
      if (err < 0) lo = t;
      else hi = t;
      t = 0.5 * (lo + hi);
    }
    return sampleY(t);
  };
}

export const editorialOut = cubicBezier(0.16, 1, 0.3, 1);

export function easeOutQuint(u) {
  const p = clampUnit(u);
  return 1 - (1 - p) ** 5;
}

export function easeInOutQuart(u) {
  const p = clampUnit(u);
  return p < 0.5 ? 8 * p * p * p * p : 1 - ((-2 * p + 2) ** 4) / 2;
}

export function easeInQuad(u) {
  const p = clampUnit(u);
  return p * p;
}

/**
 * Closed-form analytical damped spring evaluated at normalized time `tNorm` in [0, 1].
 * Seek-safe for arbitrary frame access, hitting exact 0 at tNorm <= 0 and exact 1 at tNorm >= 1.
 */
export function springClosedForm(tNorm, { stiffness = 180, damping = 22, mass = 1, durationS = 0.65 } = {}) {
  const u = clampUnit(tNorm);
  if (u === 0) return 0;
  if (u === 1) return 1;
  const k = Math.max(1, Number(stiffness) || 180);
  const c = Math.max(0.1, Number(damping) || 22);
  const m = Math.max(0.05, Number(mass) || 1);
  const dur = Math.max(0.05, Number(durationS) || 0.65);
  const t = u * dur;
  const w0 = Math.sqrt(k / m);
  const zeta = c / (2 * Math.sqrt(k * m));
  let residual;
  if (zeta < 1 - 1e-4) {
    const wd = w0 * Math.sqrt(1 - zeta * zeta);
    residual = Math.exp(-zeta * w0 * t) * (Math.cos(wd * t) + ((zeta * w0) / wd) * Math.sin(wd * t));
  } else if (zeta > 1 + 1e-4) {
    const sq = Math.sqrt(zeta * zeta - 1);
    const s1 = -w0 * (zeta - sq);
    const s2 = -w0 * (zeta + sq);
    residual = (s2 * Math.exp(s1 * t) - s1 * Math.exp(s2 * t)) / (s2 - s1);
  } else {
    residual = Math.exp(-w0 * t) * (1 + w0 * t);
  }
  const settleFade = 1 - u * u * u * u;
  return 1 - residual * settleFade;
}

/** Unified named easing evaluator used across overlay and 3D animations. */
export function evalEase(name, u) {
  const p = clampUnit(u);
  if (p === 0) return 0;
  if (p === 1) return 1;
  switch (name) {
    case "linear":
      return p;
    case "out":
      return 1 - (1 - p) ** 3;
    case "in_out":
      return p < 0.5 ? 4 * p * p * p : 1 - ((-2 * p + 2) ** 3) / 2;
    case "expo_out":
      return 1 - 2 ** (-10 * p);
    case "quint_out":
      return easeOutQuint(p);
    case "quart_in_out":
      return easeInOutQuart(p);
    case "in_quad":
      return easeInQuad(p);
    case "in_cubic":
      return p * p * p;
    case "editorial_out":
      return editorialOut(p);
    case "spring_crisp":
      return springClosedForm(p, { stiffness: 260, damping: 33, mass: 1, durationS: 0.55 });
    case "spring_tactile":
      return springClosedForm(p, { stiffness: 180, damping: 20, mass: 1, durationS: 0.75 });
    case "spring_playful":
      return springClosedForm(p, { stiffness: 220, damping: 14, mass: 1, durationS: 0.85 });
    default:
      return editorialOut(p);
  }
}

const MERC_MAX_LAT = 85.05112877980659;

/** Convert `[lng, lat]` (or `{lng, lat}`) to normalized Web Mercator `[0..1]` space. */
export function lngLatToMercNorm(coord) {
  const rawLng = Array.isArray(coord) ? Number(coord[0]) : Number(coord?.lng);
  const rawLat = Array.isArray(coord) ? Number(coord[1]) : Number(coord?.lat);
  const lng = Number.isFinite(rawLng) ? rawLng : 0;
  const lat = Number.isFinite(rawLat) ? Math.max(-MERC_MAX_LAT, Math.min(MERC_MAX_LAT, rawLat)) : 0;
  const sinLat = Math.sin((lat * Math.PI) / 180);
  const x = (lng + 180) / 360;
  const y = 0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI);
  return { x, y };
}

/** Convert normalized Web Mercator `(mx, my)` back to `[lng, lat]`. */
export function mercNormToLngLat(mx, my) {
  const x = Number.isFinite(Number(mx)) ? Number(mx) : 0.5;
  const y = Number.isFinite(Number(my)) ? Math.max(1e-7, Math.min(1 - 1e-7, Number(my))) : 0.5;
  const lng = x * 360 - 180;
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180) / Math.PI;
  return [lng, lat];
}

function ringLLToMercUnwrapped(ringLL) {
  const out = [];
  let prevX = null;
  for (const c of ringLL || []) {
    if (!c) continue;
    const rawLng = Array.isArray(c) ? Number(c[0]) : Number(c.lng);
    const rawLat = Array.isArray(c) ? Number(c[1]) : Number(c.lat);
    if (!Number.isFinite(rawLng) || !Number.isFinite(rawLat)) continue;
    const m = lngLatToMercNorm([rawLng, rawLat]);
    if (prevX !== null) {
      while (m.x - prevX > 0.5) m.x -= 1;
      while (m.x - prevX < -0.5) m.x += 1;
    }
    prevX = m.x;
    out.push(m);
  }
  return openRing(out);
}

function extractTailByLength(pts, tailLen) {
  if (!pts || pts.length < 2 || !(tailLen > 0)) return [];
  const rev = [pts[pts.length - 1]];
  let rem = tailLen;
  for (let i = pts.length - 1; i > 0 && rem > 0; i--) {
    const b = pts[i];
    const a = pts[i - 1];
    const seg = Math.hypot(b.x - a.x, b.y - a.y);
    if (seg > 0 && seg >= rem) {
      const t = rem / seg;
      rev.push({ x: b.x + (a.x - b.x) * t, y: b.y + (a.y - b.y) * t });
      rem = 0;
      break;
    }
    rev.push(a);
    rem -= seg;
  }
  rev.reverse();
  return rev;
}

/**
 * World-space Web Mercator arc-length perimeter border trace.
 * Keeps trace speed constant on the ground regardless of camera pitch or zoom,
 * and emits trailing comet segments at advancing trace tips while `0 < progress < 1`.
 */
export function perimeterPartialPathsLngLat(ringsLL, progress, opts = {}) {
  const p = clampUnit(progress);
  if (p <= 0) return { paths: [], comets: [] };
  const heads = opts.heads === 1 ? 1 : 2;
  const cometFrac = Math.max(0, Math.min(0.5, Number(opts.cometFraction ?? 0.05) || 0));
  const mercRings = [];
  const ringIndices = [];
  (ringsLL || []).forEach((raw, ri) => {
    const m = ringLLToMercUnwrapped(raw);
    if (m.length >= 2) {
      mercRings.push(m);
      ringIndices.push(ri);
    }
  });
  const paths = [];
  const comets = [];
  mercRings.forEach((ring, idx) => {
    const ri = ringIndices[idx];
    const n = ring.length;
    const total = ringLength(ring);
    if (!(total > 0)) return;
    const startRaw = Math.round(Number(pickOption(opts.startIndex, ri, 0)) || 0);
    const start = ((startRaw % n) + n) % n;
    if (p >= 1) {
      const closed = [];
      for (let k = 0; k <= n; k++) {
        const q = ring[(start + k) % n];
        closed.push(mercNormToLngLat(q.x, q.y));
      }
      paths.push(closed);
      return;
    }
    const dir = Number(pickOption(opts.direction, ri, 1)) < 0 ? -1 : 1;
    const pushWalk = (dist, walkDir) => {
      const walked = walkRing(ring, start, walkDir, dist);
      if (walked.length < 2) return;
      paths.push(walked.map((q) => mercNormToLngLat(q.x, q.y)));
      if (cometFrac > 0) {
        const cometLen = Math.min(dist, total * cometFrac);
        const tail = extractTailByLength(walked, cometLen);
        if (tail.length >= 2) {
          comets.push(tail.map((q) => mercNormToLngLat(q.x, q.y)));
        }
      }
    };
    if (heads === 1) {
      pushWalk(p * total, dir);
    } else {
      pushWalk((p * total) / 2, dir);
      pushWalk((p * total) / 2, -dir);
    }
  });
  return { paths, comets };
}

/**
 * Extract a travelling arc-length window along each ring in Mercator space
 * (wrapping seamlessly around [0, 1]), used for perimeter rim glints.
 */
export function perimeterWindowPathsLngLat(ringsLL, startFrac, spanFrac, opts = {}) {
  const span = Math.max(0, Math.min(1, Number(spanFrac) || 0));
  if (span <= 0) return [];
  const rawStart = Number(startFrac);
  const startWrapped = Number.isFinite(rawStart) ? ((rawStart % 1) + 1) % 1 : 0;
  const dir = Number(opts.direction ?? 1) < 0 ? -1 : 1;
  const out = [];
  for (const raw of ringsLL || []) {
    const ring = ringLLToMercUnwrapped(raw);
    const n = ring.length;
    if (n < 2) continue;
    const total = ringLength(ring);
    if (!(total > 0)) continue;
    const startDist = startWrapped * total;
    const wantLen = span * total;
    // Locate starting vertex + fractional offset along ring.
    let i = 0;
    let rem = startDist;
    for (let step = 0; step < n; step++) {
      const j = (i + dir + n) % n;
      const seg = Math.hypot(ring[j].x - ring[i].x, ring[j].y - ring[i].y);
      if (seg > 0 && rem <= seg) {
        const t0 = rem / seg;
        const pts = [{ x: ring[i].x + (ring[j].x - ring[i].x) * t0, y: ring[i].y + (ring[j].y - ring[i].y) * t0 }];
        let left = wantLen;
        let cur = pts[0];
        let nextIdx = j;
        let guard = 0;
        while (left > 1e-12 && guard <= n + 2) {
          guard++;
          const target = ring[nextIdx];
          const d = Math.hypot(target.x - cur.x, target.y - cur.y);
          if (d > 0 && d >= left) {
            const tf = left / d;
            pts.push({ x: cur.x + (target.x - cur.x) * tf, y: cur.y + (target.y - cur.y) * tf });
            left = 0;
            break;
          }
          pts.push({ x: target.x, y: target.y });
          left -= d;
          cur = target;
          nextIdx = (nextIdx + dir + n) % n;
        }
        if (pts.length >= 2) out.push(pts.map((q) => mercNormToLngLat(q.x, q.y)));
        break;
      }
      rem -= seg;
      i = j;
    }
  }
  return out;
}

/**
 * Compute world-space Mercator hatch spacing with logarithmic octave blending
 * so surface-locked hatch lines never alias when zooming out or pop when zooming in.
 */
export function computeOctaveHatchSpacing(baseSpacingPx, zoom, refZoom = null) {
  const px = Math.max(2, Number(baseSpacingPx) || 12);
  const z = Number.isFinite(Number(zoom)) ? Number(zoom) : 6;
  const rz =
    refZoom !== null && refZoom !== undefined && refZoom !== "" && Number.isFinite(Number(refZoom))
      ? Number(refZoom)
      : z;
  const dz = z - rz;
  const octave = Math.floor(dz);
  const frac = dz - octave;
  const primarySpacingMerc = px / (512 * 2 ** (rz + octave));
  return {
    primarySpacingMerc,
    subSpacingMerc: primarySpacingMerc * 0.5,
    subAlpha: clampUnit(frac),
    octave,
    screenSpacingPx: primarySpacingMerc * 512 * 2 ** z,
  };
}

/**
 * Generate parallel world-space Mercator hatch lines covering `boundsLngLat`,
 * quantized to the global binary Mercator grid so lines stay pinned to Earth.
 */
export function buildWorldHatchLines(
  boundsLngLat,
  { angleDeg = 45, spacingMerc = 0.001, maxLines = 180, padFrac = 0.15, segmentsPerLine = 8 } = {}
) {
  if (!boundsLngLat) return [];
  const minLng = Number(boundsLngLat.minLng);
  const maxLng = Number(boundsLngLat.maxLng);
  const minLat = Math.max(-82, Math.min(82, Number(boundsLngLat.minLat)));
  const maxLat = Math.max(-82, Math.min(82, Number(boundsLngLat.maxLat)));
  if (![minLng, maxLng, minLat, maxLat].every(Number.isFinite)) return [];
  const c00 = lngLatToMercNorm([minLng, maxLat]);
  const c11 = lngLatToMercNorm([maxLng, minLat]);
  const minX = Math.min(c00.x, c11.x);
  const maxX = Math.max(c00.x, c11.x);
  const minY = Math.min(c00.y, c11.y);
  const maxY = Math.max(c00.y, c11.y);
  const pad = Math.max(0, Number(padFrac) || 0);
  const spanX = Math.max(1e-7, maxX - minX);
  const spanY = Math.max(1e-7, maxY - minY);
  const bx0 = minX - spanX * pad;
  const bx1 = maxX + spanX * pad;
  const by0 = Math.max(1e-6, minY - spanY * pad);
  const by1 = Math.min(1 - 1e-6, maxY + spanY * pad);

  const rad = ((Number.isFinite(Number(angleDeg)) ? Number(angleDeg) : 45) * Math.PI) / 180;
  // Angle 45 deg tilts lower-left to upper-right in y-down Mercator space.
  const ux = Math.cos(rad);
  const uy = -Math.sin(rad);
  const nx = Math.sin(rad);
  const ny = Math.cos(rad);

  const corners = [
    [bx0, by0],
    [bx1, by0],
    [bx1, by1],
    [bx0, by1],
  ];
  let nMin = Infinity;
  let nMax = -Infinity;
  let uMin = Infinity;
  let uMax = -Infinity;
  for (const [cx, cy] of corners) {
    const nv = cx * nx + cy * ny;
    const uv = cx * ux + cy * uy;
    if (nv < nMin) nMin = nv;
    if (nv > nMax) nMax = nv;
    if (uv < uMin) uMin = uv;
    if (uv > uMax) uMax = uv;
  }

  const cap = Math.max(2, Math.min(400, Math.round(Number(maxLines) || 180)));
  let step = Number.isFinite(Number(spacingMerc)) && Number(spacingMerc) > 0 ? Number(spacingMerc) : (nMax - nMin) / 20;
  if (!(step > 0)) return [];
  while ((nMax - nMin) / step + 1 > cap) {
    step *= 2;
  }
  const kStart = Math.floor(nMin / step);
  const kEnd = Math.ceil(nMax / step);
  const segs = Math.max(2, Math.min(48, Math.round(Number(segmentsPerLine) || 8)));

  const lines = [];
  let idx = 0;
  for (let k = kStart; k <= kEnd && lines.length < cap; k++) {
    const nVal = k * step;
    const coords = [];
    for (let s = 0; s <= segs; s++) {
      const uVal = uMin + ((uMax - uMin) * s) / segs;
      const mx = nVal * nx + uVal * ux;
      const my = nVal * ny + uVal * uy;
      coords.push(mercNormToLngLat(mx, my));
    }
    lines.push({ index: idx++, gridK: k, isSub: Math.abs(k) % 2 === 1, coords });
  }
  return lines;
}

/** Slice a `[lng, lat]` polyline by normalized arc-length fraction `[fromFrac, toFrac]`. */
export function slicePolylineFraction(coords, fromFrac, toFrac) {
  if (!Array.isArray(coords) || coords.length < 2) return [];
  const f0 = clampUnit(fromFrac);
  const f1 = clampUnit(toFrac);
  if (f1 <= f0 + 1e-7) return [];
  if (f0 <= 1e-7 && f1 >= 1 - 1e-7) return coords;
  const n = coords.length - 1;
  const out = [];
  const sampleAt = (frac) => {
    const pos = frac * n;
    const i = Math.min(n - 1, Math.max(0, Math.floor(pos)));
    const t = pos - i;
    const a = coords[i];
    const b = coords[i + 1];
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  };
  out.push(sampleAt(f0));
  const iStart = Math.floor(f0 * n) + 1;
  const iEnd = Math.ceil(f1 * n) - 1;
  for (let i = iStart; i <= iEnd; i++) {
    if (i > 0 && i < coords.length) out.push(coords[i]);
  }
  out.push(sampleAt(f1));
  return out;
}

/**
 * Deterministic per-line reveal state for progressive interior hatching and contours.
 */
export function hatchLineRevealState(
  lineIndex,
  totalLines,
  progress,
  { mode = "staggered_draw", staggerFrac = 0.65, direction = "ltr", ease = "editorial_out" } = {}
) {
  const p = clampUnit(progress);
  const total = Math.max(0, Math.round(Number(totalLines) || 0));
  const idx = Math.max(0, Math.min(Math.max(0, total - 1), Math.round(Number(lineIndex) || 0)));
  if (p <= 0 || total <= 0) {
    return { active: false, drawFrom: 0, drawTo: 0, widthScale: 0, alpha: 0 };
  }
  if (mode === "fade") {
    return { active: true, drawFrom: 0, drawTo: 1, widthScale: 1, alpha: p };
  }
  let rank = 0;
  if (total > 1) {
    if (direction === "rtl") rank = (total - 1 - idx) / (total - 1);
    else if (direction === "center_out") {
      const mid = (total - 1) / 2;
      rank = mid > 0 ? Math.abs(idx - mid) / mid : 0;
    } else {
      rank = idx / (total - 1);
    }
  }
  const stag = Math.max(0, Math.min(0.95, Number(staggerFrac ?? 0.65) || 0));
  const start = rank * stag;
  const span = Math.max(1e-4, 1 - stag);
  const localRaw = (p - start) / span;
  if (localRaw <= 0) {
    return { active: false, drawFrom: 0, drawTo: 0, widthScale: 0, alpha: 0 };
  }
  const clampedLocal = Math.min(1, localRaw);
  const eased = evalEase(ease, clampedLocal);
  const drawLen = Math.max(0, Math.min(1, eased));
  if (mode === "venetian_grow") {
    return {
      active: true,
      drawFrom: 0,
      drawTo: 1,
      widthScale: Math.max(0, eased),
      alpha: Math.min(1, Math.max(0, eased)),
    };
  }
  if (mode === "contour_ripple") {
    return {
      active: true,
      drawFrom: 0,
      drawTo: 1,
      widthScale: 0.6 + 0.4 * drawLen,
      alpha: Math.min(1, Math.max(0, eased)),
    };
  }
  const reverseAlternate = direction === "alternate" && idx % 2 === 1;
  return {
    active: true,
    drawFrom: reverseAlternate ? 1 - drawLen : 0,
    drawTo: reverseAlternate ? 1 : drawLen,
    widthScale: 0.55 + 0.45 * Math.min(1, drawLen * 2.5),
    alpha: Math.min(1, clampedLocal * 4),
  };
}

/**
 * Sample a quadratic Bezier continuously from u = 0 to exact u = progress,
 * returning points terminating strictly at B(progress) plus analytic tangent angle.
 */
export function sampleQuadraticBezierTo(p1, ctrl, p2, progress, steps = 40) {
  const p = clampUnit(progress);
  const n = Math.max(2, Math.min(256, Math.round(Number(steps) || 40)));
  const evalPt = (u) => {
    const inv = 1 - u;
    return {
      x: inv * inv * p1.x + 2 * inv * u * ctrl.x + u * u * p2.x,
      y: inv * inv * p1.y + 2 * inv * u * ctrl.y + u * u * p2.y,
    };
  };
  const points = [evalPt(0)];
  const count = Math.max(1, Math.ceil(n * p));
  for (let i = 1; i <= count; i++) {
    const u = (p * i) / count;
    points.push(evalPt(u));
  }
  const tip = points[points.length - 1];
  let dx = 2 * (1 - p) * (ctrl.x - p1.x) + 2 * p * (p2.x - ctrl.x);
  let dy = 2 * (1 - p) * (ctrl.y - p1.y) + 2 * p * (p2.y - ctrl.y);
  if (Math.hypot(dx, dy) < 1e-7) {
    dx = p2.x - p1.x;
    dy = p2.y - p1.y;
  }
  return { points, tip, angleRad: Math.atan2(dy, dx) };
}

/**
 * Symmetric centered subframe schedule for optical motion-blur accumulation.
 * Offsets span [-shutterSpan/2, +shutterSpan/2] in frames; weights sum strictly to 1.0.
 */
export function shutterSubframeSchedule(subN, shutterAngleDeg = 180, profile = "cosine") {
  const n = Math.max(1, Math.min(32, Math.round(Number(subN)) || 1));
  if (n === 1) return [{ offset: 0, weight: 1 }];
  const angle = Number.isFinite(Number(shutterAngleDeg)) ? Number(shutterAngleDeg) : 180;
  const span = Math.max(0, Math.min(1, angle / 360));
  const raw = [];
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const u = (i + 0.5) / n;
    const offset = (u - 0.5) * span;
    let w = 1;
    if (profile === "cosine") {
      w = Math.sin(Math.PI * u);
    } else if (profile === "trapezoid") {
      if (u < 0.2) w = u / 0.2;
      else if (u > 0.8) w = (1 - u) / 0.2;
      else w = 1;
    }
    raw.push({ offset, weight: w });
    sum += w;
  }
  return raw.map((s) => ({ offset: s.offset, weight: s.weight / (sum || 1) }));
}

/**
 * Unified sun direction vector from cartographic azimuth (clockwise from North)
 * and elevation angle (degrees above horizon).
 * Returns ENU Z-up unit vector `(x, y, z)` for 3D lighting plus 2D screen cast-shadow vector.
 */
export function sunDirectionFromAzimuthElevation(azimuthDeg = 335, elevationDeg = 42) {
  const azDeg = Number.isFinite(Number(azimuthDeg)) ? ((Number(azimuthDeg) % 360) + 360) % 360 : 335;
  const elDeg = Number.isFinite(Number(elevationDeg)) ? Math.max(5, Math.min(89, Number(elevationDeg))) : 42;
  const az = (azDeg * Math.PI) / 180;
  const el = (elDeg * Math.PI) / 180;
  const cosEl = Math.cos(el);
  const x = cosEl * Math.sin(az);
  const y = cosEl * Math.cos(az);
  const z = Math.sin(el);
  const shadowDx = -Math.sin(az);
  const shadowDy = Math.cos(az);
  return {
    x,
    y,
    z,
    shadowDx,
    shadowDy,
    lightDx: -shadowDx,
    lightDy: -shadowDy,
    azimuthDeg: azDeg,
    elevationDeg: elDeg,
  };
}

/**
 * Sample a 3D parabolic flight pose along a `[lng, lat]` polyline for `u` in `[0, 1]`.
 * Produces elevated altitude (`4*u*(1-u)*altitudeArcM`), forward heading (degrees CCW from +Y),
 * climb/descent pitch, and turn-coupled bank roll bounded by `bankMaxDeg`.
 */
export function sampleParabolicArcPose(
  path,
  uRaw,
  { altitudeArcM = 0, bankMaxDeg = 22 } = {}
) {
  const pts = Array.isArray(path) && path.length >= 2 ? path : [[0, 0], [1, 0]];
  const u = Math.max(0, Math.min(1, Number(uRaw) || 0));
  const segLens = [];
  let totalDeg = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const d = Math.hypot((pts[i + 1][0] - pts[i][0]), (pts[i + 1][1] - pts[i][1]));
    segLens.push(d);
    totalDeg += d;
  }
  const sampleAt = (t) => {
    const tc = Math.max(0, Math.min(1, t));
    if (totalDeg <= 1e-9) return [pts[0][0], pts[0][1]];
    let target = tc * totalDeg;
    for (let i = 0; i < segLens.length; i++) {
      if (target <= segLens[i] || i === segLens.length - 1) {
        const f = segLens[i] > 1e-9 ? Math.max(0, Math.min(1, target / segLens[i])) : 0;
        return [
          pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f,
          pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f,
        ];
      }
      target -= segLens[i];
    }
    return [pts[pts.length - 1][0], pts[pts.length - 1][1]];
  };

  const cur = sampleAt(u);
  const eps = 0.025;
  const pPrev = sampleAt(Math.max(0, u - eps));
  const pNext = sampleAt(Math.min(1, u + eps));
  const cosLat = Math.max(0.15, Math.cos((cur[1] * Math.PI) / 180));
  const dx = (pNext[0] - pPrev[0]) * cosLat;
  const dy = pNext[1] - pPrev[1];
  const headingDeg = Math.hypot(dx, dy) > 1e-7 ? (Math.atan2(-dx, dy) * 180) / Math.PI : 0;

  const arcH = Math.max(0, Number(altitudeArcM) || 0);
  const altM = 4 * u * (1 - u) * arcH;
  // Derivative d(alt)/du = 4*(1-2u)*arcH; map cleanly to realistic nose climb/descent angle
  const horizM = Math.max(1000, totalDeg * 111320 * cosLat);
  const dAltDu = 4 * (1 - 2 * u) * arcH;
  const rawPitchDeg = (Math.atan2(dAltDu, horizM) * 180) / Math.PI;
  const pitchDeg = Math.max(-28, Math.min(28, rawPitchDeg * 1.35));

  // Turn curvature roll (bank into turns) clamped within [-bankMaxDeg, bankMaxDeg]
  const pBack = sampleAt(Math.max(0, u - eps * 2));
  const pFwd = sampleAt(Math.min(1, u + eps * 2));
  const h1 = Math.atan2(-(cur[0] - pBack[0]) * cosLat, cur[1] - pBack[1]);
  const h2 = Math.atan2(-(pFwd[0] - cur[0]) * cosLat, pFwd[1] - cur[1]);
  let dh = h2 - h1;
  while (dh > Math.PI) dh -= Math.PI * 2;
  while (dh < -Math.PI) dh += Math.PI * 2;
  const maxBank = Math.max(0, Math.min(60, Number(bankMaxDeg) || 0));
  const env = Math.sin(Math.PI * u);
  const rawRoll = (dh * 180) / Math.PI * 1.45;
  const rollDeg = Math.max(-maxBank, Math.min(maxBank, rawRoll * env));

  return {
    lng: cur[0],
    lat: cur[1],
    altM,
    headingDeg,
    pitchDeg,
    rollDeg,
  };
}

/**
 * Compute sequential two-stroke diagonal slash progress and crossing shockwave pulse for
 * contextual `crimson_x` animations.
 */
export function slashCrossProgress(
  elapsedS,
  { slashDurS = 0.22, gapS = 0.11, impactDurS = 0.35 } = {}
) {
  const t = Number(elapsedS);
  if (!Number.isFinite(t) || t <= 0) {
    return { stroke1: 0, stroke2: 0, impactPulse: 0 };
  }
  const sd = Math.max(0.02, Number(slashDurS) || 0.22);
  const gap = Math.max(0, Number(gapS) || 0);
  const impD = Math.max(0.05, Number(impactDurS) || 0.35);
  const stroke1 = easeOutQuint(Math.max(0, Math.min(1, t / sd)));
  const s2Start = sd + gap;
  const stroke2 = t <= s2Start ? 0 : easeOutQuint(Math.max(0, Math.min(1, (t - s2Start) / sd)));
  const impactStart = s2Start + sd * 0.4;
  let impactPulse = 0;
  if (t >= impactStart && t <= impactStart + impD) {
    impactPulse = Math.sin(Math.PI * ((t - impactStart) / impD));
  }
  return { stroke1, stroke2, impactPulse };
}
