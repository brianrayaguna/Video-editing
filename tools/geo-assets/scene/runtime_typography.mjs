export function buildTypographyRuntime() {
  return `
    function getMapPlaneMatrix(coord, refZoom = 5.0) {
      const [lng, lat] = coord;
      const p0 = map.project([lng, lat]);
      const curZoom = map.getZoom();
      if (!p0 || !Number.isFinite(p0.x) || !Number.isFinite(p0.y) || Math.abs(p0.x) > W * 16 || Math.abs(p0.y) > H * 16) {
        const s = Math.pow(2, curZoom - refZoom);
        const rot = (-map.getBearing() * Math.PI) / 180;
        const pitchCos = Math.max(0.25, Math.cos(((map.getPitch() || 0) * Math.PI) / 180));
        return {
          a: Math.cos(rot) * s,
          b: Math.sin(rot) * s,
          c: -Math.sin(rot) * s * pitchCos,
          d: Math.cos(rot) * s * pitchCos,
          e: Number.isFinite(p0?.x) ? p0.x : W * 0.5,
          f: Number.isFinite(p0?.y) ? p0.y : H * 0.5,
        };
      }
      const cosLat = Math.max(0.15, Math.cos((lat * Math.PI) / 180));
      const stepZoom = Math.max(refZoom, curZoom);
      const stepPx = 4;
      const dLng = (360 / (512 * Math.pow(2, stepZoom))) * stepPx;
      const dLat = dLng * cosLat;
      const relScale = Math.pow(2, stepZoom - refZoom);
      const pEast = map.project([lng + dLng, lat]);
      const pSouth = map.project([lng, lat - dLat]);
      let a = ((pEast.x - p0.x) / stepPx) * relScale;
      let b = ((pEast.y - p0.y) / stepPx) * relScale;
      let c = ((pSouth.x - p0.x) / stepPx) * relScale;
      let d = ((pSouth.y - p0.y) / stepPx) * relScale;
      const det = a * d - b * c;
      if (!Number.isFinite(det) || det <= 1e-6 || det > 1e8) {
        const mag = Math.hypot(a, b);
        const s = Number.isFinite(mag) && mag > 1e-4 ? mag : Math.pow(2, curZoom - refZoom);
        const rot = (-map.getBearing() * Math.PI) / 180;
        const pitchCos = Math.max(0.25, Math.cos(((map.getPitch() || 0) * Math.PI) / 180));
        a = Math.cos(rot) * s;
        b = Math.sin(rot) * s;
        c = -Math.sin(rot) * s * pitchCos;
        d = Math.cos(rot) * s * pitchCos;
      }
      return { a, b, c, d, e: p0.x, f: p0.y };
    }

    const CARTO_TYPO_PRESETS = Object.freeze({
      // Classic cartographic hierarchy (refined soft halos, zero heavy black outlines)
      country: { family: "Montserrat", weight: 800, fontStyle: "normal", letterSpacingEm: 0.10, fill: "#F4F1EA", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: true, shadowBlurMult: 0.22, shadowAlpha: 0.48, shadowOffsetYMult: 0.05 },
      region:  { family: "Inter", weight: 600, fontStyle: "normal", letterSpacingEm: 0.14, fill: "#D4E0E8", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: true, shadowBlurMult: 0.18, shadowAlpha: 0.45, shadowOffsetYMult: 0.04 },
      city:    { family: "Inter", weight: 700, fontStyle: "normal", letterSpacingEm: 0.01, fill: "#F4F1EA", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: false, shadowBlurMult: 0.20, shadowAlpha: 0.48, shadowOffsetYMult: 0.05 },
      water:   { family: "Lora", weight: 600, fontStyle: "italic", letterSpacingEm: 0.07, fill: "#B8E1FF", strokeHex: "rgba(3,22,31,0.55)", strokeMult: 0.025, glowStrength: "none", uppercase: false, shadowBlurMult: 0.18, shadowAlpha: 0.42, shadowOffsetYMult: 0.04 },
      coord:   { family: "IBM Plex Mono", weight: 700, fontStyle: "normal", letterSpacingEm: 0.05, fill: "#DCE8F5", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: true, tabularDigits: true, shadowBlurMult: 0.18, shadowAlpha: 0.46, shadowOffsetYMult: 0.04 },
      hero:    { family: "Montserrat", weight: 900, fontStyle: "normal", letterSpacingEm: -0.02, fill: "#F4F1EA", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: false, shadowBlurMult: 0.24, shadowAlpha: 0.48, shadowOffsetYMult: 0.06 },
      // Editorial documentary presets (zero neon glow, matte organic palette, soft directional shadow)
      editorial_title:       { family: "Montserrat", weight: 900, fontStyle: "normal", letterSpacingEm: -0.01, fill: "#F4F1EA", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: false, shadowBlurMult: 0.24, shadowAlpha: 0.48, shadowOffsetYMult: 0.06 },
      clean_region:          { family: "Montserrat", weight: 800, fontStyle: "normal", letterSpacingEm: 0.0,   fill: "#F4F1EA", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: false, shadowBlurMult: 0.22, shadowAlpha: 0.46, shadowOffsetYMult: 0.05 },
      era_marquee:           { family: "Montserrat", weight: 900, fontStyle: "normal", letterSpacingEm: -0.02, fill: "#EFECE4", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: false, shadowBlurMult: 0.20, shadowAlpha: 0.42, shadowOffsetYMult: 0.06 },
      integrated_stat:       { family: "Montserrat", weight: 900, fontStyle: "normal", letterSpacingEm: -0.01, fill: "#E5E1D6", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: false, tabularDigits: true, shadowBlurMult: 0.22, shadowAlpha: 0.44, shadowOffsetYMult: 0.06 },
      map_integrated_number: { family: "Montserrat", weight: 900, fontStyle: "normal", letterSpacingEm: -0.01, fill: "#95B05E", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: false, tabularDigits: true, shadowBlurMult: 0.16, shadowAlpha: 0.34, shadowOffsetYMult: 0.04 },
      dual_unit_stack:       { family: "Montserrat", weight: 800, fontStyle: "normal", letterSpacingEm: 0.0,   fill: "#F4F1EA", strokeHex: null, strokeMult: 0, glowStrength: "none", uppercase: false, dividerRule: true, shadowBlurMult: 0.20, shadowAlpha: 0.46, shadowOffsetYMult: 0.05 },
    });

    function inferFontFallback(family) {
      const f = String(family || "").toLowerCase();
      if (/garamond|lora|playfair|merriweather|baskerville|serif|cinzel/.test(f)) return "Georgia, serif";
      if (/mono|courier|code/.test(f)) return "monospace";
      return "sans-serif";
    }

    function resolveCanvasLetterSpacingPx(letterSpacing, fontPx) {
      if (!letterSpacing) return 0;
      if (typeof letterSpacing === "number") return Number.isFinite(letterSpacing) ? letterSpacing : 0;
      const s = String(letterSpacing).trim();
      if (s.endsWith("em")) {
        const val = parseFloat(s);
        return Number.isFinite(val) ? val * fontPx : 0;
      }
      const px = parseFloat(s);
      return Number.isFinite(px) ? px : 0;
    }

    function applyCanvasLetterSpacing(letterSpacing, fontPx) {
      if (typeof ctx.letterSpacing !== "string") return;
      const px = resolveCanvasLetterSpacingPx(letterSpacing, fontPx);
      ctx.letterSpacing = px ? px.toFixed(2) + "px" : "0px";
    }

    // Draw a single centered line with optional fixed-width tabular digit slots (eliminates
    // horizontal jitter on proportional fonts in Canvas 2D) and anchored left-to-right typewriter.
    function renderLinePass(fullLine, ly, mode, { tabularDigits = false, typewriterChars = null, typewriterLeadHex = null, fill = "#FFFFFF", strokeHex = null, extraSpacingPx = 0 } = {}) {
      const isTw = typewriterChars != null;
      const visibleChars = isTw ? Math.max(0, Math.min(fullLine.length, typewriterChars)) : fullLine.length;
      if (visibleChars <= 0) return;
      if (!tabularDigits && !isTw) {
        ctx.textAlign = "center";
        if (mode === "stroke") ctx.strokeText(fullLine, 0, ly);
        else ctx.fillText(fullLine, 0, ly);
        return;
      }
      if (!tabularDigits && isTw) {
        // Measure full text width once so centered typewriter stays anchored with zero creep.
        const fullW = ctx.measureText(fullLine).width;
        const x0 = -fullW * 0.5;
        ctx.textAlign = "left";
        const shown = fullLine.slice(0, visibleChars);
        if (mode === "stroke") {
          ctx.strokeText(shown, x0, ly);
        } else if (typewriterLeadHex && visibleChars < fullLine.length && shown.length > 0) {
          const head = shown.slice(0, -1);
          const lead = shown.slice(-1);
          if (head) {
            ctx.fillStyle = fill;
            ctx.fillText(head, x0, ly);
          }
          ctx.fillStyle = typewriterLeadHex;
          ctx.fillText(lead, x0 + ctx.measureText(head).width, ly);
        } else {
          ctx.fillText(shown, x0, ly);
        }
        return;
      }
      // Fixed-slot tabular digit rendering for smooth zero-jitter Canvas 2D counters/odometers.
      const prevLs = typeof ctx.letterSpacing === "string" ? ctx.letterSpacing : null;
      if (prevLs !== null) ctx.letterSpacing = "0px";
      let maxDigitW = 0;
      for (let d = 0; d <= 9; d++) {
        maxDigitW = Math.max(maxDigitW, ctx.measureText(String(d)).width);
      }
      const chars = Array.from(fullLine);
      const widths = chars.map((ch) => (ch >= "0" && ch <= "9" ? maxDigitW : ctx.measureText(ch).width));
      const totalW = widths.reduce((a, b) => a + b, 0) + Math.max(0, chars.length - 1) * extraSpacingPx;
      let cx = -totalW * 0.5;
      ctx.textAlign = "center";
      for (let i = 0; i < Math.min(chars.length, visibleChars); i++) {
        const ch = chars[i];
        const cw = widths[i];
        const px = cx + cw * 0.5;
        if (mode === "stroke") {
          ctx.strokeText(ch, px, ly);
        } else {
          if (typewriterLeadHex && isTw && visibleChars < chars.length && i === visibleChars - 1) {
            ctx.fillStyle = typewriterLeadHex;
          } else {
            ctx.fillStyle = fill;
          }
          ctx.fillText(ch, px, ly);
        }
        cx += cw + extraSpacingPx;
      }
      if (prevLs !== null) ctx.letterSpacing = prevLs;
    }

    // Editorial typography renderer with soft directional cinema shadow, optional divider rule
    // for dual-unit stacks, tabular digit slots, and anchored typewriter.
    function drawGlowingText(text, x, y, fontPx, { fill = "#F4F1EA", glowHex = null, glowStrength = "none", angle = 0, scale = 1.0, alpha = 1, family = "Montserrat", weight = 800, fontStyle = "normal", letterSpacing = 0, strokeHex = null, strokeWidth = 0, lineHeightMult = 1.08, tabularDigits = false, typewriterChars = null, typewriterLeadHex = null, subPill = null, shadowBlurMult = 0.22, shadowAlpha = 0.46, shadowOffsetYMult = 0.055, dividerRule = false, dividerColor = null } = {}) {
      if (alpha <= 0.005 || scale <= 0.01) return;
      const lines = String(text ?? "").split("\\n");
      const lineStep = fontPx * (dividerRule ? Math.max(1.24, lineHeightMult) : lineHeightMult);
      const totalH = (lines.length - 1) * lineStep;
      const fallback = inferFontFallback(family);
      const stylePrefix = fontStyle && fontStyle !== "normal" ? fontStyle + " " : "";
      ctx.save();
      ctx.translate(x, y);
      if (angle) ctx.rotate(angle);
      if (Math.abs(scale - 1.0) > 1e-4) ctx.scale(scale, scale);
      ctx.font = stylePrefix + weight + " " + Math.round(fontPx) + "px '" + family + "', " + fallback;
      const extraSpacingPx = resolveCanvasLetterSpacingPx(letterSpacing, fontPx);
      applyCanvasLetterSpacing(letterSpacing, fontPx);
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      // Distribute typewriter character budget cleanly across multi-line strings.
      const lineBudgets = [];
      let remChars = typewriterChars;
      for (let li = 0; li < lines.length; li++) {
        if (remChars == null) {
          lineBudgets.push(null);
        } else {
          const take = Math.max(0, Math.min(lines[li].length, remChars));
          lineBudgets.push(take);
          remChars = Math.max(0, remChars - lines[li].length - 1);
        }
      }

      if (glowHex && glowStrength && glowStrength !== "none") {
        const rings = glowStrength === "intense"
          ? [[fontPx * 0.85, 0.55], [fontPx * 0.45, 0.82], [fontPx * 0.18, 0.96]]
          : glowStrength === "subtle"
            ? [[fontPx * 0.32, 0.48], [fontPx * 0.14, 0.68]]
            : [[fontPx * 0.58, 0.46], [fontPx * 0.26, 0.74], [fontPx * 0.12, 0.90]];
        for (const [blurR, a] of rings) {
          ctx.save();
          ctx.globalAlpha = alpha * a;
          ctx.shadowColor = glowHex;
          ctx.shadowBlur = blurR;
          ctx.fillStyle = fill;
          for (let li = 0; li < lines.length; li++) {
            renderLinePass(lines[li], -totalH * 0.5 + li * lineStep, "fill", {
              tabularDigits,
              typewriterChars: lineBudgets[li],
              fill,
              extraSpacingPx,
            });
          }
          ctx.restore();
        }
      }
      ctx.globalAlpha = alpha;
      ctx.shadowColor = "rgba(3, 14, 22, " + clamp(shadowAlpha, 0, 1).toFixed(2) + ")";
      ctx.shadowBlur = Math.max(6, fontPx * shadowBlurMult);
      ctx.shadowOffsetY = Math.max(2, fontPx * shadowOffsetYMult);
      if (strokeHex && strokeWidth > 0) {
        ctx.strokeStyle = strokeHex;
        ctx.lineWidth = Math.min(strokeWidth, fontPx * 0.24);
        ctx.lineJoin = "round";
        ctx.miterLimit = 2;
        for (let li = 0; li < lines.length; li++) {
          renderLinePass(lines[li], -totalH * 0.5 + li * lineStep, "stroke", {
            tabularDigits,
            typewriterChars: lineBudgets[li],
            strokeHex,
            extraSpacingPx,
          });
        }
      }
      ctx.fillStyle = fill;
      for (let li = 0; li < lines.length; li++) {
        renderLinePass(lines[li], -totalH * 0.5 + li * lineStep, "fill", {
          tabularDigits,
          typewriterChars: lineBudgets[li],
          typewriterLeadHex,
          fill,
          extraSpacingPx,
        });
      }
      if (dividerRule && lines.length >= 2) {
        const maxW = Math.max(...lines.map((ln) => ctx.measureText(ln).width), fontPx * 1.4);
        const ruleW = maxW * 1.06;
        const ruleH = Math.max(3, Math.round(fontPx * 0.065));
        ctx.fillStyle = dividerColor || fill;
        ctx.fillRect(-ruleW * 0.5, -totalH * 0.5 + lineStep * 0.5 - ruleH * 0.5, ruleW, ruleH);
      }

      if (subPill && subPill.alpha > 0.01 && subPill.text) {
        const pScale = subPill.scale ?? 1.0;
        const pFont = subPill.font_px ?? Math.max(18, Math.round(fontPx * 0.26));
        const pY = (totalH * 0.5) + fontPx * 0.52 + (subPill.dy ?? 6);
        ctx.save();
        ctx.translate(0, pY);
        ctx.scale(pScale, pScale);
        ctx.globalAlpha = alpha * subPill.alpha;
        ctx.font = "800 " + pFont + "px '" + family + "', " + fallback;
        applyCanvasLetterSpacing(0, pFont);
        const tw = ctx.measureText(subPill.text).width;
        const iconW = subPill.icon === "person" ? pFont * 0.95 : 0;
        const padX = pFont * 0.55;
        const pillW = tw + iconW + padX * 2;
        const pillH = pFont * 1.48;
        const r = pillH * 0.5;
        ctx.shadowColor = "rgba(0,0,0,0.65)";
        ctx.shadowBlur = 10;
        ctx.shadowOffsetY = 3;
        ctx.fillStyle = subPill.bg_hex || fill;
        ctx.beginPath();
        ctx.roundRect(-pillW * 0.5, -pillH * 0.5, pillW, pillH, r);
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.shadowOffsetY = 0;
        if (subPill.border_hex) {
          ctx.strokeStyle = subPill.border_hex;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        const fg = subPill.text_hex || "#FFFFFF";
        if (subPill.icon === "person") {
          const ix = -pillW * 0.5 + padX + iconW * 0.36;
          ctx.fillStyle = fg;
          ctx.beginPath();
          ctx.arc(ix, -pFont * 0.20, pFont * 0.19, 0, Math.PI * 2);
          ctx.fill();
          ctx.beginPath();
          ctx.arc(ix, pFont * 0.36, pFont * 0.33, Math.PI, 0, false);
          ctx.closePath();
          ctx.fill();
        }
        ctx.fillStyle = fg;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(subPill.text, -pillW * 0.5 + padX + iconW, 1);
        ctx.restore();
      }
      ctx.restore();
    }

    // Arc-length-parametrized curved cartographic label for rivers, straits, coastlines, and ranges.
    function drawCurvedMapLabel(screenPts, text, fontPx, { fill = "#A8D8FF", family = "Lora", weight = 600, fontStyle = "italic", letterSpacingPx = 0, strokeHex = "rgba(3,22,31,0.78)", strokeWidth = 2.0, alpha = 1.0, offsetPx = 0, revealProgress = 1.0, maxCharAngleDeg = 22 } = {}) {
      if (alpha <= 0.005 || !screenPts || screenPts.length < 2 || !text) return;
      // Auto-orient left-to-right so curved map labels are never rendered upside-down.
      let pts = screenPts;
      const first = pts[0];
      const last = pts[pts.length - 1];
      if (last.x < first.x) {
        pts = [...pts].reverse();
      }
      const cum = [0];
      for (let i = 1; i < pts.length; i++) {
        cum.push(cum[i - 1] + Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y));
      }
      const totalLen = cum[cum.length - 1];
      if (totalLen < fontPx * 0.8) return;

      const sampleAt = (s) => {
        const clamped = Math.max(0, Math.min(totalLen, s));
        let lo = 0;
        let hi = cum.length - 1;
        while (lo + 1 < hi) {
          const mid = (lo + hi) >> 1;
          if (cum[mid] <= clamped) lo = mid;
          else hi = mid;
        }
        const segLen = Math.max(1e-6, cum[hi] - cum[lo]);
        const u = (clamped - cum[lo]) / segLen;
        const p0 = pts[lo];
        const p1 = pts[hi];
        const dx = p1.x - p0.x;
        const dy = p1.y - p0.y;
        const ang = Math.atan2(dy, dx);
        const nx = -Math.sin(ang);
        const ny = Math.cos(ang);
        return {
          x: p0.x + dx * u + nx * offsetPx,
          y: p0.y + dy * u + ny * offsetPx,
          angle: ang,
        };
      };

      const fallback = inferFontFallback(family);
      const stylePrefix = fontStyle && fontStyle !== "normal" ? fontStyle + " " : "";
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.font = stylePrefix + weight + " " + Math.round(fontPx) + "px '" + family + "', " + fallback;
      applyCanvasLetterSpacing(0, fontPx);
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      const chars = Array.from(String(text));
      const charWidths = chars.map((ch) => ctx.measureText(ch).width);
      // Pairwise optical kerning adjustment preserves natural glyph spacing (e.g. AV, WA, To)
      // when laying out curved river, strait, and coastline labels character-by-character.
      const advances = chars.map((ch, i) => {
        const chW = charWidths[i];
        let kern = 0;
        if (i + 1 < chars.length) {
          const next = chars[i + 1];
          const pairW = ctx.measureText(ch + next).width;
          kern = pairW - (chW + charWidths[i + 1]);
        }
        return Math.max(chW * 0.35, chW + kern) + letterSpacingPx;
      });
      const textLen = advances.reduce((a, b) => a + b, 0) - letterSpacingPx;
      const startS = Math.max(0, (totalLen - textLen) * 0.5);
      const visibleCount = Math.max(0, Math.round(chars.length * clamp(revealProgress, 0, 1)));
      const maxDeltaRad = (maxCharAngleDeg * Math.PI) / 180;

      // Pass 1: crisp dark halo; Pass 2: clean high-luma fill.
      const passes = strokeHex && strokeWidth > 0 ? ["stroke", "fill"] : ["fill"];
      for (const pass of passes) {
        let sCur = startS;
        let prevAng = null;
        for (let i = 0; i < visibleCount; i++) {
          const ch = chars[i];
          const adv = advances[i];
          const midS = sCur + charWidths[i] * 0.5;
          const pose = sampleAt(midS);
          let ang = pose.angle;
          if (prevAng != null) {
            let delta = ang - prevAng;
            while (delta > Math.PI) delta -= Math.PI * 2;
            while (delta < -Math.PI) delta += Math.PI * 2;
            if (Math.abs(delta) > maxDeltaRad) {
              ang = prevAng + Math.sign(delta) * maxDeltaRad;
            }
          }
          prevAng = ang;
          if (ch.trim()) {
            ctx.save();
            ctx.translate(pose.x, pose.y);
            ctx.rotate(ang);
            if (pass === "stroke") {
              ctx.strokeStyle = strokeHex;
              ctx.lineWidth = Math.min(strokeWidth, fontPx * 0.24);
              ctx.lineJoin = "round";
              ctx.miterLimit = 2;
              ctx.shadowColor = "rgba(0,0,0,0.75)";
              ctx.shadowBlur = Math.max(3, fontPx * 0.1);
              ctx.strokeText(ch, 0, 0);
            } else {
              ctx.fillStyle = fill;
              ctx.fillText(ch, 0, 0);
            }
            ctx.restore();
          }
          sCur += adv;
        }
      }
      ctx.restore();
    }
`;
}
