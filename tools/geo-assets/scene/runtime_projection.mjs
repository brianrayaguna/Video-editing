export function buildProjectionRuntime({ terrain3d }) {
  return `
    function resolveGeom(ref) {
      if (!ref) return null;
      if (typeof ref === "object" && ref.type) return ref;
      if (typeof ref !== "string") return null;
      const parts = ref.split(".");
      let cur = VEC;
      for (const p of parts) {
        if (cur && typeof cur === "object" && p in cur) cur = cur[p];
        else return null;
      }
      return cur;
    }

    function projectRingClipped(ring) {
      if (!ring || ring.length < 3) return [];
      const tr = map.transform;
      const M = tr && (tr.mercatorMatrix || tr._mercatorMatrix);
      if (M && (map.getPitch() || 0) > 1.0) {
        const hasTerr = ${terrain3d} && typeof map.queryTerrainElevation === "function";
        const hom = [];
        for (let i = 0; i < ring.length; i++) {
          const c = ring[i];
          const elev = hasTerr ? Math.max(0, map.queryTerrainElevation(c, { exaggerated: true }) || 0) : 0;
          const mc = maplibregl.MercatorCoordinate.fromLngLat(c, elev);
          hom.push({
            x: M[0] * mc.x + M[4] * mc.y + M[8] * mc.z + M[12],
            y: M[1] * mc.x + M[5] * mc.y + M[9] * mc.z + M[13],
            z: M[2] * mc.x + M[6] * mc.y + M[10] * mc.z + M[14],
            w: M[3] * mc.x + M[7] * mc.y + M[11] * mc.z + M[15],
          });
        }
        const clipped = clipHomogeneousRing(hom, 1e-4);
        if (clipped.length < 3) return [];
        const pts = [];
        for (let i = 0; i < clipped.length; i++) {
          const v = clipped[i];
          const iw = 1 / Math.max(1e-4, v.w);
          pts.push({
            x: (v.x * iw * 0.5 + 0.5) * W,
            y: (0.5 - v.y * iw * 0.5) * H,
          });
        }
        return pts;
      }
      return ring.map((c) => map.project(c));
    }

    function projectPointSafe(lngLat, eps = 1e-4) {
      if (!lngLat || lngLat.length < 2) return null;
      const tr = map.transform;
      const M = tr && (tr.mercatorMatrix || tr._mercatorMatrix);
      if (M && (map.getPitch() || 0) > 1.0) {
        const hasTerr = ${terrain3d} && typeof map.queryTerrainElevation === "function";
        const elev = hasTerr ? Math.max(0, map.queryTerrainElevation(lngLat, { exaggerated: true }) || 0) : 0;
        const mc = maplibregl.MercatorCoordinate.fromLngLat(lngLat, elev);
        const w = M[3] * mc.x + M[7] * mc.y + M[11] * mc.z + M[15];
        const z = M[2] * mc.x + M[6] * mc.y + M[10] * mc.z + M[14];
        if (!Number.isFinite(w) || w <= eps || z + w < 0) return null;
        const x = M[0] * mc.x + M[4] * mc.y + M[8] * mc.z + M[12];
        const y = M[1] * mc.x + M[5] * mc.y + M[9] * mc.z + M[13];
        const iw = 1 / w;
        return { x: (x * iw * 0.5 + 0.5) * W, y: (0.5 - y * iw * 0.5) * H };
      }
      const p = map.project(lngLat);
      return p && Number.isFinite(p.x) && Number.isFinite(p.y) ? p : null;
    }

    function projectPolylineClipped(coords, eps = 1e-4) {
      if (!coords || coords.length < 2) return [];
      const tr = map.transform;
      const M = tr && (tr.mercatorMatrix || tr._mercatorMatrix);
      if (M && (map.getPitch() || 0) > 1.0) {
        const hasTerr = ${terrain3d} && typeof map.queryTerrainElevation === "function";
        const hom = [];
        for (let i = 0; i < coords.length; i++) {
          const c = coords[i];
          const elev = hasTerr ? Math.max(0, map.queryTerrainElevation(c, { exaggerated: true }) || 0) : 0;
          const mc = maplibregl.MercatorCoordinate.fromLngLat(c, elev);
          hom.push({
            x: M[0] * mc.x + M[4] * mc.y + M[8] * mc.z + M[12],
            y: M[1] * mc.x + M[5] * mc.y + M[9] * mc.z + M[13],
            z: M[2] * mc.x + M[6] * mc.y + M[10] * mc.z + M[14],
            w: M[3] * mc.x + M[7] * mc.y + M[11] * mc.z + M[15],
          });
        }
        const segs = clipHomogeneousPolyline(hom, eps);
        return segs.map((segVerts) =>
          segVerts.map((v) => {
            const iw = 1 / Math.max(eps, v.w);
            return { x: (v.x * iw * 0.5 + 0.5) * W, y: (0.5 - v.y * iw * 0.5) * H };
          })
        );
      }
      return [coords.map((c) => map.project(c))];
    }

    function traceRing(targetCtx, ring) {
      const pts = projectRingClipped(ring);
      if (pts.length < 3) return;
      for (let i = 0; i < pts.length; i++) {
        if (i === 0) targetCtx.moveTo(pts[i].x, pts[i].y);
        else targetCtx.lineTo(pts[i].x, pts[i].y);
      }
      targetCtx.closePath();
    }

    function traceGeom(targetCtx, geom) {
      if (!geom) return;
      if (Array.isArray(geom)) {
        for (const item of geom) traceGeom(targetCtx, item?.geometry || item);
        return;
      }
      if (geom.type === "Feature" || (!geom.type && geom.geometry)) {
        traceGeom(targetCtx, geom.geometry);
      } else if (geom.type === "FeatureCollection") {
        traceGeom(targetCtx, geom.features);
      } else if (geom.type === "GeometryCollection") {
        traceGeom(targetCtx, geom.geometries);
      } else if (geom.type === "Polygon") {
        for (const r of geom.coordinates || []) traceRing(targetCtx, r);
      } else if (geom.type === "MultiPolygon") {
        for (const poly of geom.coordinates || []) {
          for (const r of poly) traceRing(targetCtx, r);
        }
      }
    }

    function parseHexRgb(hex) {
      const raw = String(hex || "#FFFFFF").trim();
      const rgbMatch = raw.match(/^rgba?\\(\\s*([\\d.]+)\\s*,\\s*([\\d.]+)\\s*,\\s*([\\d.]+)/i);
      if (rgbMatch) {
        return [
          clamp(Math.round(Number(rgbMatch[1])), 0, 255),
          clamp(Math.round(Number(rgbMatch[2])), 0, 255),
          clamp(Math.round(Number(rgbMatch[3])), 0, 255),
        ];
      }
      let h = raw.replace("#", "");
      if (h.length === 3 || h.length === 4) {
        h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
      }
      return [
        parseInt(h.slice(0, 2), 16) || 0,
        parseInt(h.slice(2, 4), 16) || 0,
        parseInt(h.slice(4, 6), 16) || 0,
      ];
    }

    function mixHex(c1, c2, u) {
      const a = parseHexRgb(c1), b = parseHexRgb(c2);
      const r = Math.round(lerp(a[0], b[0], u));
      const g = Math.round(lerp(a[1], b[1], u));
      const bl = Math.round(lerp(a[2], b[2], u));
      return "rgb(" + r + "," + g + "," + bl + ")";
    }

    function rgbaStr(hex, alpha) {
      const [r, g, b] = parseHexRgb(hex);
      return "rgba(" + r + "," + g + "," + b + "," + clamp(alpha, 0, 1).toFixed(3) + ")";
    }

    function computeGeomBounds(geom) {
      let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
      const visitRing = (ring) => {
        for (const pt of ring) {
          if (pt[0] < minLng) minLng = pt[0];
          if (pt[0] > maxLng) maxLng = pt[0];
          if (pt[1] < minLat) minLat = pt[1];
          if (pt[1] > maxLat) maxLat = pt[1];
        }
      };
      const visit = (g) => {
        if (!g) return;
        if (Array.isArray(g)) { for (const it of g) visit(it?.geometry || it); return; }
        if (g.type === "Feature" || (!g.type && g.geometry)) { visit(g.geometry); }
        else if (g.type === "FeatureCollection") { visit(g.features); }
        else if (g.type === "GeometryCollection") { visit(g.geometries); }
        else if (g.type === "Polygon") { for (const r of g.coordinates || []) visitRing(r); }
        else if (g.type === "MultiPolygon") { for (const p of g.coordinates || []) for (const r of p) visitRing(r); }
      };
      visit(geom);
      if (!Number.isFinite(minLng)) return null;
      return [minLng, minLat, maxLng, maxLat];
    }

    function applyWorldDirectionalClip(targetCtx, geom, axis, progress, explicitBounds = null) {
      const p = clamp(progress, 0, 1);
      if (p >= 0.999) return true;
      if (p <= 0.001) return false;
      const b = explicitBounds || computeGeomBounds(geom);
      if (!b) return true;
      const [minLng, minLat, maxLng, maxLat] = b;
      const padLng = Math.max(12, (maxLng - minLng) * 0.45);
      const padLat = Math.max(12, (maxLat - minLat) * 0.45);
      let w = minLng - padLng, e = maxLng + padLng, s = minLat - padLat, n = maxLat + padLat;
      if (axis === "north_south") {
        s = lerp(maxLat + 0.5, minLat - padLat, p);
      } else if (axis === "south_north") {
        n = lerp(minLat - 0.5, maxLat + padLat, p);
      } else if (axis === "west_east") {
        e = lerp(minLng - 0.5, maxLng + padLng, p);
      } else if (axis === "east_west") {
        w = lerp(maxLng + 0.5, minLng - padLng, p);
      }
      const corners = [[w, n], [e, n], [e, s], [w, s]];
      const projCorners = projectRingClipped(corners);
      if (projCorners.length < 3) return false;
      targetCtx.beginPath();
      for (let i = 0; i < projCorners.length; i++) {
        if (i === 0) targetCtx.moveTo(projCorners[i].x, projCorners[i].y);
        else targetCtx.lineTo(projCorners[i].x, projCorners[i].y);
      }
      targetCtx.closePath();
      targetCtx.clip();
      return true;
    }

    function drawProgressiveGeomPerimeter(geom, progress, { rimHex = "#F4F1EA", rimWidth = 3.2, bloomHex = "#60A5FA", bloomScale = 1.0, alpha = 1.0 } = {}) {
      if (alpha <= 0.005 || progress <= 0.001 || !geom) return;
      const rings = [];
      const collect = (g) => {
        if (!g) return;
        if (Array.isArray(g)) { for (const it of g) collect(it?.geometry || it); return; }
        if (g.type === "Feature" || (!g.type && g.geometry)) { collect(g.geometry); }
        else if (g.type === "FeatureCollection") { collect(g.features); }
        else if (g.type === "GeometryCollection") { collect(g.geometries); }
        else if (g.type === "Polygon" && g.coordinates?.[0]) rings.push(g.coordinates[0]);
        else if (g.type === "MultiPolygon") { for (const p of g.coordinates || []) if (p[0]) rings.push(p[0]); }
      };
      collect(geom);
      for (const ring of rings) {
        if (ring.length < 3) continue;
        // Trace ring symmetrically from two opposite anchors so perimeter closes swiftly across the continent
        const mid = Math.floor(ring.length / 2);
        const segA = ring.slice(0, mid + 1);
        const segB = ring.slice(mid);
        const drawHalf = (coords) => {
          drawPartialRoute(coords, progress, {
            color: rimHex,
            bloom: bloomHex || rimHex,
            core: "#FFFFFF",
            width: rimWidth,
            alpha,
          });
        };
        drawHalf(segA);
        drawHalf(segB);
      }
    }

    // Exterior rings of a (Multi)Polygon or feature list, in lng/lat.
    function outerRingsLngLat(geom) {
      return polygonRings(geom).outer;
    }

    // Per-ring start vertex and walk direction for a border trace, decided in lng/lat so the
    // heads never jump between frames while the camera moves. Default start: northernmost vertex.`;
}
