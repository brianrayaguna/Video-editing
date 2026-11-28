import { buildDynamicFontFaceCss } from "./font_css.mjs";

export function buildCutaway2dHtml(baseUrl, width, height, actSpec) {
  const safeSpec = JSON.stringify(actSpec).replace(/</g, "\\u003c");
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    ${buildDynamicFontFaceCss(baseUrl)}
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { width: ${width}px; height: ${height}px; overflow: hidden; background: #1A1410; }
    canvas { display: block; width: ${width}px; height: ${height}px; }
  </style>
</head>
<body>
  <canvas id="c" width="${width}" height="${height}"></canvas>
  <script>
    const SPEC = ${safeSpec};
    const W = ${width}, H = ${height};
    const outCanvas = document.getElementById("c");
    const outCtx = outCanvas.getContext("2d");
    const buf = document.createElement("canvas");
    buf.width = W; buf.height = H;
    const ctx = buf.getContext("2d");

    const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
    const lerp = (a, b, t) => a + (b - a) * t;
    const seg = (t, a, b) => (b <= a ? 1 : clamp((t - a) / (b - a), 0, 1));
    const easeOutCubic = (x) => 1 - Math.pow(1 - clamp(x, 0, 1), 3);
    const easeInOutCubic = (x) => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
    const easeOutBack = (x) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };

    function hash(n) { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); }

    // Pre-generate deterministic branching root trees for soil_root_cutaway
    const ROOT_TREES = [];
    const nRootClusters = 14;
    for (let i = 0; i < nRootClusters; i++) {
      const rx = ((i + 0.5) / nRootClusters) * W + (hash(i * 11) - 0.5) * 45;
      const branches = [];
      function grow(x0, y0, ang, len, depth, width, seed) {
        if (depth > 4 || len < 14) return;
        const x1 = x0 + Math.cos(ang) * len;
        const y1 = y0 + Math.sin(ang) * len;
        branches.push({ x0, y0, x1, y1, depth, width, yNorm: y1 / H });
        const kids = depth === 0 ? 3 : 2;
        for (let k = 0; k < kids; k++) {
          const sp = (k - (kids - 1) * 0.5) * (0.48 + hash(seed + k * 7) * 0.25);
          const nAng = Math.PI * 0.5 + sp + (hash(seed + k * 19) - 0.5) * 0.35;
          grow(x1, y1, nAng, len * (0.64 + hash(seed + k * 23) * 0.22), depth + 1, width * 0.68, seed * 3.1 + k + 1);
        }
      }
      grow(rx, H * 0.335, Math.PI * 0.5 + (hash(i * 5) - 0.5) * 0.16, 95 + hash(i * 3) * 65, 0, 5.2, i * 17 + 1);
      ROOT_TREES.push({ x: rx, branches });
    }

    // Pre-generate deterministic clods for wind erosion
    const EROSION_CLODS = [];
    for (let i = 0; i < 95; i++) {
      EROSION_CLODS.push({
        x0: (0.04 + hash(i * 3.1) * 0.92) * W,
        y0: H * (0.335 + hash(i * 5.7) * 0.04),
        vx: (hash(i * 7.3) - 0.35) * 420,
        vy: -(240 + hash(i * 11.9) * 760),
        sz: 12 + hash(i * 13.7) * 34,
        rot: hash(i * 17.1) * Math.PI * 2,
        vrot: (hash(i * 19.3) - 0.5) * 8,
        delay: hash(i * 23.1) * 0.95,
        dark: hash(i * 29.7) > 0.45,
      });
    }

    function renderSoilRootCutaway(t) {
      const horizonY = H * 0.335;
      const plowStart = SPEC.plow_start_s ?? 4.3;
      const plowEnd = SPEC.plow_end_s ?? 6.4;
      const erodeStart = SPEC.erode_start_s ?? 6.8;
      const erodeEnd = SPEC.erode_end_s ?? 8.6;
      const highlightStart = SPEC.roots_highlight_s ?? 2.4;
      const highlightEnd = SPEC.roots_highlight_end_s ?? 4.3;

      const plowU = seg(t, plowStart, plowEnd);
      const plowX = lerp(-280, W + 420, plowU);
      const erodeU = seg(t, erodeStart, erodeEnd);

      // 1. Overcast pale blue-grey sky
      const skyG = ctx.createLinearGradient(0, 0, 0, horizonY);
      skyG.addColorStop(0, "#AFC2CC");
      skyG.addColorStop(1, "#CDD9DF");
      ctx.fillStyle = skyG;
      ctx.fillRect(0, 0, W, horizonY + 12);

      // Subtle atmospheric wind dust streaks in sky
      ctx.fillStyle = "rgba(255,255,255,0.22)";
      for (let i = 0; i < 36; i++) {
        const sx = ((hash(i * 31) * W + t * 90) % (W + 40)) - 20;
        const sy = hash(i * 47) * horizonY * 0.92;
        ctx.fillRect(sx, sy, 10 + hash(i * 13) * 14, 2);
      }

      // 2. Green aura behind Prairie Grasses title
      const grassTitleA = easeOutCubic(seg(t, 1.4, 2.0)) * (1 - seg(t, plowStart - 0.2, plowStart + 0.3));
      if (grassTitleA > 0.01) {
        const gg = ctx.createLinearGradient(0, horizonY - 260, 0, horizonY);
        gg.addColorStop(0, "rgba(132, 204, 22, 0)");
        gg.addColorStop(1, "rgba(163, 230, 53, " + (0.45 * grassTitleA).toFixed(3) + ")");
        ctx.fillStyle = gg;
        ctx.fillRect(0, horizonY - 260, W, 260);
      }

      // 3. Multi-layered swaying prairie grass blades (already lush on entry, sheared left-to-right by plow)
      const grassGrowth = 1.0;
      const cutX = plowU > 0 ? plowX - 180 : -999;
      for (let layer = 0; layer < 2; layer++) {
        const blades = 90;
        for (let i = 0; i < blades; i++) {
          const bx = (i / (blades - 1)) * (W + 20) - 10;
          if (bx < cutX) continue;
          const bh = (68 + hash(i * 17 + layer * 91) * 78) * grassGrowth * (layer === 0 ? 1.0 : 0.72);
          const sway = Math.sin(t * 2.8 + i * 0.35 + layer) * 12;
          const bw = 9 + hash(i * 7 + layer) * 6;
          ctx.fillStyle = layer === 0
            ? (i % 3 === 0 ? "#4D9E22" : "#62B52A")
            : (i % 2 === 0 ? "#82CE32" : "#5AA824");
          ctx.beginPath();
          ctx.moveTo(bx - bw * 0.5, horizonY + 4);
          ctx.quadraticCurveTo(bx + sway * 0.5, horizonY - bh * 0.55, bx + sway, horizonY - bh);
          ctx.quadraticCurveTo(bx + bw * 0.5 + sway * 0.4, horizonY - bh * 0.45, bx + bw * 0.5, horizonY + 4);
          ctx.closePath();
          ctx.fill();
        }
      }

      // 4. Stratified 5-band soil cross-section
      const strata = [
        { y0: horizonY, y1: H * 0.40, col: "#4F2312" },
        { y0: H * 0.40, y1: H * 0.54, col: "#7D421A" },
        { y0: H * 0.54, y1: H * 0.64, col: "#9F622C" },
        { y0: H * 0.64, y1: H * 0.82, col: "#682E15" },
        { y0: H * 0.82, y1: H, col: "#3A1A11" },
      ];
      for (let s = 0; s < strata.length; s++) {
        const st = strata[s];
        ctx.fillStyle = st.col;
        ctx.beginPath();
        ctx.moveTo(0, st.y0);
        for (let x = 0; x <= W; x += 60) {
          const wave = s === 0
            ? (erodeU > 0 ? Math.sin(x * 0.015 + 1.2) * 10 * erodeU : 0)
            : Math.sin(x * 0.008 + s * 2.1) * 14 + Math.cos(x * 0.019 + s) * 6;
          ctx.lineTo(x, st.y0 + wave);
        }
        ctx.lineTo(W, st.y1 + 20);
        ctx.lineTo(0, st.y1 + 20);
        ctx.closePath();
        ctx.fill();
      }
      // Soil pebbles & organic speckles
      for (let i = 0; i < 160; i++) {
        const px = hash(i * 19.1) * W;
        const py = horizonY + 24 + hash(i * 23.7) * (H - horizonY - 36);
        const pr = 3 + hash(i * 31.3) * 8;
        ctx.fillStyle = i % 3 === 0 ? "rgba(255,215,175,0.14)" : "rgba(25,10,5,0.22)";
        ctx.beginPath();
        ctx.ellipse(px, py, pr * 1.3, pr * 0.85, hash(i) * 3, 0, Math.PI * 2);
        ctx.fill();
      }

      // 5. Branching Deep Roots (grow smoothly, glow gold on highlight, vanish behind plow)
      const rootGrow = easeOutCubic(seg(t, 0.1, 1.5));
      const rootHi = easeOutCubic(seg(t, highlightStart, highlightStart + 0.45)) * (1 - seg(t, highlightEnd - 0.3, highlightEnd));
      ctx.save();
      ctx.lineCap = "round";
      for (const tree of ROOT_TREES) {
        let treeAlpha = 1.0;
        if (plowU > 0 && tree.x < cutX + 120) {
          treeAlpha = clamp((tree.x - (cutX - 90)) / 210, 0, 1);
        }
        if (treeAlpha <= 0.01) continue;
        for (const br of tree.branches) {
          const maxDepthP = clamp(rootGrow * 5 - br.depth * 0.75, 0, 1);
          if (maxDepthP <= 0.02) continue;
          const ex = lerp(br.x0, br.x1, maxDepthP);
          const ey = lerp(br.y0, br.y1, maxDepthP);
          ctx.strokeStyle = rootHi > 0.05
            ? "rgba(" + Math.round(lerp(245, 250, rootHi)) + "," + Math.round(lerp(236, 224, rootHi)) + "," + Math.round(lerp(212, 42, rootHi)) + "," + (treeAlpha * 0.92).toFixed(3) + ")"
            : "rgba(244, 232, 206, " + (treeAlpha * 0.86).toFixed(3) + ")";
          ctx.lineWidth = br.width * (1 + rootHi * 0.35);
          if (rootHi > 0.1) {
            ctx.shadowColor = "#FACC15";
            ctx.shadowBlur = 14 * rootHi;
          } else {
            ctx.shadowBlur = 0;
          }
          ctx.beginPath();
          ctx.moveTo(br.x0, br.y0);
          ctx.lineTo(ex, ey);
          ctx.stroke();
        }
      }
      ctx.restore();

      // 6. Side-view Red Tractor + Steel Disc Plow tearing across grass horizon
      if (plowU > 0.001 && plowU < 0.999) {
        ctx.save();
        ctx.translate(plowX, horizonY);
        // Steel plow frame & twin curved discs digging into topsoil behind tractor
        ctx.strokeStyle = "#334155";
        ctx.lineWidth = 10;
        ctx.beginPath();
        ctx.moveTo(-40, -52); ctx.lineTo(-220, -45); ctx.lineTo(-250, 18);
        ctx.moveTo(-165, -45); ctx.lineTo(-185, 22);
        ctx.stroke();
        for (const dx of [-255, -188]) {
          const dg = ctx.createLinearGradient(dx - 38, -20, dx + 38, 36);
          dg.addColorStop(0, "#E2E8F0");
          dg.addColorStop(1, "#64748B");
          ctx.fillStyle = dg;
          ctx.beginPath();
          ctx.ellipse(dx, 6, 46, 22, -0.35, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = "#1E293B";
          ctx.lineWidth = 3;
          ctx.stroke();
        }
        // Churned dirt flying off plow blades
        ctx.fillStyle = "#4A2210";
        for (let k = 0; k < 14; k++) {
          const ph = ((t * 6 + k * 0.37) % 1);
          const cx = -230 - ph * 80 + Math.sin(k * 7) * 35;
          const cy = 12 - Math.sin(ph * Math.PI) * (50 + (k % 5) * 14);
          ctx.fillRect(cx, cy, 12 + (k % 4) * 4, 10 + (k % 3) * 4);
        }
        // Tractor chassis
        ctx.fillStyle = "#C81E1E";
        ctx.strokeStyle = "#1F2937";
        ctx.lineWidth = 5;
        ctx.beginPath();
        ctx.roundRect(-70, -210, 310, 130, 18);
        ctx.fill(); ctx.stroke();
        // Rear big wheel
        ctx.fillStyle = "#1F2937";
        ctx.beginPath(); ctx.arc(0, -86, 86, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#D1D5DB";
        ctx.beginPath(); ctx.arc(0, -86, 44, 0, Math.PI * 2); ctx.fill();
        // Front smaller wheel
        ctx.fillStyle = "#1F2937";
        ctx.beginPath(); ctx.arc(215, -52, 52, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#D1D5DB";
        ctx.beginPath(); ctx.arc(215, -52, 24, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }

      // 7. Wind erosion ripping dark topsoil clods violently upward into sky
      if (erodeU > 0.01) {
        for (const cl of EROSION_CLODS) {
          const lt = clamp((erodeU - cl.delay * 0.45) / 0.55, 0, 1);
          if (lt <= 0) continue;
          const cx = cl.x0 + cl.vx * lt * 1.1;
          const cy = cl.y0 + cl.vy * lt * 1.15;
          ctx.save();
          ctx.translate(cx, cy);
          ctx.rotate(cl.rot + cl.vrot * lt);
          ctx.fillStyle = cl.dark ? "#3D1B0F" : "#5D2B16";
          ctx.beginPath();
          ctx.moveTo(-cl.sz * 0.5, -cl.sz * 0.35);
          ctx.lineTo(cl.sz * 0.4, -cl.sz * 0.48);
          ctx.lineTo(cl.sz * 0.52, cl.sz * 0.30);
          ctx.lineTo(-cl.sz * 0.38, cl.sz * 0.45);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        }
      }

      // 8. Bold boxless labels: "Prairie / Grasses" & "Deep / Roots"
      if (grassTitleA > 0.01) {
        ctx.save();
        ctx.globalAlpha = grassTitleA;
        ctx.font = "800 84px 'Barlow Condensed', sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#FFFFFF";
        ctx.shadowColor = "rgba(15, 35, 10, 0.58)";
        ctx.shadowBlur = 16;
        ctx.shadowOffsetY = 4;
        ctx.fillText("Prairie", W * 0.44, H * 0.145);
        ctx.fillText("Grasses", W * 0.52, H * 0.195);
        ctx.restore();
      }
      if (rootHi > 0.02) {
        ctx.save();
        ctx.globalAlpha = rootHi;
        ctx.font = "800 72px 'Barlow Condensed', sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#FFFBEB";
        ctx.shadowColor = "rgba(35, 18, 6, 0.78)";
        ctx.shadowBlur = 14;
        ctx.fillText("Deep", W * 0.38, H * 0.515);
        ctx.fillText("Roots", W * 0.46, H * 0.558);
        ctx.restore();
      }
    }

    function renderDustWallHorizon(t) {
      const groundY = H * 0.79;
      const wallU = easeInOutCubic(seg(t, SPEC.wall_start_s ?? 0.0, SPEC.wall_cover_s ?? 5.4));
      const darkenU = easeInOutCubic(seg(t, SPEC.darken_start_s ?? 2.8, SPEC.darken_end_s ?? 5.6));
      const stampAt = SPEC.stamp_at_s ?? 5.7;

      // 1. Dusty daylight sky darkening progressively into black-blizzard night
      const skyTopR = Math.round(lerp(212, 58, darkenU));
      const skyTopG = Math.round(lerp(208, 42, darkenU));
      const skyTopB = Math.round(lerp(202, 32, darkenU));
      const skyBotR = Math.round(lerp(228, 84, darkenU));
      const skyBotG = Math.round(lerp(220, 62, darkenU));
      const skyBotB = Math.round(lerp(206, 46, darkenU));
      const skyG = ctx.createLinearGradient(0, 0, 0, groundY);
      skyG.addColorStop(0, "rgb(" + skyTopR + "," + skyTopG + "," + skyTopB + ")");
      skyG.addColorStop(1, "rgb(" + skyBotR + "," + skyBotG + "," + skyBotB + ")");
      ctx.fillStyle = skyG;
      ctx.fillRect(0, 0, W, groundY);

      // 2. Hazy pale sun at upper right-center (swallowed by dust wall)
      const sunX = W * 0.56, sunY = H * 0.27;
      const sunA = clamp(1 - darkenU * 1.15, 0, 1);
      if (sunA > 0.01) {
        const sg = ctx.createRadialGradient(sunX, sunY, 20, sunX, sunY, 260);
        sg.addColorStop(0, "rgba(255, 250, 220, " + (0.95 * sunA).toFixed(3) + ")");
        sg.addColorStop(0.42, "rgba(248, 236, 188, " + (0.45 * sunA).toFixed(3) + ")");
        sg.addColorStop(1, "rgba(235, 215, 165, 0)");
        ctx.fillStyle = sg;
        ctx.beginPath(); ctx.arc(sunX, sunY, 260, 0, Math.PI * 2); ctx.fill();
      }

      // 3. Golden-ochre flat prairie ground
      const gndG = ctx.createLinearGradient(0, groundY, 0, H);
      gndG.addColorStop(0, "rgb(" + Math.round(lerp(206, 118, darkenU)) + "," + Math.round(lerp(154, 78, darkenU)) + "," + Math.round(lerp(100, 48, darkenU)) + ")");
      gndG.addColorStop(1, "rgb(" + Math.round(lerp(168, 74, darkenU)) + "," + Math.round(lerp(116, 46, darkenU)) + "," + Math.round(lerp(72, 28, darkenU)) + ")");
      ctx.fillStyle = gndG;
      ctx.fillRect(0, groundY, W, H - groundY);

      // 4. Tiny horizon silhouettes for terrifying height scale (person + windmill + farmhouse)
      ctx.save();
      ctx.fillStyle = "#3B2314";
      // Tiny human figure at x = 51.5%
      const px = W * 0.515;
      ctx.beginPath(); ctx.arc(px, groundY - 38, 6, 0, Math.PI * 2); ctx.fill();
      ctx.fillRect(px - 5, groundY - 31, 10, 17);
      ctx.fillRect(px - 5, groundY - 14, 4, 14);
      ctx.fillRect(px + 1, groundY - 14, 4, 14);
      // Farmhouse & barn silhouettes on right horizon
      ctx.fillRect(W * 0.78, groundY - 26, 44, 26);
      ctx.beginPath(); ctx.moveTo(W * 0.77, groundY - 26); ctx.lineTo(W * 0.80, groundY - 46); ctx.lineTo(W * 0.83, groundY - 26); ctx.fill();
      ctx.fillRect(W * 0.89, groundY - 32, 64, 32);
      ctx.beginPath(); ctx.moveTo(W * 0.885, groundY - 32); ctx.lineTo(W * 0.92, groundY - 54); ctx.lineTo(W * 0.955, groundY - 32); ctx.fill();
      // Spinning windmill at x = 71%
      const wx = W * 0.71;
      ctx.strokeStyle = "#3B2314";
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(wx - 8, groundY); ctx.lineTo(wx, groundY - 44); ctx.lineTo(wx + 8, groundY); ctx.stroke();
      ctx.save();
      ctx.translate(wx, groundY - 44);
      ctx.rotate(t * 2.2);
      for (let b = 0; b < 4; b++) {
        ctx.rotate(Math.PI * 0.5);
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0, -18); ctx.stroke();
      }
      ctx.restore();
      ctx.restore();

      // 5. Towering churning billowing dark-brown Dust Wall sweeping from left edge across frame
      const frontX = lerp(W * 0.24, W * 1.24, wallU);
      ctx.save();
      // Solid opaque body behind the billowing front
      const wallGrad = ctx.createLinearGradient(0, 0, frontX, 0);
      wallGrad.addColorStop(0, "rgb(" + Math.round(lerp(92, 54, darkenU)) + "," + Math.round(lerp(56, 32, darkenU)) + "," + Math.round(lerp(34, 20, darkenU)) + ")");
      wallGrad.addColorStop(0.75, "rgb(" + Math.round(lerp(136, 78, darkenU)) + "," + Math.round(lerp(88, 48, darkenU)) + "," + Math.round(lerp(54, 30, darkenU)) + ")");
      wallGrad.addColorStop(1, "rgba(136, 88, 54, 0)");
      ctx.fillStyle = wallGrad;
      ctx.fillRect(0, 0, frontX, groundY + 12);

      // Churning volumetric lobe puffs along the towering front edge (natural billowing storm wall)
      for (let i = 0; i < 48; i++) {
        const yFrac = i / 47;
        const py = yFrac * (groundY + 24) - 12;
        const n1 = Math.sin(yFrac * Math.PI * 3.1 + t * 0.9) * 58;
        const n2 = Math.cos(yFrac * Math.PI * 6.7 - t * 1.4 + i) * 38;
        const arch = Math.sin(yFrac * Math.PI) * 165;
        const pxEdge = frontX - 85 + arch + n1 + n2 - (1 - yFrac) * 75;
        const rad = 135 + hash(i * 17) * 155;
        const g = ctx.createRadialGradient(pxEdge - rad * 0.25, py - rad * 0.18, rad * 0.06, pxEdge, py, rad);
        g.addColorStop(0, "rgba(" + Math.round(lerp(116, 58, darkenU)) + "," + Math.round(lerp(72, 34, darkenU)) + "," + Math.round(lerp(42, 20, darkenU)) + ", 0.95)");
        g.addColorStop(0.55, "rgba(" + Math.round(lerp(144, 78, darkenU)) + "," + Math.round(lerp(94, 48, darkenU)) + "," + Math.round(lerp(58, 28, darkenU)) + ", 0.62)");
        g.addColorStop(1, "rgba(144, 94, 58, 0)");
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(pxEdge, py, rad, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();

      // 6. Vertical black dashed height ruler + stacked "2.5 mi / 4 km" measurement
      const rulerIn = easeOutCubic(seg(t, 0.35, 1.15));
      const rulerOut = 1 - seg(t, 4.1, 4.9);
      const rulerA = clamp(rulerIn * rulerOut, 0, 1);
      if (rulerA > 0.01) {
        const rx = W * 0.42;
        const topY = lerp(groundY, H * 0.015, rulerIn);
        ctx.save();
        ctx.globalAlpha = rulerA;
        ctx.strokeStyle = "#1E1610";
        ctx.lineWidth = 5;
        ctx.setLineDash([22, 16]);
        ctx.beginPath();
        ctx.moveTo(rx, groundY);
        ctx.lineTo(rx, topY);
        ctx.stroke();
        ctx.setLineDash([]);
        // Stacked dual-unit label with crisp horizontal divider
        const lx = rx + 145, ly = H * 0.375;
        ctx.fillStyle = "#9A4212";
        ctx.font = "800 76px 'Barlow Condensed', sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(SPEC.height_primary || "2.5 mi", lx, ly - 32);
        ctx.fillRect(lx - 108, ly + 8, 216, 5);
        ctx.font = "800 64px 'Barlow Condensed', sans-serif";
        ctx.fillText(SPEC.height_secondary || "4 km", lx, ly + 46);
        ctx.restore();
      }

      // 7. Heavy display stamp: "Black / Blizzards"
      if (t >= stampAt) {
        const s1 = easeOutBack(seg(t, stampAt, stampAt + 0.32));
        const s2 = easeOutBack(seg(t, stampAt + 0.32, stampAt + 0.64));
        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.shadowColor = "rgba(15, 8, 4, 0.72)";
        ctx.shadowBlur = 22;
        ctx.fillStyle = "#C6B0A0";
        if (s1 > 0.02) {
          ctx.save();
          ctx.translate(W * 0.5, H * 0.455);
          ctx.scale(s1, s1);
          ctx.font = "400 132px 'Archivo Black', sans-serif";
          ctx.fillText(SPEC.stamp_line1 || "Black", 0, 0);
          ctx.restore();
        }
        if (s2 > 0.02) {
          ctx.save();
          ctx.translate(W * 0.5, H * 0.535);
          ctx.scale(s2, s2);
          ctx.font = "400 124px 'Archivo Black', sans-serif";
          ctx.fillText(SPEC.stamp_line2 || "Blizzards", 0, 0);
          ctx.restore();
        }
        ctx.restore();
      }
    }

    function renderPortDepthCutaway(t) {
      const seaY = H * 0.355;
      const bedY = H * 0.725;
      const quayRightX = W * 0.315;
      const shipEnterS = SPEC.ship_enter_s ?? 0.2;
      const shipDockS = SPEC.ship_dock_s ?? 3.6;
      const rulerStartS = SPEC.ruler_start_s ?? 1.25;
      const rulerEndS = SPEC.ruler_end_s ?? 2.65;

      const shipU = easeOutCubic(seg(t, shipEnterS, shipDockS));
      const shipBob = Math.sin(t * 2.1) * 5.5;
      const shipX = lerp(W * 1.18, quayRightX + 46, shipU);

      // 1. Crisp tropical maritime sky gradient + soft drifting clouds
      const skyG = ctx.createLinearGradient(0, 0, 0, seaY);
      skyG.addColorStop(0, "#1D4E6B");
      skyG.addColorStop(0.55, "#4E94B3");
      skyG.addColorStop(1, "#A8D5E5");
      ctx.fillStyle = skyG;
      ctx.fillRect(0, 0, W, seaY + 8);

      ctx.fillStyle = "rgba(255,255,255,0.22)";
      for (let i = 0; i < 6; i++) {
        const cx = ((hash(i * 19) * W + t * (16 + i * 3)) % (W + 320)) - 160;
        const cy = H * (0.06 + hash(i * 31) * 0.17);
        const cw = 130 + hash(i * 41) * 140;
        ctx.beginPath();
        ctx.ellipse(cx, cy, cw * 0.5, 24 + (i % 3) * 8, 0, 0, Math.PI * 2);
        ctx.ellipse(cx + cw * 0.22, cy - 10, cw * 0.32, 20, 0, 0, Math.PI * 2);
        ctx.fill();
      }

      // 2. Stratified luminous deep-water ocean column (surface turquoise -> deep abyssal teal)
      const seaG = ctx.createLinearGradient(0, seaY, 0, bedY + 30);
      seaG.addColorStop(0, "#0E85A3");
      seaG.addColorStop(0.32, "#0A5D77");
      seaG.addColorStop(0.75, "#063B50");
      seaG.addColorStop(1, "#042333");
      ctx.fillStyle = seaG;
      ctx.fillRect(0, seaY, W, bedY - seaY + 40);

      // Sunlit underwater caustic shafts filtering through deep water
      ctx.save();
      for (let i = 0; i < 8; i++) {
        const rx = W * (0.34 + i * 0.095) + Math.sin(t * 0.9 + i * 1.4) * 26;
        const rw = 52 + (i % 3) * 24;
        const rg = ctx.createLinearGradient(rx, seaY, rx - 70, bedY);
        rg.addColorStop(0, "rgba(124, 224, 249, 0.16)");
        rg.addColorStop(0.7, "rgba(56, 189, 248, 0.05)");
        rg.addColorStop(1, "rgba(56, 189, 248, 0)");
        ctx.fillStyle = rg;
        ctx.beginPath();
        ctx.moveTo(rx - rw * 0.4, seaY);
        ctx.lineTo(rx + rw * 0.4, seaY);
        ctx.lineTo(rx + rw * 0.9 - 90, bedY);
        ctx.lineTo(rx - rw * 0.9 - 90, bedY);
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();

      // Gentle underwater rising bubbles & suspended particles
      ctx.fillStyle = "rgba(186, 230, 253, 0.28)";
      for (let i = 0; i < 42; i++) {
        const bx = quayRightX + 20 + hash(i * 17.3) * (W - quayRightX - 30);
        const by = bedY - (((hash(i * 29.1) * (bedY - seaY) + t * (24 + (i % 4) * 9))) % (bedY - seaY - 12));
        const br = 2.5 + hash(i * 7.7) * 5.0;
        ctx.beginPath(); ctx.arc(bx, by, br, 0, Math.PI * 2); ctx.fill();
      }

      // 3. Stratified Seabed floor + bedrock cross-section (y: 72.5%..100%)
      const bedStrata = [
        { y0: bedY, y1: H * 0.785, col: "#5E4934" },
        { y0: H * 0.785, y1: H * 0.875, col: "#3F3025" },
        { y0: H * 0.875, y1: H, col: "#231B16" },
      ];
      for (let s = 0; s < bedStrata.length; s++) {
        const st = bedStrata[s];
        ctx.fillStyle = st.col;
        ctx.beginPath();
        ctx.moveTo(0, st.y0);
        for (let x = 0; x <= W; x += 48) {
          const wv = Math.sin(x * 0.011 + s * 1.9) * (s === 0 ? 7 : 12) + Math.cos(x * 0.024 + s) * 4;
          ctx.lineTo(x, st.y0 + wv);
        }
        ctx.lineTo(W, st.y1 + 20);
        ctx.lineTo(0, st.y1 + 20);
        ctx.closePath();
        ctx.fill();
      }
      // Subtle seabed rock speckles
      for (let i = 0; i < 65; i++) {
        const sx = hash(i * 21.1) * W;
        const sy = bedY + 14 + hash(i * 37.3) * (H - bedY - 24);
        ctx.fillStyle = i % 2 === 0 ? "rgba(255,235,205,0.10)" : "rgba(10,8,6,0.28)";
        ctx.beginPath(); ctx.ellipse(sx, sy, 6 + hash(i) * 10, 4 + hash(i * 3) * 5, hash(i) * 2, 0, Math.PI * 2); ctx.fill();
      }

      // 4. Concrete Deep-Water Quay Wall (Dermaga CT3 Sabang) on left
      const quayTopY = seaY - 58;
      const quayGrad = ctx.createLinearGradient(0, quayTopY, quayRightX, quayTopY);
      quayGrad.addColorStop(0, "#475569");
      quayGrad.addColorStop(0.75, "#64748B");
      quayGrad.addColorStop(1, "#94A3B8");
      ctx.fillStyle = quayGrad;
      ctx.fillRect(0, quayTopY, quayRightX, bedY - quayTopY + 34);
      // Concrete vertical caisson seams + steel fenders
      ctx.strokeStyle = "rgba(15, 23, 42, 0.35)";
      ctx.lineWidth = 3;
      for (let cx = 64; cx < quayRightX; cx += 64) {
        ctx.beginPath(); ctx.moveTo(cx, quayTopY); ctx.lineTo(cx, bedY + 26); ctx.stroke();
      }
      // Yellow safety coping stripe along top edge of quay
      ctx.fillStyle = "#FACC15";
      ctx.fillRect(0, quayTopY, quayRightX, 11);
      // Black rubber dock fenders facing ship
      ctx.fillStyle = "#0F172A";
      for (const fy of [seaY - 34, seaY - 6, seaY + 28]) {
        ctx.fillRect(quayRightX - 4, fy, 14, 22);
      }

      // Stacked containers waiting on CT3 terminal apron
      const pierBoxes = [
        [20, quayTopY - 40, 82, 40, "#0EA5E9"],
        [108, quayTopY - 40, 82, 40, "#F59E0B"],
        [46, quayTopY - 80, 82, 40, "#10B981"],
      ];
      for (const [bx, by, bw, bh, bc] of pierBoxes) {
        ctx.fillStyle = bc;
        ctx.fillRect(bx, by, bw, bh);
        ctx.strokeStyle = "#0F172A"; ctx.lineWidth = 2.5;
        ctx.strokeRect(bx, by, bw, bh);
      }

      // Towering Crimson & White Ship-to-Shore (STS) Gantry Crane on CT3 pier
      ctx.save();
      const crBaseX = quayRightX - 74;
      ctx.strokeStyle = "#DC2626";
      ctx.lineWidth = 14;
      ctx.lineCap = "round";
      ctx.beginPath();
      // Main portal legs
      ctx.moveTo(crBaseX - 66, quayTopY); ctx.lineTo(crBaseX - 38, quayTopY - 265);
      ctx.moveTo(crBaseX + 42, quayTopY); ctx.lineTo(crBaseX + 18, quayTopY - 265);
      // Top crossbeam + extended boom reaching over the ship
      ctx.moveTo(crBaseX - 140, quayTopY - 195); ctx.lineTo(crBaseX + 295, quayTopY - 195);
      ctx.stroke();
      // Crane apex & diagonal tension stays
      ctx.strokeStyle = "#F8FAFC";
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.moveTo(crBaseX - 38, quayTopY - 265); ctx.lineTo(crBaseX + 18, quayTopY - 265);
      ctx.moveTo(crBaseX - 10, quayTopY - 310); ctx.lineTo(crBaseX - 38, quayTopY - 265);
      ctx.moveTo(crBaseX - 10, quayTopY - 310); ctx.lineTo(crBaseX + 18, quayTopY - 265);
      ctx.moveTo(crBaseX - 10, quayTopY - 310); ctx.lineTo(crBaseX + 275, quayTopY - 195);
      ctx.moveTo(crBaseX - 10, quayTopY - 310); ctx.lineTo(crBaseX - 125, quayTopY - 195);
      ctx.stroke();
      // Animated crane trolley sliding out toward ship + dangling yellow spreader
      const trX = crBaseX + lerp(55, 195, easeInOutCubic(seg(t, 1.4, 5.2)));
      ctx.fillStyle = "#FACC15";
      ctx.fillRect(trX - 24, quayTopY - 208, 48, 20);
      ctx.strokeStyle = "#E2E8F0"; ctx.lineWidth = 3;
      const dropY = quayTopY - 115 + Math.sin(t * 2.2) * 14;
      ctx.beginPath();
      ctx.moveTo(trX - 12, quayTopY - 188); ctx.lineTo(trX - 12, dropY);
      ctx.moveTo(trX + 12, quayTopY - 188); ctx.lineTo(trX + 12, dropY);
      ctx.stroke();
      ctx.fillStyle = "#F59E0B";
      ctx.fillRect(trX - 32, dropY, 64, 16);
      ctx.restore();

      // 5. Giant Mega Container Vessel (side profile showing deep underwater draft!)
      const draftPx = 225; // ~15.5m submerged draft vs >22m (~355px) seabed depth!
      const hullTopY = seaY - 92 + shipBob;
      const keelY = seaY + draftPx + shipBob;
      ctx.save();
      ctx.translate(shipX, 0);
      // Submerged deep red anti-fouling lower hull + bulbous bow
      ctx.fillStyle = "#991B1B";
      ctx.strokeStyle = "#1E293B";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(14, seaY + shipBob);
      ctx.lineTo(680, seaY + shipBob);
      ctx.lineTo(680, keelY);
      ctx.lineTo(54, keelY);
      ctx.quadraticCurveTo(-18, keelY - 6, -24, keelY - 46);
      ctx.quadraticCurveTo(-24, keelY - 82, 22, keelY - 90);
      ctx.lineTo(14, seaY + shipBob);
      ctx.closePath();
      ctx.fill(); ctx.stroke();

      // Upper dark slate steel freeboard hull above waterline
      ctx.fillStyle = "#0F172A";
      ctx.beginPath();
      ctx.moveTo(-22, hullTopY);
      ctx.lineTo(680, hullTopY);
      ctx.lineTo(680, seaY + shipBob + 4);
      ctx.lineTo(14, seaY + shipBob + 4);
      ctx.closePath();
      ctx.fill(); ctx.stroke();
      // White Plimsoll waterline stripe
      ctx.fillStyle = "#F8FAFC";
      ctx.fillRect(10, seaY + shipBob - 5, 670, 8);

      // Towering colorful container stacks on deck (4 tiers high)
      const cCols = ["#E11D48", "#F59E0B", "#0EA5E9", "#10B981", "#F97316", "#38BDF8", "#84CC16", "#DC2626"];
      const boxW = 76, boxH = 36, gap = 5;
      for (let col = 0; col < 6; col++) {
        const tiers = col === 0 ? 3 : 4;
        for (let tier = 0; tier < tiers; tier++) {
          const bx = 56 + col * (boxW + gap);
          const by = hullTopY - (tier + 1) * (boxH + 2);
          ctx.fillStyle = cCols[(col * 3 + tier * 2) % cCols.length];
          ctx.fillRect(bx, by, boxW, boxH);
          ctx.strokeStyle = "#0F172A";
          ctx.lineWidth = 2.5;
          ctx.strokeRect(bx, by, boxW, boxH);
          // Subtle rib highlight
          ctx.fillStyle = "rgba(255,255,255,0.18)";
          ctx.fillRect(bx + 3, by + 3, boxW - 6, 7);
        }
      }
      // White bridge superstructure tower behind stacks
      ctx.fillStyle = "#F8FAFC";
      ctx.fillRect(556, hullTopY - 210, 96, 210);
      ctx.strokeStyle = "#1E293B"; ctx.lineWidth = 3.5;
      ctx.strokeRect(556, hullTopY - 210, 96, 210);
      // Dark panoramic bridge windows
      ctx.fillStyle = "#0F172A";
      ctx.fillRect(546, hullTopY - 190, 62, 18);
      // Funnel stack
      ctx.fillStyle = "#DC2626";
      ctx.fillRect(612, hullTopY - 256, 36, 46);
      ctx.restore();

      // 6. Animated glowing sea surface wave crest over ship waterline
      ctx.save();
      ctx.strokeStyle = "rgba(224, 247, 255, 0.88)";
      ctx.lineWidth = 6;
      ctx.beginPath();
      for (let x = quayRightX; x <= W; x += 14) {
        const wy = seaY + Math.sin(x * 0.025 + t * 3.8) * 5.5 + Math.cos(x * 0.052 - t * 2.4) * 2.5;
        if (x === quayRightX) ctx.moveTo(x, wy); else ctx.lineTo(x, wy);
      }
      ctx.stroke();
      ctx.restore();

      // 7. Animated Vertical Dashed Depth Ruler (0 m -> >22 METER down to seabed!)
      const rulerP = easeOutCubic(seg(t, rulerStartS, rulerEndS));
      if (rulerP > 0.01) {
        const rx = quayRightX + 34;
        const botY = lerp(seaY, bedY - 4, rulerP);
        ctx.save();
        // Dashed luminous cyan-amber depth rail
        ctx.strokeStyle = "#FACC15";
        ctx.lineWidth = 6;
        ctx.setLineDash([18, 12]);
        ctx.beginPath();
        ctx.moveTo(rx, seaY);
        ctx.lineTo(rx, botY);
        ctx.stroke();
        ctx.setLineDash([]);
        // Top & bottom T-ticks
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 5;
        ctx.beginPath();
        ctx.moveTo(rx - 18, seaY); ctx.lineTo(rx + 18, seaY);
        ctx.moveTo(rx - 18, botY); ctx.lineTo(rx + 18, botY);
        ctx.stroke();
        // Depth tick marks every 5m
        ctx.font = "700 28px 'IBM Plex Mono', monospace";
        ctx.fillStyle = "#BAE6FD";
        ctx.textAlign = "right";
        ctx.textBaseline = "middle";
        const ticks = [[0.23, "5 m"], [0.45, "10 m"], [0.68, "15 m"], [0.91, "20 m"]];
        for (const [frac, lbl] of ticks) {
          const ty = lerp(seaY, bedY - 4, frac);
          if (ty <= botY + 2) {
            ctx.strokeStyle = "rgba(186, 230, 253, 0.72)";
            ctx.lineWidth = 3;
            ctx.beginPath(); ctx.moveTo(rx - 12, ty); ctx.lineTo(rx + 6, ty); ctx.stroke();
            ctx.fillText(lbl, rx - 20, ty);
          }
        }
        // Clean editorial depth readout (Montserrat geometric sans, zero neon, crisp horizontal divider)
        const depthVal = Math.round(lerp(0, SPEC.depth_target_m ?? 22, rulerP));
        const depthTxt = (rulerP > 0.96 && SPEC.depth_primary) ? SPEC.depth_primary : (">" + depthVal + " meter");
        ctx.textAlign = "left";
        ctx.shadowColor = "rgba(3, 18, 28, 0.55)";
        ctx.shadowBlur = 16;
        ctx.shadowOffsetY = 4;
        ctx.fillStyle = "#F4F1EA";
        ctx.font = "900 66px 'Montserrat', sans-serif";
        ctx.fillText(depthTxt, rx + 28, H * 0.542);
        const depthW = Math.min(340, ctx.measureText(depthTxt).width);
        ctx.fillStyle = "rgba(244, 241, 234, 0.78)";
        ctx.fillRect(rx + 28, H * 0.566, depthW, 4);
        ctx.fillStyle = "#CBE7F5";
        ctx.font = "700 30px 'Montserrat', sans-serif";
        ctx.fillText(SPEC.depth_secondary || "Kedalaman kolam", rx + 28, H * 0.590);

        // Keel clearance emerald bracket beneath ship hull (right side, zero overlap)
        if (shipU > 0.72 && rulerP > 0.82) {
          const clrA = easeOutCubic(seg(t, shipDockS - 0.5, shipDockS + 0.3));
          const kx = W * 0.86;
          ctx.globalAlpha = clrA;
          ctx.strokeStyle = "#86EFAC";
          ctx.lineWidth = 4.5;
          ctx.beginPath();
          ctx.moveTo(kx, keelY + 6); ctx.lineTo(kx, bedY - 6);
          ctx.moveTo(kx - 14, keelY + 6); ctx.lineTo(kx + 14, keelY + 6);
          ctx.moveTo(kx - 14, bedY - 6); ctx.lineTo(kx + 14, bedY - 6);
          ctx.stroke();
          ctx.fillStyle = "#DCFCE7";
          ctx.font = "700 24px 'Montserrat', sans-serif";
          ctx.textAlign = "center";
          ctx.fillText(SPEC.clearance_label || "Lunas aman", kx, (keelY + bedY) * 0.5);
        }
        ctx.restore();
      }

      // 8. Clean editorial Title Case top header ("Dermaga CT3 Sabang")
      const titleA = easeOutCubic(seg(t, 0.15, 0.65));
      if (titleA > 0.01) {
        ctx.save();
        ctx.globalAlpha = titleA;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.shadowColor = "rgba(3, 18, 28, 0.45)";
        ctx.shadowBlur = 18;
        ctx.shadowOffsetY = 5;
        ctx.fillStyle = "#F4F1EA";
        ctx.font = "900 64px 'Montserrat', sans-serif";
        ctx.fillText(SPEC.port_title || "Dermaga CT3 Sabang", W * 0.5, H * 0.105);
        ctx.restore();
      }
    }

    // Optional radial zoom blur at act boundaries (cut_blur_in_s / cut_blur_out_s)
    window.__renderCutaway = function(t) {
      ctx.clearRect(0, 0, W, H);
      const preset = SPEC.preset || "soil_root_cutaway";
      if (preset === "dust_wall_horizon") {
        renderDustWallHorizon(t);
      } else if (preset === "port_depth_cutaway") {
        renderPortDepthCutaway(t);
      } else {
        renderSoilRootCutaway(t);
      }

      const dur = SPEC.duration_s || 8.0;
      const inS = SPEC.cut_blur_in_s || 0;
      const outS = SPEC.cut_blur_out_s || 0;
      const str = SPEC.cut_blur_strength ?? 0.22;
      let blurAmt = 0;
      if (inS > 0 && t < inS) {
        const u = 1 - t / inS;
        blurAmt = Math.max(blurAmt, u * u * str);
      }
      if (outS > 0 && t > dur - outS) {
        const u = clamp((t - (dur - outS)) / outS, 0, 1);
        blurAmt = Math.max(blurAmt, u * u * str);
      }

      outCtx.clearRect(0, 0, W, H);
      if (blurAmt <= 0.002) {
        outCtx.drawImage(buf, 0, 0);
      } else {
        const samples = 10;
        outCtx.save();
        for (let i = 0; i < samples; i++) {
          const f = i / (samples - 1);
          const sc = 1 + f * blurAmt;
          outCtx.globalAlpha = i === 0 ? 1.0 : 1.0 / (i + 1);
          outCtx.save();
          outCtx.translate(W * 0.5, H * 0.5);
          outCtx.scale(sc, sc);
          outCtx.drawImage(buf, -W * 0.5, -H * 0.5);
          outCtx.restore();
        }
        outCtx.restore();
      }
    };
  </script>
</body>
</html>`;
}

