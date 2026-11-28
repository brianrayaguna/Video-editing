import { DEFAULT_MAP_CENTER } from "../geo_defaults.mjs";
import { buildDynamicFontFaceCss } from "./font_css.mjs";

export function buildBlueprintHtml(baseUrl, width, height, vectorsJson, actSpec) {
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
${typeof buildDynamicFontFaceCss === "function" ? buildDynamicFontFaceCss(baseUrl) : ""}
    * { margin: 0; padding: 0; }
    html, body { width: ${width}px; height: ${height}px; overflow: hidden; background: #1E1B18; }
    canvas { display: block; width: ${width}px; height: ${height}px; }
  </style>
</head>
<body>
  <canvas id="c" width="${width}" height="${height}"></canvas>
  <script>
    const VEC = ${vectorsJson.replace(/</g, "\\u003c")};
    const SPEC = ${JSON.stringify(actSpec).replace(/</g, "\\u003c")};
    const W = ${width}, H = ${height};
    const ctx = document.getElementById("c").getContext("2d");
    const maskC = document.createElement("canvas"); maskC.width = 1200; maskC.height = 1700;
    const maskX = maskC.getContext("2d");

    const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
    const lerp = (a, b, t) => a + (b - a) * t;
    const seg = (t, a, b) => (b <= a ? 1 : clamp((t - a) / (b - a), 0, 1));
    const easeInOutCubic = (x) => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
    const easeOutCubic = (x) => 1 - Math.pow(1 - x, 3);
    const easeInExpo = (x) => x <= 0 ? 0 : Math.pow(2, 10 * (x - 1));

    function resolveGeom(ref) {
      if (!ref) return null;
      if (typeof ref === "object" && ref.type) return ref;
      let cur = VEC;
      for (const p of String(ref).split(".")) cur = cur ? cur[p] : null;
      return cur;
    }

    const cLng = SPEC.center?.[0] ?? ${DEFAULT_MAP_CENTER[0]};
    const cLat = SPEC.center?.[1] ?? ${DEFAULT_MAP_CENTER[1]};
    function projLocal(lng, lat) {
      return [(lng - cLng) * 235, -(lat - cLat) * 245];
    }
    function traceLocal(targetCtx, geom, ox = 0, oy = 0) {
      if (!geom) return;
      const doRing = (ring) => {
        for (let i = 0; i < ring.length; i++) {
          const [x, y] = projLocal(ring[i][0], ring[i][1]);
          if (i === 0) targetCtx.moveTo(x + ox, y + oy);
          else targetCtx.lineTo(x + ox, y + oy);
        }
        targetCtx.closePath();
      };
      if (geom.type === "Polygon") geom.coordinates.forEach(doRing);
      else if (geom.type === "MultiPolygon") geom.coordinates.forEach((p) => p.forEach(doRing));
    }

    function drawPartial(pts, prog, strokeStyle, width) {
      if (prog <= 0.001 || pts.length < 2) return;
      const lens = [0]; let tot = 0;
      for (let i = 1; i < pts.length; i++) { tot += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); lens.push(tot); }
      const target = tot * clamp(prog, 0, 1);
      ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) {
        if (lens[i] <= target) ctx.lineTo(pts[i][0], pts[i][1]);
        else {
          const f = (target - lens[i - 1]) / Math.max(1e-5, lens[i] - lens[i - 1]);
          ctx.lineTo(lerp(pts[i - 1][0], pts[i][0], f), lerp(pts[i - 1][1], pts[i][1], f));
          break;
        }
      }
      ctx.strokeStyle = strokeStyle; ctx.lineWidth = width; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.stroke();
    }

    const regionGeom = resolveGeom(SPEC.region_ref);
    const landGeoms = (SPEC.land_refs || []).map(resolveGeom).filter(Boolean);
    const northPts = (SPEC.north_road || []).map((c) => projLocal(c[0], c[1]));
    const southPts = (SPEC.south_road || []).map((c) => projLocal(c[0], c[1]));
    const failPts = (SPEC.failed_road || []).map((c) => projLocal(c[0], c[1]));

    // Pre-bake seamless dissolved mask for paper blueprint region
    maskX.clearRect(0, 0, 1200, 1700);
    maskX.fillStyle = "#FFFFFF"; maskX.strokeStyle = "#FFFFFF"; maskX.lineWidth = 3.5; maskX.lineJoin = "round";
    maskX.beginPath(); traceLocal(maskX, regionGeom, 600, 850); maskX.fill(); maskX.stroke();

    window.__renderBlueprint = function(t) {
      ctx.fillStyle = "#1E1B18";
      ctx.fillRect(0, 0, W, H);
      const pull = easeInOutCubic(seg(t, 0.2, 5.6));
      const scale = lerp(2.35, 1.18, pull);
      const rot = lerp(-0.16, 0.08, pull);
      const ox = lerp(W * 0.54, W * 0.50, pull);
      const oy = lerp(H * 0.52, H * 0.49, pull);
      const stampAt = SPEC.stamp_at_s ?? 5.65;

      let sx = 0, sy = 0;
      if (t >= stampAt && t <= stampAt + 0.36) {
        const d = 1 - seg(t, stampAt, stampAt + 0.36);
        sx = Math.sin(t * 98) * 15 * d;
        sy = Math.cos(t * 82) * 15 * d;
      }

      ctx.save();
      ctx.translate(ox + sx, oy + sy);
      ctx.rotate(rot);
      ctx.scale(scale, scale);

      const pw = 1160, ph = 1660;
      ctx.fillStyle = "#D9D2C3";
      ctx.shadowColor = "rgba(0,0,0,0.65)"; ctx.shadowBlur = 40;
      ctx.fillRect(-pw / 2, -ph / 2, pw, ph);
      ctx.shadowBlur = 0;

      ctx.fillStyle = "#8C939A";
      ctx.fillRect(-pw / 2 + 44, -ph / 2 + 195, pw - 88, ph - 265);

      ctx.save();
      ctx.beginPath(); ctx.rect(-pw / 2 + 44, -ph / 2 + 195, pw - 88, ph - 265); ctx.clip();
      ctx.fillStyle = "#CFC8B8"; ctx.strokeStyle = "#6B675E"; ctx.lineWidth = 2;
      for (const g of landGeoms) { ctx.beginPath(); traceLocal(ctx, g); ctx.fill(); ctx.stroke(); }

      ctx.strokeStyle = "rgba(92, 88, 80, 0.26)"; ctx.lineWidth = 1.2;
      for (let gx = -560; gx <= 560; gx += 85) { ctx.beginPath(); ctx.moveTo(gx, -650); ctx.lineTo(gx, 760); ctx.stroke(); }
      for (let gy = -620; gy <= 760; gy += 85) { ctx.beginPath(); ctx.moveTo(-560, gy); ctx.lineTo(560, gy); ctx.stroke(); }

      // Seamless glowing green dissolved boundary on paper
      ctx.save();
      ctx.shadowColor = "#22C55E"; ctx.shadowBlur = 24;
      ctx.globalAlpha = 0.52;
      ctx.drawImage(maskC, -600, -850);
      ctx.restore();
      ctx.save();
      ctx.globalAlpha = 0.34;
      ctx.beginPath(); traceLocal(ctx, regionGeom); ctx.fillStyle = "#22C55E"; ctx.fill();
      ctx.restore();

      drawPartial(northPts, 1, "#C89B2B", 7.5);
      drawPartial(southPts, 1, "#C89B2B", 7.5);
      drawPartial(failPts, easeInOutCubic(seg(t, 0.4, 5.2)), "#8B0000", 9);
      ctx.restore();

      ctx.fillStyle = "#48433B";
      ctx.font = "600 56px 'EB Garamond', Georgia, serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(SPEC.header || "PAN AMERICAN HIGHWAY", 0, -ph / 2 + 104);
      ctx.font = "400 18px 'EB Garamond', Georgia, serif";
      ctx.fillStyle = "#6B655B";
      ctx.fillText(SPEC.subheader || "ENGINEERING ROUTE SURVEY", 0, -ph / 2 + 150);

      // Subtle paper fold lines
      ctx.strokeStyle = "rgba(40, 35, 28, 0.2)"; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(-pw / 2, -60); ctx.lineTo(pw / 2, -60); ctx.moveTo(0, -ph / 2); ctx.lineTo(0, ph / 2); ctx.stroke();

      if (t >= stampAt - 0.03) {
        const stA = seg(t, stampAt - 0.03, stampAt + 0.07);
        ctx.save();
        ctx.translate(18, 22); ctx.rotate(-0.50); ctx.globalAlpha = stA * 0.94;
        ctx.strokeStyle = "#991B1B"; ctx.lineWidth = 8; ctx.strokeRect(-142, -52, 284, 104);
        ctx.lineWidth = 3; ctx.strokeRect(-130, -40, 260, 80);
        ctx.fillStyle = "#991B1B"; ctx.font = "900 56px 'Archivo Black', sans-serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(SPEC.stamp_text || "FAILED", 0, 3);
        ctx.restore();
      }

      if (t >= stampAt - 0.40 && t <= stampAt + 0.35) {
        const down = easeInExpo(seg(t, stampAt - 0.40, stampAt));
        const up = easeOutCubic(seg(t, stampAt + 0.07, stampAt + 0.35));
        const lift = 1 - down + up;
        const sc = 1.0 + lift * 0.95;
        const al = seg(t, stampAt - 0.40, stampAt - 0.28) * (1 - seg(t, stampAt + 0.23, stampAt + 0.35));
        ctx.save();
        ctx.translate(18 + lift * 210, 22 + lift * 160); ctx.rotate(-0.50); ctx.scale(sc, sc); ctx.globalAlpha = al;
        ctx.shadowColor = "rgba(0,0,0,0.55)"; ctx.shadowBlur = 24 + lift * 35; ctx.shadowOffsetX = 12 + lift * 24; ctx.shadowOffsetY = 18 + lift * 30;
        ctx.fillStyle = "#8C6239"; ctx.beginPath(); ctx.roundRect(-155, -64, 310, 128, 10); ctx.fill();
        ctx.strokeStyle = "#5C3D1E"; ctx.lineWidth = 5; ctx.stroke();
        ctx.shadowBlur = 14; ctx.fillStyle = "#262320"; ctx.beginPath(); ctx.ellipse(24, 18, 62, 48, 0.2, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }
      ctx.restore();

      // Macro-lens subtle top/bottom atmospheric vignette on paper sheet
      const mg = ctx.createRadialGradient(W * 0.5, H * 0.48, 280, W * 0.5, H * 0.48, 1120);
      mg.addColorStop(0, "rgba(0,0,0,0)");
      mg.addColorStop(1, "rgba(18,14,10,0.34)");
      ctx.fillStyle = mg;
      ctx.fillRect(0, 0, W, H);

      if (SPEC.entry_flash_hex && t < 0.55) {
        const fA = 1 - easeOutCubic(seg(t, 0, 0.55));
        let h = String(SPEC.entry_flash_hex).replace("#", "");
        if (h.length === 3 || h.length === 4) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
        ctx.fillStyle = "rgba(" + (parseInt(h.slice(0,2),16) || 0) + "," + (parseInt(h.slice(2,4),16) || 0) + "," + (parseInt(h.slice(4,6),16) || 0) + "," + (fA * 0.78).toFixed(3) + ")";
        ctx.fillRect(0, 0, W, H);
      }
    };
  </script>
</body>
</html>`;
}

