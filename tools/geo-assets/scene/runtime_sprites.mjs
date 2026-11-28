export function buildSpritesRuntime() {
  return `
    function drawHumanFigure(x, y, h, color = "#FFFFFF", alpha = 1.0) {
      if (alpha <= 0.005 || h <= 1) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      ctx.shadowColor = "rgba(0,0,0,0.65)";
      ctx.shadowBlur = Math.max(4, h * 0.14);
      ctx.shadowOffsetY = 2;
      ctx.fillStyle = color;
      // Head
      const headR = h * 0.135;
      ctx.beginPath();
      ctx.arc(0, -h * 0.37, headR, 0, Math.PI * 2);
      ctx.fill();
      // Torso + arms (clean pill silhouette)
      const w = h * 0.38;
      ctx.beginPath();
      ctx.roundRect(-w * 0.5, -h * 0.20, w, h * 0.38, w * 0.36);
      ctx.fill();
      // Legs
      const legW = w * 0.34;
      const legGap = w * 0.12;
      ctx.beginPath();
      ctx.roundRect(-legGap * 0.5 - legW, h * 0.10, legW, h * 0.38, legW * 0.45);
      ctx.roundRect(legGap * 0.5, h * 0.10, legW, h * 0.38, legW * 0.45);
      ctx.fill();
      ctx.restore();
    }

    function drawLandmarkSilhouette(x, y, heightPx, landmark = "statue_of_liberty", { fillHex = "#94A3B8", accentHex = "#CBD5E1", rimHex = "#E2E8F0", alpha = 1.0, riseProgress = 1.0, time = 0, angleDeg = 0 } = {}) {
      if (alpha <= 0.005 || heightPx <= 2 || riseProgress <= 0.01) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      // Ground shadow anchor beneath structure so it sits physically on terrain
      const shS = heightPx / 200;
      ctx.save();
      ctx.fillStyle = "rgba(2, 10, 14, 0.44)";
      ctx.beginPath();
      ctx.ellipse(0, 4 * shS, 42 * shS * clamp(riseProgress, 0.3, 1), 12 * shS * clamp(riseProgress, 0.3, 1), 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      // Clip from baseline upward so the monument rises out of the map anchor cleanly
      ctx.beginPath();
      ctx.rect(-heightPx * 1.05, -heightPx * 1.35, heightPx * 2.1, heightPx * 1.45);
      ctx.clip();
      const slideY = (1 - riseProgress) * heightPx * 1.15;
      ctx.translate(0, slideY);
      const s = heightPx / 200;
      ctx.scale(s, s);
      ctx.shadowColor = "rgba(0,0,0,0.65)";
      ctx.shadowBlur = 14;
      ctx.shadowOffsetY = 5;

      if (landmark === "statue_of_liberty") {
        // Pedestal base
        ctx.fillStyle = "#64748B";
        ctx.beginPath();
        ctx.roundRect(-24, -18, 48, 18, 3);
        ctx.fill();
        // Draped robe & body silhouette
        const grad = ctx.createLinearGradient(-22, -160, 26, -18);
        grad.addColorStop(0, accentHex);
        grad.addColorStop(0.55, fillHex);
        grad.addColorStop(1, "#475569");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(-20, -18);
        ctx.lineTo(-16, -95);
        ctx.lineTo(-22, -124);
        ctx.lineTo(-10, -138);
        // Raised torch arm (right side)
        ctx.lineTo(14, -142);
        ctx.lineTo(22, -182);
        ctx.lineTo(29, -182);
        ctx.lineTo(24, -132);
        ctx.lineTo(18, -95);
        ctx.lineTo(21, -18);
        ctx.closePath();
        ctx.fill();
        // Tablet in left arm
        ctx.fillStyle = "#475569";
        ctx.beginPath();
        ctx.roundRect(-24, -118, 13, 22, 2);
        ctx.fill();
        // Head & 7-ray crown
        ctx.fillStyle = accentHex;
        ctx.beginPath();
        ctx.arc(-1, -149, 10, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = rimHex;
        ctx.lineWidth = 2.4;
        ctx.lineCap = "round";
        for (let i = -3; i <= 3; i++) {
          const ang = -Math.PI * 0.5 + i * 0.34;
          ctx.beginPath();
          ctx.moveTo(-1 + Math.cos(ang) * 9, -151 + Math.sin(ang) * 9);
          ctx.lineTo(-1 + Math.cos(ang) * 19, -151 + Math.sin(ang) * 19);
          ctx.stroke();
        }
        // Torch cup & flame
        ctx.fillStyle = "#CBD5E1";
        ctx.beginPath();
        ctx.roundRect(19, -187, 13, 7, 2);
        ctx.fill();
        ctx.fillStyle = "#FACC15";
        ctx.shadowColor = "#F59E0B";
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.moveTo(25.5, -203);
        ctx.quadraticCurveTo(32, -193, 25.5, -186);
        ctx.quadraticCurveTo(19, -193, 25.5, -203);
        ctx.fill();
      } else if (landmark === "transmission_tower") {
        // Steel HVDC lattice transmission pylon with cross-arms and energized insulator terminals
        ctx.strokeStyle = rimHex;
        ctx.fillStyle = fillHex;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        // Concrete foundation pads
        ctx.fillRect(-38, -8, 16, 8);
        ctx.fillRect(22, -8, 16, 8);
        // Main tapered lattice legs
        ctx.lineWidth = 5.5;
        ctx.beginPath();
        ctx.moveTo(-30, -8); ctx.lineTo(-10, -158); ctx.lineTo(0, -188);
        ctx.moveTo(30, -8); ctx.lineTo(10, -158); ctx.lineTo(0, -188);
        ctx.stroke();
        // Horizontal cross-arms (lower and upper)
        ctx.lineWidth = 5.0;
        ctx.beginPath();
        ctx.moveTo(-54, -108); ctx.lineTo(54, -108);
        ctx.moveTo(-40, -148); ctx.lineTo(40, -148);
        ctx.stroke();
        // Cross-arm diagonal braces
        ctx.lineWidth = 3.0;
        ctx.beginPath();
        ctx.moveTo(-54, -108); ctx.lineTo(-16, -94);
        ctx.moveTo(54, -108); ctx.lineTo(16, -94);
        ctx.moveTo(-40, -148); ctx.lineTo(-12, -134);
        ctx.moveTo(40, -148); ctx.lineTo(12, -134);
        // Body X-bracing bays
        const bays = [[-8, -42, 30, 24], [-42, -76, 24, 19], [-76, -108, 19, 15], [-108, -148, 15, 11]];
        for (const [y0, y1, w0, w1] of bays) {
          ctx.moveTo(-w0, y0); ctx.lineTo(w1, y1);
          ctx.moveTo(w0, y0); ctx.lineTo(-w1, y1);
          ctx.moveTo(-w1, y1); ctx.lineTo(w1, y1);
        }
        ctx.stroke();
        // Suspended insulator strings & glowing energized terminals
        ctx.shadowBlur = 12;
        ctx.shadowColor = accentHex;
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 3.0;
        for (const [ix, iy] of [[-52, -108], [52, -108], [-38, -148], [38, -148]]) {
          ctx.beginPath(); ctx.moveTo(ix, iy); ctx.lineTo(ix, iy + 14); ctx.stroke();
          ctx.fillStyle = accentHex;
          ctx.beginPath(); ctx.arc(ix, iy + 16, 5.5, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = "#FFFFFF";
          ctx.beginPath(); ctx.arc(ix, iy + 16, 2.3, 0, Math.PI * 2); ctx.fill();
        }
        // Earth-wire apex beacon
        ctx.fillStyle = accentHex;
        ctx.beginPath(); ctx.arc(0, -190, 4.5, 0, Math.PI * 2); ctx.fill();
      } else if (landmark === "solar_array") {
        // Isometric perspective solar panel bank with tilted PV cell grid and animated sun glint
        const panels = [[-46, -18], [4, -18], [-34, -58], [16, -58]];
        for (let pi = 0; pi < panels.length; pi++) {
          const [px, py] = panels[pi];
          // Support stanchion
          ctx.fillStyle = "#64748B";
          ctx.fillRect(px + 14, py + 12, 5, 16);
          ctx.save();
          ctx.translate(px, py);
          // Tilted panel quad
          ctx.beginPath();
          ctx.moveTo(-22, 12);
          ctx.lineTo(24, 12);
          ctx.lineTo(34, -16);
          ctx.lineTo(-12, -16);
          ctx.closePath();
          const pg = ctx.createLinearGradient(-18, -16, 30, 12);
          pg.addColorStop(0, fillHex === "#94A3B8" ? "#1E3A8A" : fillHex);
          pg.addColorStop(1, "#0F172A");
          ctx.fillStyle = pg;
          ctx.fill();
          ctx.strokeStyle = rimHex;
          ctx.lineWidth = 2.4;
          ctx.stroke();
          // PV cell grid lines
          ctx.strokeStyle = "rgba(147, 197, 253, 0.45)";
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          for (const f of [0.33, 0.66]) {
            ctx.moveTo(lerp(-22, 24, f), 12); ctx.lineTo(lerp(-12, 34, f), -16);
            ctx.moveTo(lerp(-22, -12, f), lerp(12, -16, f)); ctx.lineTo(lerp(24, 34, f), lerp(12, -16, f));
          }
          ctx.stroke();
          // Subtle sunlit glint sweep
          const glint = 0.5 + 0.5 * Math.sin(time * 3.4 + pi * 1.3);
          ctx.fillStyle = rgbaStr(accentHex === "#CBD5E1" ? "#FDE047" : accentHex, 0.16 + glint * 0.24);
          ctx.beginPath();
          ctx.moveTo(-12, 8); ctx.lineTo(2, 8); ctx.lineTo(10, -12); ctx.lineTo(-4, -12);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        }
      } else if (landmark === "substation_hub") {
        // HVDC converter terminal station with glowing energy bolt crest
        ctx.fillStyle = "#1E293B";
        ctx.strokeStyle = rimHex;
        ctx.lineWidth = 3.2;
        ctx.beginPath();
        ctx.roundRect(-48, -56, 96, 56, 6);
        ctx.fill();
        ctx.stroke();
        // Roof deck & transformer bushings
        ctx.fillStyle = "#334155";
        ctx.fillRect(-42, -68, 84, 12);
        for (const bx of [-28, 0, 28]) {
          ctx.strokeStyle = rimHex;
          ctx.lineWidth = 3.5;
          ctx.beginPath(); ctx.moveTo(bx, -68); ctx.lineTo(bx, -88); ctx.stroke();
          ctx.fillStyle = accentHex;
          ctx.shadowColor = accentHex;
          ctx.shadowBlur = 12;
          ctx.beginPath(); ctx.arc(bx, -91, 5, 0, Math.PI * 2); ctx.fill();
        }
        // Central energized lightning bolt
        ctx.fillStyle = accentHex;
        ctx.beginPath();
        ctx.moveTo(4, -46); ctx.lineTo(-12, -26); ctx.lineTo(-1, -26);
        ctx.lineTo(-7, -8); ctx.lineTo(13, -30); ctx.lineTo(2, -30);
        ctx.closePath();
        ctx.fill();
      } else if (landmark === "survey_vessel") {
        // Ocean cable-laying / survey ship with bow wake and rotating radar mast
        ctx.save();
        ctx.translate(0, -18);
        if (angleDeg) ctx.rotate((angleDeg * Math.PI) / 180);
        // Subtle ocean wake V behind stern
        ctx.strokeStyle = "rgba(124, 224, 249, 0.55)";
        ctx.lineWidth = 2.6;
        ctx.beginPath();
        ctx.moveTo(-44, 4); ctx.lineTo(-74, -12);
        ctx.moveTo(-44, 10); ctx.lineTo(-74, 26);
        ctx.stroke();
        // Hull
        ctx.fillStyle = fillHex === "#94A3B8" ? "#0F172A" : fillHex;
        ctx.strokeStyle = rimHex;
        ctx.lineWidth = 2.8;
        ctx.beginPath();
        ctx.moveTo(-48, 12);
        ctx.lineTo(36, 12);
        ctx.lineTo(58, -4);
        ctx.lineTo(44, -10);
        ctx.lineTo(-44, -10);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        // Superstructure & bridge
        ctx.fillStyle = "#F8FAFC";
        ctx.fillRect(-16, -26, 36, 16);
        ctx.fillStyle = "#38BDF8";
        ctx.fillRect(6, -22, 11, 6);
        // Cable reel drum on stern deck
        ctx.fillStyle = accentHex;
        ctx.beginPath();
        ctx.arc(-30, -16, 10, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#0F172A";
        ctx.lineWidth = 2;
        ctx.stroke();
        // Mast + radar ping dot
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.moveTo(-2, -26); ctx.lineTo(-2, -44); ctx.stroke();
        ctx.fillStyle = accentHex;
        ctx.beginPath(); ctx.arc(-2, -46, 4, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      } else if (landmark === "gavel") {
        // Editorial permit/leverage gavel with strike base and subtle impact ring
        const strike = Math.sin(clamp(riseProgress, 0, 1) * Math.PI * 0.5);
        const swingAng = lerp(-0.58, 0.06, strike);
        // Sound block base
        ctx.fillStyle = "#451A03";
        ctx.strokeStyle = rimHex;
        ctx.lineWidth = 2.4;
        ctx.beginPath();
        ctx.roundRect(-34, -16, 68, 14, 4);
        ctx.fill();
        ctx.stroke();
        // Swinging hammer
        ctx.save();
        ctx.translate(22, -22);
        ctx.rotate(swingAng);
        // Handle
        ctx.fillStyle = "#B45309";
        ctx.strokeStyle = "#FEF3C7";
        ctx.lineWidth = 2.2;
        ctx.beginPath();
        ctx.roundRect(-42, -5, 76, 10, 4);
        ctx.fill();
        ctx.stroke();
        // Head
        ctx.fillStyle = fillHex === "#94A3B8" ? "#F59E0B" : fillHex;
        ctx.beginPath();
        ctx.roundRect(-52, -24, 24, 48, 5);
        ctx.fill();
        ctx.strokeStyle = accentHex;
        ctx.lineWidth = 2.8;
        ctx.stroke();
        ctx.restore();
      } else {
        // Generic monument spire
        ctx.fillStyle = fillHex;
        ctx.beginPath();
        ctx.moveTo(-16, 0);
        ctx.lineTo(-9, -155);
        ctx.lineTo(0, -195);
        ctx.lineTo(9, -155);
        ctx.lineTo(16, 0);
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();
    }

    function drawShadedCloud(x, y, radiusPx, alpha, tLocal, seed = 1, shadowDx = 14, shadowDy = 36) {
      if (alpha <= 0.005 || radiusPx <= 2) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      const s = radiusPx / 90;
      ctx.scale(s, s);
      // Soft elongated ground shadow cast clearly beneath cloud onto terrain
      ctx.save();
      ctx.translate(shadowDx, shadowDy);
      ctx.scale(1.55, 0.42);
      const sh = ctx.createRadialGradient(0, 0, 10, 0, 0, 105);
      sh.addColorStop(0, "rgba(2, 10, 14, 0.62)");
      sh.addColorStop(0.55, "rgba(2, 10, 14, 0.28)");
      sh.addColorStop(1, "rgba(2, 10, 14, 0)");
      ctx.fillStyle = sh;
      ctx.beginPath();
      ctx.arc(0, 0, 105, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      // Elongated realistic cumulus/stratocumulus silhouette (wider than tall, crisp sunlit tops)
      ctx.save();
      ctx.scale(1.22, 0.56);
      const puffs = [
        [-84, 14, 38, 0.86], [-48, -14, 52, 0.95], [-6, -24, 62, 0.99],
        [40, -14, 54, 0.96], [78, 8, 42, 0.88], [-24, 16, 48, 0.94],
        [24, 16, 46, 0.92], [102, 18, 28, 0.78],
      ];
      for (let i = 0; i < puffs.length; i++) {
        const [px, py, pr, pa] = puffs[i];
        const jx = Math.sin(seed * 7.1 + i * 2.3 + tLocal * 1.1) * 3.5;
        const jy = Math.cos(seed * 5.3 + i * 1.9 + tLocal * 0.8) * 2.2;
        const cx = px + jx, cy = py + jy;
        const g = ctx.createRadialGradient(cx - pr * 0.22, cy - pr * 0.36, pr * 0.12, cx, cy, pr);
        g.addColorStop(0, "rgba(255, 255, 255, " + pa + ")");
        g.addColorStop(0.56, "rgba(238, 244, 249, " + (pa * 0.95) + ")");
        g.addColorStop(0.84, "rgba(176, 192, 204, " + (pa * 0.58) + ")");
        g.addColorStop(1, "rgba(142, 162, 178, 0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(cx, cy, pr, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
      ctx.restore();
    }

    function samplePolylineCoord(coords, u) {
      if (!coords || coords.length === 0) return [0, 0];
      if (coords.length === 1) return coords[0];
      const p = clamp(u, 0, 1);
      const segLens = [];
      let total = 0;
      for (let i = 1; i < coords.length; i++) {
        const d = Math.hypot(coords[i][0] - coords[i - 1][0], coords[i][1] - coords[i - 1][1]);
        segLens.push(d);
        total += d;
      }
      if (total <= 1e-6) return coords[0];
      const target = total * p;
      let acc = 0;
      for (let i = 0; i < segLens.length; i++) {
        if (acc + segLens[i] >= target || i === segLens.length - 1) {
          const f = segLens[i] > 1e-6 ? clamp((target - acc) / segLens[i], 0, 1) : 0;
          return [
            lerp(coords[i][0], coords[i + 1][0], f),
            lerp(coords[i][1], coords[i + 1][1], f),
          ];
        }
        acc += segLens[i];
      }
      return coords[coords.length - 1];
    }

    function drawWindStreamline(coords, headU, tailFrac, { widthPx = 4.5, color = "#FFFFFF", glowHex = "#7CE0F9", alpha = 1.0 } = {}) {
      if (alpha <= 0.005 || !coords || coords.length < 2) return;
      const u1 = clamp(headU, 0, 1 + tailFrac);
      const u0 = u1 - tailFrac;
      const segStart = clamp(u0, 0, 1);
      const segEnd = clamp(u1, 0, 1);
      if (segEnd - segStart <= 0.005) return;
      const steps = 28;
      const pts = [];
      for (let i = 0; i <= steps; i++) {
        const u = lerp(segStart, segEnd, i / steps);
        const c = samplePolylineCoord(coords, u);
        const pt = projectPointSafe(c);
        if (pt) pts.push(pt);
      }
      if (pts.length < 2) return;
      ctx.save();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      for (let i = 1; i < pts.length; i++) {
        const frac = i / (pts.length - 1);
        const taper = Math.sin(frac * Math.PI);
        const segAlpha = alpha * Math.pow(frac, 0.8) * (0.25 + 0.75 * taper);
        if (segAlpha <= 0.01) continue;
        ctx.strokeStyle = rgbaStr(color, segAlpha);
        ctx.lineWidth = Math.max(1.2, widthPx * (0.28 + 0.72 * taper));
        ctx.shadowColor = glowHex || color;
        ctx.shadowBlur = 10;
        ctx.beginPath();
        ctx.moveTo(pts[i - 1].x, pts[i - 1].y);
        ctx.lineTo(pts[i].x, pts[i].y);
        ctx.stroke();
      }
      ctx.restore();
    }

    let __crackedEarthCache = null;
    function getCrackedEarthCanvas() {
      if (__crackedEarthCache) return __crackedEarthCache;
      const S = 512;
      const c = document.createElement("canvas");
      c.width = S; c.height = S;
      const g = c.getContext("2d");
      const img = g.createImageData(S, S);
      const data = img.data;
      // Deterministic tileable cellular Voronoi sites on a 7x7 jittered grid
      const N = 7;
      const pts = [];
      for (let gy = 0; gy < N; gy++) {
        for (let gx = 0; gx < N; gx++) {
          const h1 = Math.sin((gx * 127.1 + gy * 311.7) * 1.13) * 43758.5453;
          const h2 = Math.sin((gx * 269.5 + gy * 183.3) * 1.37) * 43758.5453;
          const jx = h1 - Math.floor(h1);
          const jy = h2 - Math.floor(h2);
          pts.push({
            x: (gx + 0.18 + jx * 0.64) / N,
            y: (gy + 0.18 + jy * 0.64) / N,
            shade: ((gx * 19 + gy * 37) % 11) / 11,
          });
        }
      }
      for (let py = 0; py < S; py++) {
        const ny = py / S;
        const gy0 = Math.floor(ny * N);
        for (let px = 0; px < S; px++) {
          const nx = px / S;
          const gx0 = Math.floor(nx * N);
          let d1 = 99, d2 = 99, cellShade = 0.5;
          for (let oy = -1; oy <= 1; oy++) {
            const wy = (gy0 + oy + N) % N;
            for (let ox = -1; ox <= 1; ox++) {
              const wx = (gx0 + ox + N) % N;
              const p = pts[wy * N + wx];
              let dx = p.x - nx;
              let dy = p.y - ny;
              if (dx > 0.5) dx -= 1; else if (dx < -0.5) dx += 1;
              if (dy > 0.5) dy -= 1; else if (dy < -0.5) dy += 1;
              const d = Math.hypot(dx, dy);
              if (d < d1) { d2 = d1; d1 = d; cellShade = p.shade; }
              else if (d < d2) { d2 = d; }
            }
          }
          const edge = d2 - d1;
          const noise = (Math.sin(px * 0.23 + py * 0.17) * Math.cos(px * 0.11 - py * 0.29)) * 7;
          let r = 156 + cellShade * 24 + noise;
          let gr = 136 + cellShade * 20 + noise * 0.9;
          let b = 104 + cellShade * 15 + noise * 0.7;
          if (edge < 0.011) {
            const k = clamp(edge / 0.011, 0, 1);
            r = lerp(42, r, k * k);
            gr = lerp(31, gr, k * k);
            b = lerp(20, b, k * k);
          } else if (edge < 0.020) {
            // Subtle sunlit lip along crack ridge
            r += 10; gr += 9; b += 6;
          }
          const idx = (py * S + px) * 4;
          data[idx] = clamp(Math.round(r), 0, 255);
          data[idx + 1] = clamp(Math.round(gr), 0, 255);
          data[idx + 2] = clamp(Math.round(b), 0, 255);
          data[idx + 3] = 255;
        }
      }
      g.putImageData(img, 0, 0);
      __crackedEarthCache = c;
      return c;
    }

    function drawProhibitionPin(x, y, radiusPx, iconKind, popScale, slashProgress, alpha, shape = "teardrop") {
      if (alpha <= 0.005 || popScale <= 0.01) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.scale(popScale, popScale);
      ctx.globalAlpha = alpha;
      const r = radiusPx;
      const isCircle = shape === "circle";
      const cy = isCircle ? 0 : -r * 1.24;

      if (!isCircle) {
        ctx.save();
        ctx.fillStyle = "rgba(0,0,0,0.38)";
        ctx.beginPath();
        ctx.ellipse(0, 3, r * 0.44, r * 0.16, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }

      // White disc or teardrop pin body
      ctx.save();
      ctx.shadowColor = "rgba(0,0,0,0.48)";
      ctx.shadowBlur = 16;
      ctx.shadowOffsetY = 5;
      ctx.fillStyle = "#FFFFFF";
      ctx.beginPath();
      if (isCircle) {
        ctx.arc(0, 0, r, 0, Math.PI * 2);
      } else {
        ctx.arc(0, cy, r, Math.PI * 0.22, Math.PI * 0.78, true);
        ctx.lineTo(0, 0);
      }
      ctx.closePath();
      ctx.fill();
      ctx.restore();

      // Inner domain icon
      ctx.save();
      ctx.translate(0, cy);
      if (iconKind === "water_drop") {
        const dg = ctx.createLinearGradient(-r * 0.3, -r * 0.55, r * 0.35, r * 0.55);
        dg.addColorStop(0, "#38BDF8");
        dg.addColorStop(1, "#0284C7");
        ctx.fillStyle = dg;
        ctx.beginPath();
        ctx.moveTo(0, -r * 0.56);
        ctx.bezierCurveTo(r * 0.46, -r * 0.04, r * 0.48, r * 0.50, 0, r * 0.54);
        ctx.bezierCurveTo(-r * 0.48, r * 0.50, -r * 0.46, -r * 0.04, 0, -r * 0.56);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,0.68)";
        ctx.beginPath();
        ctx.ellipse(-r * 0.14, r * 0.06, r * 0.08, r * 0.17, -0.35, 0, Math.PI * 2);
        ctx.fill();
      } else if (iconKind === "wheat_crop") {
        ctx.fillStyle = "#EAB308";
        ctx.strokeStyle = "#CA8A04";
        ctx.lineWidth = Math.max(1.5, r * 0.055);
        const stalks = [-0.28, -0.09, 0.09, 0.28];
        for (const sx of stalks) {
          const topY = -r * (0.50 - Math.abs(sx) * 0.35);
          ctx.beginPath();
          ctx.moveTo(sx * r * 0.7, r * 0.36);
          ctx.quadraticCurveTo(sx * r * 1.1, topY * 0.45, sx * r * 1.22, topY);
          ctx.stroke();
          for (let g = 0; g < 4; g++) {
            const gy = lerp(topY + r * 0.05, r * 0.12, g / 3.2);
            const gx = sx * r * (1.20 - g * 0.08);
            ctx.beginPath();
            ctx.ellipse(gx, gy, r * 0.075, r * 0.12, sx * 0.8, 0, Math.PI * 2);
            ctx.fill();
          }
        }
        ctx.fillStyle = "#5C3A21";
        ctx.beginPath();
        ctx.arc(0, r * 0.46, r * 0.52, Math.PI * 1.12, Math.PI * 1.88, false);
        ctx.quadraticCurveTo(0, r * 0.62, -r * 0.48, r * 0.26);
        ctx.closePath();
        ctx.fill();
      } else if (iconKind === "concrete_block") {
        // Isometric 3D cinder/concrete block
        ctx.strokeStyle = "#57534E";
        ctx.lineWidth = Math.max(1.4, r * 0.035);
        ctx.fillStyle = "#D6D3C4";
        ctx.beginPath();
        ctx.moveTo(-r * 0.48, -r * 0.08);
        ctx.lineTo(r * 0.06, -r * 0.44);
        ctx.lineTo(r * 0.50, -r * 0.16);
        ctx.lineTo(-r * 0.04, r * 0.20);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        ctx.fillStyle = "#A8A29E";
        ctx.beginPath();
        ctx.moveTo(-r * 0.48, -r * 0.08);
        ctx.lineTo(-r * 0.04, r * 0.20);
        ctx.lineTo(-r * 0.04, r * 0.48);
        ctx.lineTo(-r * 0.48, r * 0.20);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        ctx.fillStyle = "#78716C";
        ctx.beginPath();
        ctx.moveTo(-r * 0.04, r * 0.20);
        ctx.lineTo(r * 0.50, -r * 0.16);
        ctx.lineTo(r * 0.50, r * 0.12);
        ctx.lineTo(-r * 0.04, r * 0.48);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        // Hollow cores on top face
        ctx.fillStyle = "#57534E";
        ctx.beginPath();
        ctx.ellipse(-r * 0.14, -r * 0.06, r * 0.10, r * 0.06, -0.5, 0, Math.PI * 2);
        ctx.ellipse(r * 0.14, -r * 0.22, r * 0.10, r * 0.06, -0.5, 0, Math.PI * 2);
        ctx.fill();
      } else if (iconKind === "steel_beam") {
        // Isometric 3D structural steel I-beam
        ctx.strokeStyle = "#1E293B";
        ctx.lineWidth = Math.max(1.5, r * 0.035);
        // Back flange
        ctx.fillStyle = "#475569";
        ctx.beginPath();
        ctx.moveTo(-r * 0.52, r * 0.14);
        ctx.lineTo(r * 0.16, -r * 0.34);
        ctx.lineTo(r * 0.50, -r * 0.10);
        ctx.lineTo(-r * 0.18, r * 0.38);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        // Central web
        ctx.fillStyle = "#334155";
        ctx.beginPath();
        ctx.moveTo(-r * 0.36, -r * 0.04);
        ctx.lineTo(r * 0.32, -r * 0.48);
        ctx.lineTo(r * 0.32, -r * 0.14);
        ctx.lineTo(-r * 0.36, r * 0.30);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        // Top sunlit flange
        ctx.fillStyle = "#94A3B8";
        ctx.beginPath();
        ctx.moveTo(-r * 0.52, -r * 0.16);
        ctx.lineTo(r * 0.16, -r * 0.54);
        ctx.lineTo(r * 0.52, -r * 0.32);
        ctx.lineTo(-r * 0.16, r * 0.08);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
      } else if (iconKind === "construction_crane") {
        // Vibrant amber tower crane icon
        ctx.strokeStyle = "#1E293B";
        ctx.lineWidth = Math.max(1.8, r * 0.045);
        // Vertical mast
        ctx.fillStyle = "#F59E0B";
        ctx.fillRect(-r * 0.14, -r * 0.44, r * 0.22, r * 0.86);
        ctx.strokeRect(-r * 0.14, -r * 0.44, r * 0.22, r * 0.86);
        // Horizontal jib boom
        ctx.fillStyle = "#FBBF24";
        ctx.fillRect(-r * 0.48, -r * 0.36, r * 0.98, r * 0.16);
        ctx.strokeRect(-r * 0.48, -r * 0.36, r * 0.98, r * 0.16);
        // Counterweight block on left
        ctx.fillStyle = "#475569";
        ctx.fillRect(-r * 0.50, -r * 0.40, r * 0.22, r * 0.24);
        // Cable + hanging hook + cargo block
        ctx.strokeStyle = "#334155";
        ctx.beginPath();
        ctx.moveTo(r * 0.34, -r * 0.20);
        ctx.lineTo(r * 0.34, r * 0.12);
        ctx.stroke();
        ctx.fillStyle = "#0EA5E9";
        ctx.fillRect(r * 0.18, r * 0.12, r * 0.32, r * 0.22);
        ctx.strokeRect(r * 0.18, r * 0.12, r * 0.32, r * 0.22);
        // Base plinth
        ctx.fillStyle = "#334155";
        ctx.fillRect(-r * 0.32, r * 0.36, r * 0.58, r * 0.12);
      } else if (iconKind === "cargo_ship_icon") {
        // Side-view container vessel
        ctx.strokeStyle = "#0F172A";
        ctx.lineWidth = Math.max(1.6, r * 0.04);
        // Multicolored container blocks
        const blocks = [
          [-0.40, -0.22, 0.22, 0.18, "#E11D48"],
          [-0.16, -0.22, 0.22, 0.18, "#F59E0B"],
          [0.08, -0.22, 0.22, 0.18, "#0EA5E9"],
          [-0.28, -0.40, 0.22, 0.18, "#10B981"],
          [-0.04, -0.40, 0.22, 0.18, "#EA580C"],
        ];
        for (const [bx, by, bw, bh, bc] of blocks) {
          ctx.fillStyle = bc;
          ctx.fillRect(r * bx, r * by, r * bw, r * bh);
          ctx.strokeRect(r * bx, r * by, r * bw, r * bh);
        }
        // White bridge on left
        ctx.fillStyle = "#F8FAFC";
        ctx.fillRect(-r * 0.44, -r * 0.44, r * 0.14, r * 0.40);
        ctx.strokeRect(-r * 0.44, -r * 0.44, r * 0.14, r * 0.40);
        // Hull
        ctx.fillStyle = "#B91C1C";
        ctx.beginPath();
        ctx.moveTo(-r * 0.52, -r * 0.04);
        ctx.lineTo(r * 0.54, -r * 0.04);
        ctx.lineTo(r * 0.38, r * 0.32);
        ctx.lineTo(-r * 0.42, r * 0.32);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        // Waterline stripe
        ctx.fillStyle = "#0284C7";
        ctx.fillRect(-r * 0.54, r * 0.28, r * 1.08, r * 0.12);
      } else {
        ctx.fillStyle = "#3B82F6";
        ctx.beginPath();
        ctx.arc(0, 0, r * 0.45, 0, Math.PI * 2);
        ctx.fill();
      }

      // Stage 2: Animated crimson prohibition ring + diagonal slash
      if (slashProgress > 0.01) {
        const sp = clamp(slashProgress, 0, 1);
        const ringP = clamp(sp / 0.65, 0, 1);
        const barP = clamp((sp - 0.30) / 0.70, 0, 1);
        ctx.strokeStyle = "#DC2626";
        ctx.lineWidth = Math.max(4.5, r * 0.18);
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.arc(0, 0, r * 0.88, -Math.PI * 0.75, -Math.PI * 0.75 + Math.PI * 2 * ringP);
        ctx.stroke();
        if (barP > 0.01) {
          const d = r * 0.62;
          ctx.beginPath();
          ctx.moveTo(-d, -d);
          ctx.lineTo(lerp(-d, d, barP), lerp(-d, d, barP));
          ctx.stroke();
        }
      }
      ctx.restore();
      ctx.restore();
    }

    function drawTreeBelt(layer, t, tStart, tEnd, baseAlpha) {
      const spine = layer.coords || [];
      if (spine.length < 2 || baseAlpha <= 0.005) return;
      const revealS = layer.reveal_s ?? 0.9;
      const revealP = revealS > 0 ? easeOutCubic(seg(t, tStart, tStart + revealS)) : 1.0;
      const refZoom = layer.ref_zoom ?? 4.5;
      const zSc = clamp(Math.pow(2, (map.getZoom() - refZoom) * (layer.scale_coupling ?? 0.85)), 0.35, 3.2);
      const halfWidthDeg = layer.width_deg ?? 1.15;
      const density = layer.tree_count ?? 140;
      const mode = layer.reveal_mode || "corridor";

      // Optional glowing emerald ground halo beneath tree corridor
      if (layer.glow_hex !== null && (layer.glow_alpha ?? 0.75) > 0.01) {
        const glowHex = layer.glow_hex || "#22FF33";
        const glowA = (layer.glow_alpha ?? 0.78) * baseAlpha * clamp(revealP * 1.25, 0, 1);
        const pts = [];
        for (let i = 0; i <= 32; i++) {
          const u = (i / 32) * revealP;
          const pt = projectPointSafe(samplePolylineCoord(spine, u));
          if (pt) pts.push(pt);
        }
        if (pts.length >= 2) {
          ctx.save();
          ctx.lineCap = "round";
          ctx.lineJoin = "round";
          const baseW = (layer.glow_width_px ?? 68) * zSc;
          for (const [wm, a] of [[2.2, 0.22], [1.35, 0.42], [0.75, 0.68]]) {
            ctx.globalCompositeOperation = "screen";
            ctx.strokeStyle = rgbaStr(glowHex, clamp(glowA * a, 0, 1));
            ctx.lineWidth = baseW * wm;
            ctx.shadowColor = glowHex;
            ctx.shadowBlur = 24 * zSc;
            ctx.beginPath();
            ctx.moveTo(pts[0].x, pts[0].y);
            for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
            ctx.stroke();
          }
          ctx.restore();
        }
      }

      // Optional crisp diagonal planting hatch rows beneath trees (shelterbelt pattern)
      if (layer.hatch_rows) {
        ctx.save();
        ctx.strokeStyle = layer.hatch_color || "rgba(235, 244, 225, 0.48)";
        ctx.lineWidth = Math.max(1.2, 1.8 * zSc);
        const rows = layer.hatch_row_count ?? 42;
        for (let r = 0; r < rows; r++) {
          const u = r / Math.max(1, rows - 1);
          if (u > revealP) break;
          const c = samplePolylineCoord(spine, u);
          const pL = projectPointSafe([c[0] - halfWidthDeg * 1.15, c[1] + 0.28]);
          const pR = projectPointSafe([c[0] + halfWidthDeg * 1.15, c[1] - 0.28]);
          if (pL && pR) {
            ctx.beginPath();
            ctx.moveTo(pL.x, pL.y);
            ctx.lineTo(pR.x, pR.y);
            ctx.stroke();
          }
        }
        ctx.restore();
      }

      // Deterministic seeded volumetric 3D-shaded tree canopies
      const seedBase = layer.seed ?? 17;
      const trees = [];
      for (let i = 0; i < density; i++) {
        const h1 = Math.sin((i + 1) * 12.9898 + seedBase * 78.233) * 43758.5453;
        const h2 = Math.sin((i + 1) * 93.9898 + seedBase * 41.173) * 43758.5453;
        const h3 = Math.sin((i + 1) * 45.164 + seedBase * 19.713) * 43758.5453;
        const r1 = h1 - Math.floor(h1);
        const r2 = h2 - Math.floor(h2);
        const r3 = h3 - Math.floor(h3);
        const u = mode === "rows" ? Math.floor((i / density) * 14) / 14 + r1 * 0.045 : (i + r1 * 0.7) / density;
        const popAt = u * revealS * 0.85;
        const popP = easeOutBack(seg(t, tStart + popAt, tStart + popAt + 0.28));
        if (popP <= 0.02) continue;
        const c = samplePolylineCoord(spine, clamp(u, 0, 1));
        const latOff = (r2 - 0.5) * 2.0 * halfWidthDeg;
        const pt = projectPointSafe([c[0] + latOff, c[1] + (r3 - 0.5) * 0.35]);
        if (!pt) continue;
        trees.push({ x: pt.x, y: pt.y, rad: (13 + r3 * 13) * zSc * (layer.tree_scale ?? 1.0) * clamp(popP, 0, 1.12), r1, r2 });
      }
      // Sort north-to-south (top-to-bottom y) so southern canopies overlap northern ones naturally
      trees.sort((a, b) => a.y - b.y);

      ctx.save();
      ctx.globalAlpha = baseAlpha;
      for (const tr of trees) {
        const rad = tr.rad;
        // Ground shadow cast toward SE
        ctx.fillStyle = "rgba(8, 22, 10, 0.42)";
        ctx.beginPath();
        ctx.ellipse(tr.x + rad * 0.36, tr.y + rad * 0.44, rad * 0.92, rad * 0.55, 0.2, 0, Math.PI * 2);
        ctx.fill();
        // Short woody trunk stub
        ctx.fillStyle = "#3E2716";
        ctx.fillRect(tr.x - rad * 0.13, tr.y + rad * 0.1, rad * 0.26, rad * 0.45);
        // Dark foliage base cluster
        const g = ctx.createRadialGradient(tr.x - rad * 0.28, tr.y - rad * 0.32, rad * 0.12, tr.x, tr.y, rad);
        g.addColorStop(0, tr.r1 > 0.5 ? "#7EC838" : "#6BB82C");
        g.addColorStop(0.52, tr.r2 > 0.5 ? "#3E8022" : "#2E6A1A");
        g.addColorStop(1, "#183D10");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(tr.x, tr.y - rad * 0.15, rad * 0.88, 0, Math.PI * 2);
        ctx.arc(tr.x - rad * 0.42, tr.y + rad * 0.06, rad * 0.54, 0, Math.PI * 2);
        ctx.arc(tr.x + rad * 0.44, tr.y + rad * 0.04, rad * 0.52, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }

    function drawDustStormPlume(layer, t, tStart, tEnd, baseAlpha) {
      const refZoom = layer.ref_zoom ?? map.getZoom();
      const zSc = clamp(Math.pow(2, (map.getZoom() - refZoom) * (layer.scale_coupling ?? 0.85)), 0.35, 3.2);
      for (let pi = 0; pi < (layer.plumes || []).length; pi++) {
        const pl = layer.plumes[pi];
        const pStart = pl.start_s ?? tStart;
        const pEnd = pl.end_s ?? tEnd;
        if (t < pStart - 0.01 || t > pEnd + 0.01) continue;
        const pIn = (pl.fade_in_s ?? 0.65) > 0 ? easeOutCubic(seg(t, pStart, pStart + (pl.fade_in_s ?? 0.65))) : 1.0;
        const pOut = (pl.fade_out_s ?? 0.55) > 0 ? (1 - seg(t, pEnd - (pl.fade_out_s ?? 0.55), pEnd)) : 1.0;
        const pAlpha = baseAlpha * clamp(pIn * pOut * (pl.opacity ?? 0.92), 0, 1);
        if (pAlpha <= 0.005) continue;
        const u = easeInOutCubic(seg(t, pStart, pStart + (pl.move_duration_s ?? (pEnd - pStart))));
        const coord = samplePolylineCoord(pl.path || [pl.coord || [-100, 38]], u);
        const pt = projectPointSafe(coord);
        if (!pt) continue;
        const grow = lerp(pl.grow_from ?? 0.45, pl.grow_to ?? 1.45, u);
        const rad = (pl.radius_px ?? 180) * zSc * grow;
        const seed = pl.seed ?? (pi + 1);
        const puffs = pl.puff_count ?? 14;
        ctx.save();
        ctx.translate(pt.x, pt.y);
        ctx.globalAlpha = pAlpha;
        for (let k = 0; k < puffs; k++) {
          const ang = (k / puffs) * Math.PI * 2 + seed * 1.3 + (t - pStart) * 0.14;
          const dist = (0.12 + ((k * 37 + seed * 13) % 10) / 15) * rad;
          const pr = rad * (0.34 + ((k * 19 + seed * 7) % 10) / 26);
          const px = Math.cos(ang) * dist * 1.15;
          const py = Math.sin(ang) * dist * 0.92;
          const g = ctx.createRadialGradient(px - pr * 0.18, py - pr * 0.22, pr * 0.08, px, py, pr);
          g.addColorStop(0, k % 2 === 0 ? "rgba(134, 112, 88, 0.88)" : "rgba(104, 84, 62, 0.86)");
          g.addColorStop(0.55, "rgba(82, 64, 46, 0.68)");
          g.addColorStop(1, "rgba(62, 46, 32, 0)");
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(px, py, pr, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }
    }

    function drawParchmentSheet(layer, t, tStart, tEnd, baseAlpha) {
      const bbox = layer.bbox || [-126, 23, -65, 51];
      const [wLon, sLat, eLon, nLat] = bbox;
      const nw = projectPointSafe([wLon, nLat]);
      const ne = projectPointSafe([eLon, nLat]);
      const se = projectPointSafe([eLon, sLat]);
      const sw = projectPointSafe([wLon, sLat]);
      if (!nw || !ne || !se || !sw) return;

      const unfoldS = layer.unfold_s ?? 1.4;
      const unfoldU = easeInOutCubic(seg(t, tStart, tStart + unfoldS));
      if (unfoldU <= 0.005) return;

      const bilerp = (u, v) => {
        const tx = lerp(nw.x, ne.x, u), ty = lerp(nw.y, ne.y, u);
        const bx = lerp(sw.x, se.x, u), by = lerp(sw.y, se.y, u);
        return { x: lerp(tx, bx, v), y: lerp(ty, by, v) };
      };

      ctx.save();
      ctx.globalAlpha = baseAlpha;

      // Cast drop shadow under parchment sheet
      ctx.save();
      ctx.shadowColor = "rgba(2, 10, 16, 0.68)";
      ctx.shadowBlur = 32;
      ctx.shadowOffsetX = 10;
      ctx.shadowOffsetY = 18;
      ctx.fillStyle = "#8C7A60";
      ctx.beginPath();
      ctx.moveTo(nw.x, nw.y);
      ctx.lineTo(ne.x, ne.y);
      ctx.lineTo(se.x, se.y);
      ctx.lineTo(sw.x, sw.y);
      ctx.closePath();
      if (unfoldU < 0.995) {
        // Clip along advancing diagonal fold line from NW toward SE
        const foldP = lerp(0.15, 2.05, unfoldU);
        const c1 = bilerp(clamp(foldP, 0, 1), clamp(foldP - 1, 0, 1));
        const c2 = bilerp(clamp(foldP - 1, 0, 1), clamp(foldP, 0, 1));
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(nw.x, nw.y);
        if (foldP <= 1) {
          ctx.lineTo(bilerp(foldP, 0).x, bilerp(foldP, 0).y);
          ctx.lineTo(bilerp(0, foldP).x, bilerp(0, foldP).y);
        } else {
          ctx.lineTo(ne.x, ne.y);
          ctx.lineTo(c1.x, c1.y);
          ctx.lineTo(c2.x, c2.y);
          ctx.lineTo(sw.x, sw.y);
        }
        ctx.closePath();
        ctx.clip();
        ctx.beginPath();
        ctx.moveTo(nw.x, nw.y); ctx.lineTo(ne.x, ne.y); ctx.lineTo(se.x, se.y); ctx.lineTo(sw.x, sw.y);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
      } else {
        ctx.fill();
      }
      ctx.restore();

      // Clip interior of revealed parchment sheet
      ctx.save();
      ctx.beginPath();
      if (unfoldU < 0.995) {
        const foldP = lerp(0.15, 2.05, unfoldU);
        ctx.moveTo(nw.x, nw.y);
        if (foldP <= 1) {
          ctx.lineTo(bilerp(foldP, 0).x, bilerp(foldP, 0).y);
          ctx.lineTo(bilerp(0, foldP).x, bilerp(0, foldP).y);
        } else {
          const c1 = bilerp(1, foldP - 1);
          const c2 = bilerp(foldP - 1, 1);
          ctx.lineTo(ne.x, ne.y); ctx.lineTo(c1.x, c1.y); ctx.lineTo(c2.x, c2.y); ctx.lineTo(sw.x, sw.y);
        }
      } else {
        ctx.moveTo(nw.x, nw.y); ctx.lineTo(ne.x, ne.y); ctx.lineTo(se.x, se.y); ctx.lineTo(sw.x, sw.y);
      }
      ctx.closePath();
      ctx.clip();

      // Aged sepia parchment gradient + subtle slate ocean backing
      const grad = ctx.createLinearGradient(nw.x, nw.y, se.x, se.y);
      grad.addColorStop(0, "#746B5E");
      grad.addColorStop(0.5, "#696459");
      grad.addColorStop(1, "#55544C");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, W, H);

      // Country sepia landmass silhouette inside parchment
      const countryGeom = resolveGeom(layer.country_geom_ref);
      if (countryGeom) {
        ctx.save();
        ctx.fillStyle = "#A28E70";
        ctx.strokeStyle = "rgba(44, 34, 22, 0.55)";
        ctx.lineWidth = 2.0;
        ctx.beginPath();
        traceGeom(ctx, countryGeom);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
      }

      // Fine drafting grid lines in parchment plane
      ctx.strokeStyle = "rgba(235, 224, 200, 0.16)";
      ctx.lineWidth = 1.0;
      for (let i = 1; i < 12; i++) {
        const f = i / 12;
        const a = bilerp(f, 0), b = bilerp(f, 1);
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        const c = bilerp(0, f), d = bilerp(1, f);
        ctx.beginPath(); ctx.moveTo(c.x, c.y); ctx.lineTo(d.x, d.y); ctx.stroke();
      }

      // Crisp double drafting border around sheet perimeter
      ctx.strokeStyle = "rgba(232, 220, 196, 0.42)";
      ctx.lineWidth = 3.0;
      ctx.beginPath();
      ctx.moveTo(nw.x, nw.y); ctx.lineTo(ne.x, ne.y); ctx.lineTo(se.x, se.y); ctx.lineTo(sw.x, sw.y);
      ctx.closePath();
      ctx.stroke();

      // Optional green shelterbelt corridor painted directly onto the parchment map
      if (Array.isArray(layer.strip_coords) && layer.strip_coords.length >= 2 && t >= (layer.strip_start_s ?? tStart + 1.0)) {
        const sp = easeOutCubic(seg(t, layer.strip_start_s ?? tStart + 1.0, (layer.strip_start_s ?? tStart + 1.0) + 0.85));
        const sPts = [];
        for (let i = 0; i <= 24; i++) {
          const pt = projectPointSafe(samplePolylineCoord(layer.strip_coords, (i / 24) * sp));
          if (pt) sPts.push(pt);
        }
        if (sPts.length >= 2) {
          const zSc = clamp(Math.pow(2, (map.getZoom() - 4.2) * 0.85), 0.45, 2.6);
          ctx.save();
          ctx.strokeStyle = layer.strip_color || "#3E8B18";
          ctx.lineWidth = (layer.strip_width_px ?? 46) * zSc;
          ctx.lineCap = "butt";
          ctx.lineJoin = "round";
          ctx.beginPath();
          ctx.moveTo(sPts[0].x, sPts[0].y);
          for (let i = 1; i < sPts.length; i++) ctx.lineTo(sPts[i].x, sPts[i].y);
          ctx.stroke();
          ctx.restore();
        }
      }

      // Vintage serif title & year anchored along the top edge of the parchment sheet
      if (layer.title && t >= (layer.title_start_s ?? tStart + 0.9)) {
        const tA = easeOutCubic(seg(t, layer.title_start_s ?? tStart + 0.9, (layer.title_start_s ?? tStart + 0.9) + 0.55));
        const topMid = bilerp(0.50, 0.085);
        const topAng = Math.atan2(ne.y - nw.y, ne.x - nw.x);
        const sheetW = Math.hypot(ne.x - nw.x, ne.y - nw.y);
        const titlePx = clamp(sheetW * 0.072, 34, 86);
        drawGlowingText(layer.title, topMid.x, topMid.y, titlePx, {
          fill: "#F8F4EA",
          family: "Lora",
          weight: 700,
          angle: topAng,
          alpha: tA * baseAlpha,
          strokeHex: "rgba(30, 22, 14, 0.65)",
          strokeWidth: 2.2,
        });
        if (layer.subtitle) {
          const subMid = bilerp(0.50, 0.145);
          drawGlowingText(layer.subtitle, subMid.x, subMid.y, titlePx * 0.68, {
            fill: "#EDE5D2",
            family: "Lora",
            weight: 600,
            angle: topAng,
            alpha: tA * baseAlpha * 0.95,
            strokeHex: "rgba(30, 22, 14, 0.65)",
            strokeWidth: 1.8,
          });
        }
      }
      ctx.restore();

      // Animated folded-back triangular paper underside while unfolding
      if (unfoldU > 0.02 && unfoldU < 0.985) {
        const foldP = lerp(0.15, 2.05, unfoldU);
        const a = foldP <= 1 ? bilerp(foldP, 0) : bilerp(1, foldP - 1);
        const b = foldP <= 1 ? bilerp(0, foldP) : bilerp(foldP - 1, 1);
        const tip = bilerp(clamp(foldP * 0.68, 0.1, 1.05), clamp(foldP * 0.68, 0.1, 1.05));
        ctx.save();
        ctx.shadowColor = "rgba(0,0,0,0.48)";
        ctx.shadowBlur = 24;
        const fg = ctx.createLinearGradient(a.x, a.y, tip.x, tip.y);
        fg.addColorStop(0, "#D4D2C7");
        fg.addColorStop(1, "#B8B5A8");
        ctx.fillStyle = fg;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.lineTo(tip.x, tip.y);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
      }
      ctx.restore();
    }

    function drawMapSprite(item, t, tStart, tEnd, baseAlpha, zSc) {
      const iStart = item.start_s ?? tStart;
      const iEnd = item.end_s ?? tEnd;
      if (t < iStart - 0.005 || t > iEnd + 0.005) return;
      const popP = easeOutBack(seg(t, iStart, iStart + (item.pop_s ?? 0.28)));
      const fadeOut = item.fade_out_s ? 1 - seg(t, iEnd - item.fade_out_s, iEnd) : 1;
      const alpha = baseAlpha * clamp(fadeOut, 0, 1);
      if (alpha <= 0.005 || popP <= 0.02) return;

      let coord = item.coord;
      let headingRad = ((item.angle_deg ?? 0) * Math.PI) / 180;
      let moveU = 0;
      if (Array.isArray(item.path) && item.path.length >= 2) {
        const dur = Math.max(0.1, item.move_duration_s ?? (iEnd - iStart));
        moveU = clamp(seg(t, iStart, iStart + dur), 0, 1);
        const easedU = item.easing === "linear" ? moveU : easeInOutCubic(moveU);
        coord = samplePolylineCoord(item.path, easedU);
        if (item.auto_heading !== false) {
          const p0 = projectPointSafe(samplePolylineCoord(item.path, Math.max(0, easedU - 0.02)));
          const p1 = projectPointSafe(samplePolylineCoord(item.path, Math.min(1, easedU + 0.02)));
          if (p0 && p1 && Math.hypot(p1.x - p0.x, p1.y - p0.y) > 0.5) {
            headingRad = Math.atan2(p1.y - p0.y, p1.x - p0.x);
          }
        }
      }
      const pt = projectPointSafe(coord);
      if (!pt) return;
      const x = pt.x + (item.dx || 0);
      const y = pt.y + (item.dy || 0);
      const sz = (item.size_px ?? 64) * zSc * clamp(popP, 0, 1.15);
      const kind = item.kind || "tractor";
      const rawImgUrl = item.svg_url || item.image_url || null;

      ctx.save();
      ctx.globalAlpha = alpha;
      if (rawImgUrl) {
        // Optional animated foaming water wake or dust trail behind moving external SVG/image sprite
        if (item.wake && Array.isArray(item.path) && item.path.length >= 2 && moveU > 0.01) {
          ctx.save();
          const wakeSteps = 9;
          for (let w = 1; w <= wakeSteps; w++) {
            const wu = clamp(moveU - w * 0.022, 0, 1);
            const wp = projectPointSafe(samplePolylineCoord(item.path, wu));
            if (!wp) continue;
            const frac = 1 - w / (wakeSteps + 1);
            const spread = sz * (0.14 + w * 0.055);
            const rFoam = sz * (0.09 + w * 0.035);
            ctx.fillStyle = "rgba(224, 247, 255, " + (0.42 * frac).toFixed(3) + ")";
            const nx = -Math.sin(headingRad), ny = Math.cos(headingRad);
            ctx.beginPath(); ctx.arc(wp.x + nx * spread, wp.y + ny * spread, rFoam, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(wp.x - nx * spread, wp.y - ny * spread, rFoam, 0, Math.PI * 2); ctx.fill();
          }
          ctx.restore();
        } else if (item.dust_trail && Array.isArray(item.path) && item.path.length >= 2 && moveU > 0.02) {
          for (let d = 1; d <= 5; d++) {
            const du = clamp(moveU - d * 0.045, 0, 1);
            const dp = projectPointSafe(samplePolylineCoord(item.path, du));
            if (!dp) continue;
            const dr = sz * (0.28 + d * 0.14);
            const dg = ctx.createRadialGradient(dp.x, dp.y, 1, dp.x, dp.y, dr);
            dg.addColorStop(0, "rgba(196, 174, 138, " + (0.48 / d).toFixed(3) + ")");
            dg.addColorStop(1, "rgba(196, 174, 138, 0)");
            ctx.fillStyle = dg;
            ctx.beginPath(); ctx.arc(dp.x, dp.y, dr, 0, Math.PI * 2); ctx.fill();
          }
        }
        const resolvedUrl = String(rawImgUrl).startsWith("http")
          ? String(rawImgUrl)
          : BASE_URL + "/" + String(rawImgUrl).replace(/^\\/+/, "");
        const img = window.__imgCache[resolvedUrl];
        if (img && img.naturalWidth > 0 && img.naturalHeight > 0) {
          const bob = item.bob_amp ? Math.sin((t - iStart) * (item.bob_freq ?? 3.2) + (item.phase || 0)) * sz * item.bob_amp : 0;
          ctx.translate(x, y + bob);
          if (headingRad) ctx.rotate(headingRad);
          if (item.shadow !== false) {
            ctx.shadowColor = "rgba(0,0,0,0.45)";
            ctx.shadowBlur = Math.max(8, sz * 0.14);
            ctx.shadowOffsetY = Math.max(3, sz * 0.05);
          }
          const aspect = img.naturalWidth / img.naturalHeight;
          const dw = aspect >= 1 ? sz : sz * aspect;
          const dh = aspect >= 1 ? sz / aspect : sz;
          ctx.drawImage(img, -dw * 0.5, -dh * 0.5, dw, dh);
          if (item.badge_text) {
            ctx.rotate(-headingRad);
            ctx.shadowBlur = 6;
            ctx.fillStyle = item.badge_color || "#F59E0B";
            ctx.beginPath();
            ctx.roundRect(-sz * 0.58, dh * 0.54, sz * 1.16, sz * 0.28, sz * 0.07);
            ctx.fill();
            ctx.fillStyle = "#0F172A";
            ctx.font = "800 " + Math.round(sz * 0.20) + "px 'Barlow Condensed', sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(item.badge_text, 0, dh * 0.54 + sz * 0.14);
          }
        }
        ctx.restore();
        return;
      }
      if (kind === "tractor") {
        // Trailing dust puffs behind moving tractor
        if (item.dust_trail !== false && moveU > 0.02) {
          for (let d = 1; d <= 5; d++) {
            const du = clamp(moveU - d * 0.045, 0, 1);
            const dp = projectPointSafe(samplePolylineCoord(item.path, du));
            if (!dp) continue;
            const dr = sz * (0.28 + d * 0.14);
            const dg = ctx.createRadialGradient(dp.x, dp.y, 1, dp.x, dp.y, dr);
            dg.addColorStop(0, "rgba(196, 174, 138, " + (0.48 / d).toFixed(3) + ")");
            dg.addColorStop(1, "rgba(196, 174, 138, 0)");
            ctx.fillStyle = dg;
            ctx.beginPath(); ctx.arc(dp.x, dp.y, dr, 0, Math.PI * 2); ctx.fill();
          }
        }
        ctx.translate(x, y);
        ctx.rotate(headingRad);
        const col = item.color || "#DC2626";
        // Ground shadow
        ctx.fillStyle = "rgba(0,0,0,0.35)";
        ctx.beginPath(); ctx.ellipse(0, sz * 0.08, sz * 0.54, sz * 0.34, 0, 0, Math.PI * 2); ctx.fill();
        // Rear big wheels & front small wheels
        ctx.fillStyle = "#1C1917";
        ctx.fillRect(-sz * 0.38, -sz * 0.36, sz * 0.30, sz * 0.14);
        ctx.fillRect(-sz * 0.38, sz * 0.22, sz * 0.30, sz * 0.14);
        ctx.fillRect(sz * 0.18, -sz * 0.28, sz * 0.20, sz * 0.11);
        ctx.fillRect(sz * 0.18, sz * 0.17, sz * 0.20, sz * 0.11);
        // Tractor body & hood
        ctx.fillStyle = col;
        ctx.strokeStyle = "#1C1917";
        ctx.lineWidth = Math.max(1.2, sz * 0.03);
        ctx.beginPath();
        ctx.roundRect(-sz * 0.42, -sz * 0.22, sz * 0.84, sz * 0.44, sz * 0.08);
        ctx.fill(); ctx.stroke();
        // Cab roof
        ctx.fillStyle = "#E7E5E4";
        ctx.fillRect(-sz * 0.30, -sz * 0.16, sz * 0.28, sz * 0.32);
      } else if (kind === "barn_farm") {
        ctx.translate(x, y);
        ctx.shadowColor = "rgba(0,0,0,0.45)";
        ctx.shadowBlur = 12;
        ctx.shadowOffsetY = 4;
        // White silo on right
        ctx.fillStyle = "#FFFFFF";
        ctx.strokeStyle = "#1E293B";
        ctx.lineWidth = Math.max(1.8, sz * 0.035);
        ctx.beginPath();
        ctx.roundRect(sz * 0.16, -sz * 0.52, sz * 0.24, sz * 0.64, [sz * 0.12, sz * 0.12, 0, 0]);
        ctx.fill(); ctx.stroke();
        // White gambrel-roof barn
        ctx.beginPath();
        ctx.moveTo(-sz * 0.44, sz * 0.12);
        ctx.lineTo(-sz * 0.44, -sz * 0.18);
        ctx.lineTo(-sz * 0.28, -sz * 0.42);
        ctx.lineTo(-sz * 0.04, -sz * 0.52);
        ctx.lineTo(sz * 0.20, -sz * 0.42);
        ctx.lineTo(sz * 0.32, -sz * 0.18);
        ctx.lineTo(sz * 0.32, sz * 0.12);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
        // Barn X door
        ctx.strokeStyle = "#334155";
        ctx.lineWidth = Math.max(1.4, sz * 0.028);
        ctx.strokeRect(-sz * 0.20, -sz * 0.12, sz * 0.28, sz * 0.24);
        ctx.beginPath();
        ctx.moveTo(-sz * 0.20, -sz * 0.12); ctx.lineTo(sz * 0.08, sz * 0.12);
        ctx.moveTo(sz * 0.08, -sz * 0.12); ctx.lineTo(-sz * 0.20, sz * 0.12);
        ctx.stroke();
        // Bright green FARMS ribbon tag below barn
        ctx.shadowBlur = 6;
        ctx.fillStyle = "#74A80C";
        ctx.beginPath();
        ctx.roundRect(-sz * 0.56, sz * 0.08, sz * 1.12, sz * 0.30, sz * 0.08);
        ctx.fill();
        ctx.fillStyle = "#FFFFFF";
        ctx.font = "800 " + Math.round(sz * 0.21) + "px 'Barlow Condensed', sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(item.badge_text || "FARMS", 0, sz * 0.235);
      } else if (kind === "human_lung" || kind === "human_migrate") {
        const col = item.color || (kind === "human_lung" ? "#C81E28" : "#F8FAFC");
        drawHumanFigure(x, y, sz, col, alpha);
        if (kind === "human_lung") {
          // Crisp white lungs emblem centered on torso
          ctx.translate(x, y - sz * 0.55);
          ctx.fillStyle = "#FFFFFF";
          ctx.beginPath();
          ctx.ellipse(-sz * 0.065, 0, sz * 0.055, sz * 0.095, 0.15, 0, Math.PI * 2);
          ctx.ellipse(sz * 0.065, 0, sz * 0.055, sz * 0.095, -0.15, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = "#FFFFFF";
          ctx.lineWidth = Math.max(1.2, sz * 0.022);
          ctx.beginPath();
          ctx.moveTo(0, -sz * 0.13); ctx.lineTo(0, -sz * 0.04);
          ctx.moveTo(0, -sz * 0.04); ctx.lineTo(-sz * 0.05, 0);
          ctx.moveTo(0, -sz * 0.04); ctx.lineTo(sz * 0.05, 0);
          ctx.stroke();
        }
      } else if (kind === "alert_exclamation") {
        const pulse = 1 + Math.sin((t - iStart) * 5.2) * 0.06;
        ctx.translate(x, y);
        // Crimson radial warning aura + pulsing ring
        const g = ctx.createRadialGradient(0, 0, sz * 0.2, 0, 0, sz * 2.1 * pulse);
        g.addColorStop(0, "rgba(239, 68, 68, 0.52)");
        g.addColorStop(0.65, "rgba(220, 38, 38, 0.22)");
        g.addColorStop(1, "rgba(220, 38, 38, 0)");
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(0, 0, sz * 2.1 * pulse, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = "rgba(248, 113, 113, 0.72)";
        ctx.lineWidth = Math.max(8, sz * 0.18);
        ctx.beginPath(); ctx.arc(0, 0, sz * 1.45 * pulse, 0, Math.PI * 2); ctx.stroke();
        // Bold white exclamation mark
        ctx.shadowColor = "rgba(0,0,0,0.45)";
        ctx.shadowBlur = 16;
        ctx.fillStyle = "#FFFFFF";
        ctx.beginPath();
        ctx.roundRect(-sz * 0.14, -sz * 0.62, sz * 0.28, sz * 0.84, sz * 0.06);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(0, sz * 0.44, sz * 0.15, 0, Math.PI * 2);
        ctx.fill();
      } else if (kind === "thumbs_up") {
        ctx.translate(x, y);
        // Expanding white confirmation ripple
        const ripU = clamp(seg(t, iStart, iStart + 0.9), 0, 1);
        if (ripU < 0.99) {
          ctx.strokeStyle = "rgba(255,255,255," + (0.68 * (1 - ripU)).toFixed(3) + ")";
          ctx.lineWidth = Math.max(2, 6 * (1 - ripU));
          ctx.beginPath(); ctx.arc(0, 0, sz * lerp(0.55, 1.55, easeOutCubic(ripU)), 0, Math.PI * 2); ctx.stroke();
        }
        ctx.rotate(-0.12);
        ctx.shadowColor = "rgba(0,0,0,0.45)";
        ctx.shadowBlur = 16;
        ctx.fillStyle = "#FFFFFF";
        // Cuff
        ctx.beginPath(); ctx.roundRect(-sz * 0.56, -sz * 0.08, sz * 0.24, sz * 0.50, sz * 0.06); ctx.fill();
        // Palm & fingers + thumb
        ctx.beginPath();
        ctx.moveTo(-sz * 0.26, -sz * 0.06);
        ctx.lineTo(-sz * 0.04, -sz * 0.52);
        ctx.quadraticCurveTo(sz * 0.12, -sz * 0.56, sz * 0.14, -sz * 0.36);
        ctx.lineTo(sz * 0.08, -sz * 0.12);
        ctx.lineTo(sz * 0.46, -sz * 0.12);
        ctx.quadraticCurveTo(sz * 0.58, -sz * 0.12, sz * 0.54, sz * 0.04);
        ctx.lineTo(sz * 0.46, sz * 0.34);
        ctx.quadraticCurveTo(sz * 0.42, sz * 0.44, sz * 0.28, sz * 0.44);
        ctx.lineTo(-sz * 0.26, sz * 0.44);
        ctx.closePath();
        ctx.fill();
      } else if (kind === "pointer_arrow") {
        ctx.translate(x, y);
        ctx.rotate(headingRad);
        const bob = Math.sin((t - iStart) * 6.0) * sz * 0.08;
        ctx.translate(bob, 0);
        ctx.shadowColor = "rgba(0,0,0,0.52)";
        ctx.shadowBlur = 12;
        ctx.fillStyle = item.color || "#FFFFFF";
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(-sz * 0.48, -sz * 0.34);
        ctx.lineTo(-sz * 0.40, -sz * 0.13);
        ctx.lineTo(-sz * 1.05, -sz * 0.13);
        ctx.lineTo(-sz * 1.05, sz * 0.13);
        ctx.lineTo(-sz * 0.40, sz * 0.13);
        ctx.lineTo(-sz * 0.48, sz * 0.34);
        ctx.closePath();
        ctx.fill();
      } else if (kind === "reaction_badge") {
        ctx.translate(x, y);
        ctx.shadowColor = "rgba(0,0,0,0.45)";
        ctx.shadowBlur = 14;
        const r = sz * 0.5;
        const g = ctx.createRadialGradient(-r * 0.25, -r * 0.25, r * 0.1, 0, 0, r);
        g.addColorStop(0, "#FDE047");
        g.addColorStop(0.75, "#EAB308");
        g.addColorStop(1, "#B45309");
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#451A03";
        ctx.strokeStyle = "#451A03";
        ctx.lineWidth = Math.max(2, r * 0.11);
        ctx.lineCap = "round";
        // Eyes
        ctx.beginPath(); ctx.arc(-r * 0.32, -r * 0.14, r * 0.10, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(r * 0.32, -r * 0.14, r * 0.10, 0, Math.PI * 2); ctx.fill();
        // Mouth by mood
        const mood = item.mood || "surprised";
        ctx.beginPath();
        if (mood === "skeptic") {
          ctx.moveTo(-r * 0.30, r * 0.28); ctx.lineTo(r * 0.30, r * 0.22); ctx.stroke();
        } else if (mood === "worried") {
          ctx.arc(0, r * 0.48, r * 0.28, Math.PI * 1.18, Math.PI * 1.82); ctx.stroke();
        } else {
          ctx.arc(0, r * 0.28, r * 0.16, 0, Math.PI * 2); ctx.fill();
        }
      } else if (kind === "cargo_ship") {
        // Animated V-shaped white foaming wake trailing behind moving ship
        if (item.wake !== false && Array.isArray(item.path) && item.path.length >= 2 && moveU > 0.01) {
          ctx.save();
          const wakeSteps = 9;
          for (let w = 1; w <= wakeSteps; w++) {
            const wu = clamp(moveU - w * 0.022, 0, 1);
            const wp = projectPointSafe(samplePolylineCoord(item.path, wu));
            if (!wp) continue;
            const frac = 1 - w / (wakeSteps + 1);
            const spread = sz * (0.14 + w * 0.055);
            const rFoam = sz * (0.09 + w * 0.035);
            ctx.fillStyle = "rgba(224, 247, 255, " + (0.42 * frac).toFixed(3) + ")";
            const nx = -Math.sin(headingRad), ny = Math.cos(headingRad);
            ctx.beginPath(); ctx.arc(wp.x + nx * spread, wp.y + ny * spread, rFoam, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(wp.x - nx * spread, wp.y - ny * spread, rFoam, 0, Math.PI * 2); ctx.fill();
          }
          ctx.restore();
        }
        ctx.translate(x, y);
        ctx.rotate(headingRad);
        const hullCol = item.color || "#B91C1C";
        const deckCol = item.deck_color || "#1E293B";
        // Soft water shadow
        ctx.fillStyle = "rgba(2, 16, 28, 0.42)";
        ctx.beginPath();
        ctx.ellipse(-sz * 0.04, sz * 0.06, sz * 0.62, sz * 0.24, 0, 0, Math.PI * 2);
        ctx.fill();
        // Sleek pointed ship hull
        ctx.fillStyle = hullCol;
        ctx.strokeStyle = "#F8FAFC";
        ctx.lineWidth = Math.max(1.4, sz * 0.026);
        ctx.beginPath();
        ctx.moveTo(sz * 0.62, 0);
        ctx.quadraticCurveTo(sz * 0.42, -sz * 0.21, sz * 0.18, -sz * 0.21);
        ctx.lineTo(-sz * 0.50, -sz * 0.20);
        ctx.quadraticCurveTo(-sz * 0.58, -sz * 0.16, -sz * 0.58, 0);
        ctx.quadraticCurveTo(-sz * 0.58, sz * 0.16, -sz * 0.50, sz * 0.20);
        ctx.lineTo(sz * 0.18, sz * 0.21);
        ctx.quadraticCurveTo(sz * 0.42, sz * 0.21, sz * 0.62, 0);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        // Inner dark steel deck
        ctx.fillStyle = deckCol;
        ctx.beginPath();
        ctx.roundRect(-sz * 0.46, -sz * 0.145, sz * 0.78, sz * 0.29, sz * 0.04);
        ctx.fill();
        // Vibrant multicolored container blocks in 3x2 grid
        const cPalette = item.containers || ["#F59E0B", "#0EA5E9", "#10B981", "#EF4444", "#F97316", "#38BDF8"];
        const cols = 3, rows = 2;
        const cw = sz * 0.18, ch = sz * 0.105, gapX = sz * 0.03, gapY = sz * 0.025;
        for (let ci = 0; ci < cols; ci++) {
          for (let ri = 0; ri < rows; ri++) {
            const cx0 = -sz * 0.22 + ci * (cw + gapX);
            const cy0 = -ch - gapY * 0.5 + ri * (ch + gapY);
            ctx.fillStyle = cPalette[(ci * 2 + ri) % cPalette.length];
            ctx.fillRect(cx0, cy0, cw, ch);
            ctx.strokeStyle = "rgba(15, 23, 42, 0.55)";
            ctx.lineWidth = Math.max(0.8, sz * 0.012);
            ctx.strokeRect(cx0, cy0, cw, ch);
          }
        }
        // Crisp white rear bridge superstructure
        ctx.fillStyle = "#F8FAFC";
        ctx.fillRect(-sz * 0.44, -sz * 0.13, sz * 0.14, sz * 0.26);
        ctx.fillStyle = "#0F172A";
        ctx.fillRect(-sz * 0.36, -sz * 0.10, sz * 0.04, sz * 0.20);
      } else if (kind === "port_crane") {
        ctx.translate(x, y);
        ctx.shadowColor = "rgba(0,0,0,0.48)";
        ctx.shadowBlur = 14;
        ctx.shadowOffsetY = 4;
        const craneCol = item.color || "#E11D48";
        // Concrete pier plinth
        ctx.fillStyle = "#CBD5E1";
        ctx.beginPath(); ctx.roundRect(-sz * 0.52, sz * 0.24, sz * 1.04, sz * 0.16, sz * 0.04); ctx.fill();
        // Stacked colorful containers on pier
        const stacks = [
          [-0.44, 0.06, 0.22, 0.18, "#F59E0B"],
          [-0.20, 0.06, 0.22, 0.18, "#0EA5E9"],
          [-0.32, -0.10, 0.22, 0.16, "#10B981"],
        ];
        for (const [bx, by, bw, bh, bc] of stacks) {
          ctx.fillStyle = bc;
          ctx.fillRect(sz * bx, sz * by, sz * bw, sz * bh);
          ctx.strokeStyle = "#0F172A"; ctx.lineWidth = Math.max(1.1, sz * 0.02);
          ctx.strokeRect(sz * bx, sz * by, sz * bw, sz * bh);
        }
        // A-frame red gantry crane legs + horizontal boom
        ctx.strokeStyle = craneCol;
        ctx.lineWidth = Math.max(3.0, sz * 0.075);
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(sz * 0.02, sz * 0.24); ctx.lineTo(sz * 0.18, -sz * 0.42);
        ctx.moveTo(sz * 0.34, sz * 0.24); ctx.lineTo(sz * 0.18, -sz * 0.42);
        ctx.moveTo(-sz * 0.36, -sz * 0.26); ctx.lineTo(sz * 0.56, -sz * 0.26);
        ctx.stroke();
        // Stay cables
        ctx.strokeStyle = "#F8FAFC";
        ctx.lineWidth = Math.max(1.4, sz * 0.026);
        ctx.beginPath();
        ctx.moveTo(sz * 0.18, -sz * 0.42); ctx.lineTo(sz * 0.52, -sz * 0.26);
        ctx.moveTo(sz * 0.18, -sz * 0.42); ctx.lineTo(-sz * 0.32, -sz * 0.26);
        ctx.stroke();
        // Animated hanging container trolley
        const sway = Math.sin((t - iStart) * 2.6) * sz * 0.08;
        ctx.strokeStyle = "#E2E8F0";
        ctx.beginPath();
        ctx.moveTo(sz * 0.40 + sway, -sz * 0.26); ctx.lineTo(sz * 0.40 + sway, -sz * 0.04);
        ctx.stroke();
        ctx.fillStyle = "#F59E0B";
        ctx.fillRect(sz * 0.29 + sway, -sz * 0.04, sz * 0.22, sz * 0.14);
        if (item.badge_text) {
          ctx.shadowBlur = 6;
          ctx.fillStyle = item.badge_color || "#F59E0B";
          ctx.beginPath();
          ctx.roundRect(-sz * 0.56, sz * 0.44, sz * 1.12, sz * 0.28, sz * 0.07);
          ctx.fill();
          ctx.fillStyle = "#0F172A";
          ctx.font = "800 " + Math.round(sz * 0.20) + "px 'Barlow Condensed', sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(item.badge_text, 0, sz * 0.58);
        }
      } else if (kind === "cargo_crate") {
        ctx.translate(x, y);
        const bob = Math.sin((t - iStart) * 3.4 + (item.phase || 0)) * sz * 0.04;
        ctx.translate(0, bob);
        ctx.shadowColor = "rgba(0,0,0,0.45)";
        ctx.shadowBlur = 10;
        ctx.shadowOffsetY = 3;
        const cCol = item.color || "#F59E0B";
        // Crisp isometric shipping container / commodity crate
        ctx.fillStyle = cCol;
        ctx.strokeStyle = "#1E293B";
        ctx.lineWidth = Math.max(1.6, sz * 0.035);
        ctx.beginPath();
        ctx.roundRect(-sz * 0.44, -sz * 0.32, sz * 0.88, sz * 0.64, sz * 0.06);
        ctx.fill(); ctx.stroke();
        // Corrugated vertical ribs
        ctx.strokeStyle = "rgba(15, 23, 42, 0.35)";
        ctx.lineWidth = Math.max(1.2, sz * 0.025);
        for (const rx of [-0.24, -0.08, 0.08, 0.24]) {
          ctx.beginPath(); ctx.moveTo(sz * rx, -sz * 0.24); ctx.lineTo(sz * rx, sz * 0.24); ctx.stroke();
        }
        // Top sunlit highlight edge
        ctx.fillStyle = "rgba(255,255,255,0.28)";
        ctx.fillRect(-sz * 0.40, -sz * 0.29, sz * 0.80, sz * 0.11);
      }
      ctx.restore();
    }

    function drawCrimsonX(x, y, size, alpha, opts = {}) {
      if (alpha <= 0.005 || size <= 1) return;
      const s1 = opts.stroke1 != null ? clamp(opts.stroke1, 0, 1) : 1;
      const s2 = opts.stroke2 != null ? clamp(opts.stroke2, 0, 1) : 1;
      const impact = opts.impactPulse != null ? clamp(opts.impactPulse, 0, 1) : 0;
      const showShockwave = opts.shockwave !== false;
      const strokeHex = opts.strokeHex || "#DC2626";
      const glowHex = opts.glowHex || "#EF4444";
      const coreHex = opts.coreHex || "#FFFFFF";
      const angleRad = ((Number(opts.strikeAngleDeg) || 0) * Math.PI) / 180;
      if (s1 <= 0.001 && s2 <= 0.001) return;

      ctx.save();
      ctx.translate(x, y);
      if (angleRad !== 0) ctx.rotate(angleRad);
      ctx.globalAlpha = alpha;

      // Ambient crimson impact bloom behind the crossing point
      const bloomScale = 1.0 + impact * 0.45;
      const g = ctx.createRadialGradient(0, 0, size * 0.08, 0, 0, size * 2.1 * bloomScale);
      g.addColorStop(0, rgbaStr(glowHex, 0.72 + impact * 0.25));
      g.addColorStop(0.45, rgbaStr(strokeHex, 0.34 + impact * 0.16));
      g.addColorStop(1, rgbaStr(strokeHex, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(0, 0, size * 2.1 * bloomScale, 0, Math.PI * 2);
      ctx.fill();

      // Expanding diagonal-intersection shockwave ring on second slash impact
      if (showShockwave && impact > 0.01) {
        const ringR = size * (0.45 + (1 - impact) * 1.65);
        ctx.save();
        ctx.strokeStyle = rgbaStr(glowHex, impact * 0.9);
        ctx.lineWidth = Math.max(2.5, size * 0.085 * impact);
        ctx.beginPath();
        ctx.arc(0, 0, ringR, 0, Math.PI * 2);
        ctx.stroke();
        ctx.strokeStyle = rgbaStr(coreHex, impact * 0.75);
        ctx.lineWidth = Math.max(1.5, size * 0.032 * impact);
        ctx.beginPath();
        ctx.arc(0, 0, ringR * 0.88, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }

      const half = size * 0.52;
      const drawSlash = (x0, y0, x1, y1, prog) => {
        if (prog <= 0.002) return;
        const ex = lerp(x0, x1, prog);
        const ey = lerp(y0, y1, prog);
        ctx.lineCap = "round";
        for (const [col, w, a, blur] of [
          [glowHex, size * 0.36, 0.42, size * 0.28],
          [strokeHex, size * 0.24, 0.94, size * 0.12],
          [coreHex, size * 0.11, 1.0, 0],
        ]) {
          ctx.save();
          ctx.strokeStyle = col;
          ctx.lineWidth = w;
          ctx.globalAlpha = alpha * a;
          if (blur > 0) {
            ctx.shadowColor = glowHex;
            ctx.shadowBlur = blur;
          }
          ctx.beginPath();
          ctx.moveTo(x0, y0);
          ctx.lineTo(ex, ey);
          ctx.stroke();
          ctx.restore();
        }
        // Leading slash spark head while stroke is actively carving
        if (prog > 0.02 && prog < 0.98) {
          ctx.save();
          const sg = ctx.createRadialGradient(ex, ey, 1, ex, ey, size * 0.34);
          sg.addColorStop(0, coreHex);
          sg.addColorStop(0.45, rgbaStr("#FDE047", 0.85));
          sg.addColorStop(1, rgbaStr(glowHex, 0));
          ctx.fillStyle = sg;
          ctx.beginPath();
          ctx.arc(ex, ey, size * 0.34, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }
      };

      // Stroke 1: top-left -> bottom-right; Stroke 2: top-right -> bottom-left
      drawSlash(-half, -half, half, half, s1);
      drawSlash(half, -half, -half, half, s2);
      ctx.restore();
    }

    function drawSkull(x, y, r, alpha, { rotRad = 0, pitchScale = 1.0 } = {}) {
      if (alpha <= 0.005 || r <= 2) return;
      ctx.save();
      ctx.translate(x, y);
      if (pitchScale < 0.999) ctx.scale(1, Math.max(0.45, pitchScale));
      if (rotRad) ctx.rotate(rotRad);
      ctx.globalAlpha = alpha;
      // Warm neon crimson outer bloom fused with crimson territory polygon
      ctx.shadowColor = "#FF2E4C";
      ctx.shadowBlur = Math.max(8, r * 0.42);
      ctx.strokeStyle = "#FFD6DC";
      ctx.lineWidth = r * 0.22;
      ctx.lineCap = "round";
      const bx = r * 0.95, by = r * 0.72, yOff = r * 0.26;
      for (const [x1, y1, x2, y2] of [[-bx, yOff - by * 0.4, bx, yOff + by * 0.65], [bx, yOff - by * 0.4, -bx, yOff + by * 0.65]]) {
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        ctx.fillStyle = "#FFD6DC";
        for (const [kx, ky] of [[x1, y1], [x2, y2]]) {
          ctx.beginPath(); ctx.arc(kx, ky - r * 0.08, r * 0.12, 0, Math.PI * 2); ctx.arc(kx, ky + r * 0.08, r * 0.12, 0, Math.PI * 2); ctx.fill();
        }
      }
      ctx.fillStyle = "#FFE4E6";
      ctx.beginPath();
      ctx.arc(0, -r * 0.22, r * 0.66, Math.PI * 0.85, Math.PI * 2.15);
      ctx.lineTo(r * 0.45, r * 0.22);
      ctx.quadraticCurveTo(r * 0.42, r * 0.50, r * 0.28, r * 0.52);
      ctx.lineTo(-r * 0.28, r * 0.52);
      ctx.quadraticCurveTo(-r * 0.42, r * 0.50, -r * 0.45, r * 0.22);
      ctx.closePath();
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.fillStyle = "#7F1D1D";
      ctx.beginPath();
      ctx.ellipse(-r * 0.24, -r * 0.12, r * 0.18, r * 0.16, -0.15, 0, Math.PI * 2);
      ctx.ellipse(r * 0.24, -r * 0.12, r * 0.18, r * 0.16, 0.15, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath(); ctx.moveTo(0, r * 0.02); ctx.lineTo(-r * 0.09, r * 0.20); ctx.lineTo(r * 0.09, r * 0.20); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = "#7F1D1D"; ctx.lineWidth = Math.max(1.5, r * 0.055);
      for (const tx of [-0.14, 0, 0.14]) { ctx.beginPath(); ctx.moveTo(r * tx, r * 0.34); ctx.lineTo(r * tx, r * 0.52); ctx.stroke(); }
      ctx.restore();
    }

    function drawTeardropPin(x, y, r, kind, alpha, badgeColor = "#DC2626") {
      if (alpha <= 0.005 || r <= 1) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      // Anchor at bottom tip (0,0), center of circular head at (0, -r * 1.35)
      const cy = -r * 1.25;
      ctx.shadowColor = "rgba(0,0,0,0.45)";
      ctx.shadowBlur = 18;
      ctx.fillStyle = "#FFFFFF";
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.bezierCurveTo(-r * 0.52, -r * 0.62, -r, -r * 0.88, -r, cy);
      ctx.arc(0, cy, r, Math.PI, 0, false);
      ctx.bezierCurveTo(r, -r * 0.88, r * 0.52, -r * 0.62, 0, 0);
      ctx.closePath();
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = badgeColor;
      ctx.lineWidth = Math.max(5, r * 0.12);
      ctx.stroke();

      ctx.translate(0, cy);
      ctx.fillStyle = badgeColor;
      ctx.strokeStyle = badgeColor;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      if (kind === "snake") {
        ctx.lineWidth = r * 0.18;
        ctx.beginPath();
        ctx.moveTo(-r * 0.42, r * 0.40);
        ctx.bezierCurveTo(-r * 0.55, 0, r * 0.55, r * 0.36, r * 0.36, -r * 0.05);
        ctx.bezierCurveTo(r * 0.24, -r * 0.44, -r * 0.40, -r * 0.26, -r * 0.10, -r * 0.46);
        ctx.stroke();
        ctx.beginPath(); ctx.arc(r * 0.06, -r * 0.48, r * 0.16, 0, Math.PI * 2); ctx.fill();
      } else if (kind === "jaguar") {
        ctx.beginPath(); ctx.arc(0, r * 0.06, r * 0.44, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(-r * 0.34, -r * 0.32, r * 0.16, 0, Math.PI * 2); ctx.arc(r * 0.34, -r * 0.32, r * 0.16, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#FFFFFF";
        ctx.beginPath(); ctx.ellipse(-r * 0.16, -r * 0.02, r * 0.08, r * 0.05, 0.2, 0, Math.PI * 2); ctx.ellipse(r * 0.16, -r * 0.02, r * 0.08, r * 0.05, -0.2, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.moveTo(0, r * 0.08); ctx.lineTo(-r * 0.09, r * 0.22); ctx.lineTo(r * 0.09, r * 0.22); ctx.closePath(); ctx.fill();
      } else if (kind === "mosquito") {
        ctx.lineWidth = r * 0.08;
        ctx.beginPath(); ctx.ellipse(0, 0, r * 0.12, r * 0.42, 0.35, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.ellipse(-r * 0.30, -r * 0.12, r * 0.30, r * 0.11, -0.35, 0, Math.PI * 2); ctx.ellipse(r * 0.30, -r * 0.12, r * 0.30, r * 0.11, 0.35, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath();
        ctx.moveTo(r * 0.18, -r * 0.34); ctx.lineTo(r * 0.48, -r * 0.56);
        ctx.moveTo(-r * 0.10, r * 0.18); ctx.lineTo(-r * 0.48, r * 0.44);
        ctx.moveTo(r * 0.10, r * 0.18); ctx.lineTo(r * 0.48, r * 0.46);
        ctx.stroke();
      } else {
        ctx.beginPath(); ctx.arc(0, r * 0.14, r * 0.26, 0, Math.PI * 2); ctx.arc(0, -r * 0.22, r * 0.17, 0, Math.PI * 2); ctx.fill();
        ctx.lineWidth = r * 0.07;
        for (const s of [-1, 1]) {
          for (const dy of [-0.28, -0.06, 0.16, 0.38]) {
            ctx.beginPath(); ctx.moveTo(s * r * 0.18, r * dy * 0.6); ctx.lineTo(s * r * 0.44, r * (dy - 0.14)); ctx.lineTo(s * r * 0.58, r * (dy + 0.12)); ctx.stroke();
          }
        }
      }
      ctx.restore();
    }

    function drawNoPoliceBadge(x, y, r, alpha) {
      if (alpha <= 0.005 || r <= 1) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      const g = ctx.createRadialGradient(0, 0, r * 0.72, 0, 0, r * 1.5);
      g.addColorStop(0, "rgba(220, 38, 38, 0.72)");
      g.addColorStop(1, "rgba(220, 38, 38, 0)");
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(0, 0, r * 1.5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#FFFFFF";
      ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = "#B91C1C";
      ctx.lineWidth = Math.max(4, r * 0.065);
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(-r * 0.42, -r * 0.44); ctx.lineTo(-r * 0.26, -r * 0.68); ctx.lineTo(0, -r * 0.76);
      ctx.lineTo(r * 0.26, -r * 0.68); ctx.lineTo(r * 0.42, -r * 0.44); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-r * 0.36, -r * 0.38); ctx.quadraticCurveTo(0, -r * 0.30, r * 0.36, -r * 0.38); ctx.stroke();
      ctx.beginPath(); ctx.arc(0, -r * 0.16, r * 0.24, 0, Math.PI); ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(-r * 0.56, r * 0.62); ctx.quadraticCurveTo(-r * 0.52, r * 0.16, -r * 0.18, r * 0.10);
      ctx.lineTo(0, r * 0.28); ctx.lineTo(r * 0.18, r * 0.10); ctx.quadraticCurveTo(r * 0.52, r * 0.16, r * 0.56, r * 0.62); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, r * 0.28); ctx.lineTo(0, r * 0.62); ctx.stroke();
      ctx.beginPath(); ctx.arc(r * 0.28, r * 0.40, r * 0.09, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = "#DC2626";
      ctx.lineWidth = Math.max(8, r * 0.15);
      ctx.beginPath(); ctx.arc(0, 0, r * 0.94, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-r * 0.66, -r * 0.66); ctx.lineTo(r * 0.66, r * 0.66); ctx.stroke();
      ctx.restore();
    }

    function drawDoubleArrow(p1, p2, labelText, progress, alpha) {
      if (alpha <= 0.005 || progress <= 0.01) return;
      const mx = (p1.x + p2.x) * 0.5, my = (p1.y + p2.y) * 0.5;
      const dx = p2.x - p1.x, dy = p2.y - p1.y;
      const len = Math.hypot(dx, dy);
      const ang = Math.atan2(dy, dx);
      const half = (len * 0.5) * clamp(progress, 0, 1);
      ctx.save();
      ctx.translate(mx, my);
      ctx.rotate(ang);
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = "#FFFFFF";
      ctx.fillStyle = "#FFFFFF";
      ctx.shadowColor = "rgba(0,0,0,0.88)";
      ctx.shadowBlur = 14;
      ctx.lineWidth = Math.max(5, len * 0.015);
      ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(-half + 14, 0); ctx.lineTo(half - 14, 0); ctx.stroke();
      const ah = Math.max(18, len * 0.048);
      for (const s of [-1, 1]) {
        ctx.beginPath();
        ctx.moveTo(s * half, 0);
        ctx.lineTo(s * (half - ah), -ah * 0.62);
        ctx.lineTo(s * (half - ah * 0.72), 0);
        ctx.lineTo(s * (half - ah), ah * 0.62);
        ctx.closePath();
        ctx.fill();
      }
      const fSize = Math.max(38, Math.min(130, len * 0.145));
      ctx.font = "800 " + Math.round(fSize) + "px 'Barlow Condensed', sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      const ly = -Math.max(16, len * 0.045);
      ctx.save();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = "rgba(3,22,31,0.84)";
      ctx.lineWidth = Math.max(3, fSize * 0.06);
      ctx.lineJoin = "round";
      ctx.strokeText(labelText, 0, ly);
      ctx.restore();
      ctx.fillText(labelText, 0, ly);
      ctx.restore();
    }

    function drawWeatherCloudsRain(cx, cy, scale, alpha, tLocal) {
      if (alpha <= 0.005) return;
      ctx.save();
      ctx.translate(cx, cy);
      ctx.scale(scale, scale);
      ctx.globalAlpha = alpha;

      // Ground shadow cast beneath cloud cluster onto map relief
      const sh = ctx.createRadialGradient(18, 42, 20, 18, 42, 230);
      sh.addColorStop(0, "rgba(2, 12, 16, 0.52)");
      sh.addColorStop(0.65, "rgba(2, 12, 16, 0.24)");
      sh.addColorStop(1, "rgba(2, 12, 16, 0)");
      ctx.fillStyle = sh;
      ctx.beginPath(); ctx.arc(18, 42, 230, 0, Math.PI * 2); ctx.fill();

      // Parallax diagonal rain streaks
      ctx.strokeStyle = "rgba(215, 244, 255, 0.58)";
      ctx.lineWidth = 2.6;
      ctx.lineCap = "round";
      for (let i = 0; i < 48; i++) {
        const rx = ((i * 73) % 360) - 180;
        const speed = 340 + (i % 5) * 48;
        const ry = ((tLocal * speed + i * 53) % 360) - 45;
        ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(rx - 15, ry + 38); ctx.stroke();
      }

      // Multi-puff shaded volumetric clouds
      const puffs = [
        [-102, -96, 72, 0.92], [-26, -128, 92, 0.97], [60, -108, 78, 0.93], [116, -68, 58, 0.88],
        [-118, 22, 76, 0.95], [-36, 2, 98, 0.99], [48, 16, 86, 0.96], [114, 42, 60, 0.89],
        [-58, 96, 66, 0.87], [26, 104, 62, 0.85],
      ];
      for (let idx = 0; idx < puffs.length; idx++) {
        const [px, py, pr, pa] = puffs[idx];
        const dx = Math.sin(tLocal * 1.3 + idx) * 9;
        const dy = Math.cos(tLocal * 1.0 + idx * 0.7) * 4.5;
        const g = ctx.createRadialGradient(px + dx - pr * 0.28, py + dy - pr * 0.32, pr * 0.1, px + dx, py + dy, pr);
        g.addColorStop(0, "rgba(255, 255, 255, " + pa + ")");
        g.addColorStop(0.62, "rgba(232, 240, 245, " + (pa * 0.92) + ")");
        g.addColorStop(1, "rgba(168, 188, 200, 0)");
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(px + dx, py + dy, pr, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
    }

    function drawJungleEmojiEnding(tLocal, gagAt = 1.12) {
      const canopyP = easeOutExpo(seg(tLocal, 0.0, 0.45));
      const emojiP = easeOutBack(seg(tLocal, 0.18, 0.55));
      const gagP = easeOutExpo(seg(tLocal, gagAt, gagAt + 0.32));

      ctx.save();
      const drawCanopyCluster = (baseY, dirSign, colors) => {
        ctx.save();
        ctx.translate(0, baseY);
        for (let layer = 0; layer < colors.length; layer++) {
          for (let i = -2; i <= 20; i++) {
            const cx = i * 58 + (layer % 2) * 29;
            const cy = dirSign * (32 + layer * 72 + Math.sin(i * 2.5 + layer * 1.7) * 34);
            const rx = 56 + ((i * 19 + layer * 13) % 34);
            const ry = 38 + ((i * 11 + layer * 7) % 24);
            const g = ctx.createRadialGradient(cx - rx * 0.2, cy - ry * 0.3, 6, cx, cy, rx);
            g.addColorStop(0, colors[layer][0]);
            g.addColorStop(1, colors[layer][1]);
            ctx.fillStyle = g;
            ctx.beginPath();
            ctx.ellipse(cx, cy, rx, ry, ((i + layer) % 5 - 2) * 0.28, 0, Math.PI * 2);
            ctx.fill();
          }
        }
        ctx.restore();
      };

      const topPal = [["#143A18", "#0A200D"], ["#1F5621", "#103213"], ["#2F7428", "#17421A"], ["#439432", "#20591F"], ["#5CB33F", "#2D7127"]];
      drawCanopyCluster(lerp(-440, 0, canopyP), 1, topPal);

      // Bottom trunks + canopy
      const botOff = lerp(540, 0, canopyP);
      ctx.save();
      ctx.translate(0, botOff);
      ctx.fillStyle = "#3E2616";
      for (const [tx, tw] of [[85, 42], [290, 34], [540, 48], [810, 36], [985, 44]]) {
        ctx.fillRect(tx - tw / 2, H - 360, tw, 380);
      }
      ctx.restore();
      drawCanopyCluster(H + botOff - 10, -1, topPal);

      if (emojiP > 0.01) {
        const ex = W * 0.5, ey = H * 0.43;
        const r = 138 * clamp(emojiP, 0, 1.15);
        ctx.save();
        ctx.translate(ex, ey);
        ctx.shadowColor = "rgba(0,0,0,0.58)";
        ctx.shadowBlur = 32;
        const eg = ctx.createRadialGradient(-r * 0.28, -r * 0.28, r * 0.08, 0, 0, r);
        eg.addColorStop(0, "#FFF078");
        eg.addColorStop(0.7, "#FACC15");
        eg.addColorStop(1, "#D97706");
        ctx.fillStyle = eg;
        ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
        ctx.shadowBlur = 0;
        ctx.strokeStyle = "#92400E"; ctx.lineWidth = 4; ctx.stroke();

        for (const sx of [-1, 1]) {
          ctx.fillStyle = "#FFFFFF";
          ctx.beginPath(); ctx.arc(sx * r * 0.34, -r * 0.16, r * 0.24, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = "#78350F"; ctx.lineWidth = 3; ctx.stroke();
          ctx.fillStyle = "#111827";
          ctx.beginPath(); ctx.arc(sx * r * 0.30, -r * 0.14, r * 0.095, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = "#78350F"; ctx.lineWidth = 7; ctx.lineCap = "round";
          ctx.beginPath(); ctx.moveTo(sx * r * 0.14, -r * 0.48); ctx.lineTo(sx * r * 0.52, -r * 0.38); ctx.stroke();
        }
        ctx.strokeStyle = "#78350F"; ctx.lineWidth = 8; ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(-r * 0.38, r * 0.32);
        ctx.quadraticCurveTo(-r * 0.20, r * 0.18, 0, r * 0.32);
        ctx.quadraticCurveTo(r * 0.20, r * 0.44, r * 0.38, r * 0.30);
        ctx.stroke();

        if (gagP > 0.01) {
          const gx = lerp(380, 18, gagP);
          ctx.save();
          ctx.translate(gx, r * 0.28);
          ctx.fillStyle = "#0F1115";
          ctx.shadowColor = "rgba(0,0,0,0.68)";
          ctx.shadowBlur = 18;
          ctx.beginPath(); ctx.roundRect(-r * 0.64, -r * 0.26, r * 1.52, r * 0.54, r * 0.24); ctx.fill();
          ctx.strokeStyle = "#374151"; ctx.lineWidth = 3;
          for (const fy of [-0.11, 0.04, 0.18]) { ctx.beginPath(); ctx.moveTo(-r * 0.58, r * fy); ctx.lineTo(r * 0.18, r * fy); ctx.stroke(); }
          ctx.restore();
        }
        ctx.restore();
      }
      ctx.restore();
    }
`;
}
