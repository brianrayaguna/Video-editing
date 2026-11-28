export function buildPolygonsRuntime() {
  return `
    function borderTraceOptions(ringsLL, heads, startLngLat, dir) {
      const startIndex = ringsLL.map((r) => {
        if (startLngLat) {
          return nearestVertexIndex(r.map((c) => ({ x: c[0], y: c[1] })), { x: startLngLat[0], y: startLngLat[1] });
        }
        let best = 0;
        for (let i = 1; i < r.length; i++) if (r[i][1] > r[best][1]) best = i;
        return best;
      });
      // Lat grows northward (y up), so a ring that is clockwise on a north-up screen has negative area here.
      const wantCw = dir !== "ccw";
      const direction = ringsLL.map((r) => {
        const cwOnScreen = signedArea(r.map((c) => ({ x: c[0], y: c[1] }))) < 0;
        return cwOnScreen === wantCw ? 1 : -1;
      });
      return { heads: heads === 1 ? 1 : 2, startIndex, direction };
    }

    // Draw a flag raster over a territory's screen bounds (upright, optional quarter turns).
    // "stretch" maps the whole flag design onto the bounding box; "cover" keeps the flag's
    // proportions and covers the box, cropping the overflow. Optional travelling wind-gust
    // vertical slice displacement warps the fabric silhouette when flagWave.warp > 0.
    function drawFlagCover(tctx, img, bounds, rotateDeg = 0, fit = "stretch", flagWave = null, time = 0) {
      const quarter = ((Math.round((rotateDeg || 0) / 90) % 4) + 4) % 4;
      const aspect = quarter % 2 ? img.height / img.width : img.width / img.height;
      const r = fit === "cover"
        ? coverRect(bounds, aspect)
        : { x: bounds.minX, y: bounds.minY, w: Math.max(1, bounds.maxX - bounds.minX), h: Math.max(1, bounds.maxY - bounds.minY) };
      const dw = quarter % 2 ? r.h : r.w;
      const dh = quarter % 2 ? r.w : r.h;
      tctx.save();
      tctx.translate(r.x + r.w / 2, r.y + r.h / 2);
      tctx.rotate((quarter * Math.PI) / 2);
      tctx.imageSmoothingQuality = "high";
      const warpFrac = flagWave && flagWave.warp > 0 ? Number(flagWave.warp) : 0;
      if (warpFrac > 0.001 && dw >= 12) {
        const slices = 80;
        const sw = img.width / slices;
        const dwS = dw / slices;
        const warpPx = clamp(dh * warpFrac, 2, 42);
        const cycles = flagWave.cycles ?? 2.5;
        const speed = flagWave.speed ?? 0.5;
        for (let i = 0; i < slices; i++) {
          const u = (i + 0.5) / slices;
          const ph = 2 * Math.PI * (cycles * u - speed * time);
          const gust = 0.72 * Math.sin(ph) + 0.28 * Math.sin(2 * ph + 1.15);
          const dy = gust * warpPx;
          tctx.drawImage(
            img,
            i * sw,
            0,
            Math.max(1, sw + 0.9),
            img.height,
            -dw / 2 + i * dwS - 0.9,
            -dh / 2 + dy - warpPx * 0.35,
            dwS + 2.2,
            dh + warpPx * 0.70
          );
        }
      } else {
        tctx.drawImage(img, -dw / 2, -dh / 2, dw, dh);
      }
      tctx.restore();
    }

    // Cloth shading for a waving flag: highlight and shadow bands along "angleDeg" across the
    // territory bounds, composited onto the flag pixels only, plus optional satin gloss sheen.
    function applyClothShade(tctx, b, wave, t) {
      const stops = clothWaveStops(t, { ...wave, stops: 40 });
      const amp = Math.max(0.001, Number(wave.amplitude) || 0.22);
      const ang = ((wave.angleDeg ?? 20) * Math.PI) / 180;
      const cx = (b.minX + b.maxX) / 2;
      const cy = (b.minY + b.maxY) / 2;
      const half = Math.max(1, Math.hypot(b.maxX - b.minX, b.maxY - b.minY) / 2);
      const dx = Math.cos(ang) * half;
      const dy = Math.sin(ang) * half;
      const grad = tctx.createLinearGradient(cx - dx, cy - dy, cx + dx, cy + dy);
      for (const st of stops) {
        grad.addColorStop(st.offset, st.light >= 0
          ? "rgba(255,255,255," + clamp(st.light * 1.15, 0, 0.72).toFixed(3) + ")"
          : "rgba(0,0,0," + clamp(-st.light * 1.18, 0, 0.72).toFixed(3) + ")");
      }
      tctx.save();
      tctx.globalCompositeOperation = "source-atop";
      tctx.fillStyle = grad;
      tctx.fillRect(b.minX, b.minY, b.maxX - b.minX, b.maxY - b.minY);
      const gloss = wave.gloss > 0 ? clamp(Number(wave.gloss), 0, 1) : 0;
      if (gloss > 0.01) {
        const specGrad = tctx.createLinearGradient(cx - dx, cy - dy, cx + dx, cy + dy);
        for (const st of stops) {
          const ridge = Math.max(0, (st.light / amp - 0.30) / 0.70);
          const crestA = clamp(Math.pow(ridge, 1.8) * gloss * 0.56, 0, 0.68);
          specGrad.addColorStop(st.offset, "rgba(255,255,255," + crestA.toFixed(3) + ")");
        }
        tctx.fillStyle = specGrad;
        tctx.fillRect(b.minX, b.minY, b.maxX - b.minX, b.maxY - b.minY);

        const sheenGrad = tctx.createLinearGradient(b.minX, b.minY, b.maxX, b.maxY);
        sheenGrad.addColorStop(0.0, "rgba(255,255,255," + (0.24 * gloss).toFixed(3) + ")");
        sheenGrad.addColorStop(0.38, "rgba(255,255,255," + (0.04 * gloss).toFixed(3) + ")");
        sheenGrad.addColorStop(0.68, "rgba(255,255,255," + (0.14 * gloss).toFixed(3) + ")");
        sheenGrad.addColorStop(1.0, "rgba(255,255,255,0)");
        tctx.fillStyle = sheenGrad;
        tctx.fillRect(b.minX, b.minY, b.maxX - b.minX, b.maxY - b.minY);
      }
      tctx.restore();
    }

    // Soft-edged reveal mask applied with destination-in: "radial" grows from "origin" (default
    // bounds centre); "organic" grows a world-space noise-edged seed with continuous Gaussian
    // feathering (zero step banding); "wipe_right" / "wipe_left" / "wipe_down" / "wipe_up" travel
    // in the named direction (see wipeFrontEdge).
    function applyRevealMask(tctx, mode, progress, b, origin = null, organic = null, geomBounds = null, originLngLat = null) {
      const p = clamp(progress, 0, 1);
      if (!b || mode === "fade" || p >= 0.999) return;
      if (mode === "organic") {
        organicCtx.save();
        organicCtx.setTransform(ORG_SCALE, 0, 0, ORG_SCALE, 0, 0);
        organicCtx.clearRect(0, 0, W, H);
        organicCtx.filter = "blur(6px)";
        organicCtx.fillStyle = "#000";
        const rough = organic && organic.roughness != null ? organic.roughness : 0.22;
        const seed = organic && organic.seed != null ? organic.seed : 1;
        let drewWorld = false;
        if (geomBounds && geomBounds.length === 4) {
          const [minLng, minLat, maxLng, maxLat] = geomBounds;
          const origLL = originLngLat || [(minLng + maxLng) * 0.5, (minLat + maxLat) * 0.5];
          const om = lngLatToMercNorm(origLL);
          const cornersM = [
            lngLatToMercNorm([minLng, minLat]),
            lngLatToMercNorm([maxLng, minLat]),
            lngLatToMercNorm([maxLng, maxLat]),
            lngLatToMercNorm([minLng, maxLat]),
          ];
          const maxRMerc = Math.max(
            1e-6,
            ...cornersM.map((cm) => Math.hypot(cm.x - om.x, cm.y - om.y))
          );
          const radii = organicRevealRadii(p, maxRMerc / 0.88, { points: 120, roughness: rough, seed });
          const ringLL = radii.map((r, i) => {
            const th = (2 * Math.PI * i) / radii.length;
            return mercNormToLngLat(om.x + Math.cos(th) * r, om.y + Math.sin(th) * r);
          });
          const pts = projectRingClipped(ringLL);
          if (pts.length >= 3) {
            organicCtx.beginPath();
            for (let i = 0; i < pts.length; i++) {
              if (i === 0) organicCtx.moveTo(pts[i].x, pts[i].y);
              else organicCtx.lineTo(pts[i].x, pts[i].y);
            }
            organicCtx.closePath();
            organicCtx.fill();
            drewWorld = true;
          }
        }
        if (!drewWorld) {
          const cx = origin ? origin.x : (b.minX + b.maxX) / 2;
          const cy = origin ? origin.y : (b.minY + b.maxY) / 2;
          const R = Math.max(
            Math.hypot(b.minX - cx, b.minY - cy), Math.hypot(b.maxX - cx, b.minY - cy),
            Math.hypot(b.minX - cx, b.maxY - cy), Math.hypot(b.maxX - cx, b.maxY - cy), 1
          );
          const radii = organicRevealRadii(p, R / 0.88, { points: 120, roughness: rough, seed });
          organicCtx.beginPath();
          radii.forEach((r, i) => {
            const th = (2 * Math.PI * i) / radii.length;
            const x = cx + Math.cos(th) * r;
            const y = cy + Math.sin(th) * r;
            if (i === 0) organicCtx.moveTo(x, y); else organicCtx.lineTo(x, y);
          });
          organicCtx.closePath();
          organicCtx.fill();
        }
        organicCtx.filter = "none";
        organicCtx.restore();
        tctx.save();
        tctx.globalCompositeOperation = "destination-in";
        tctx.drawImage(organicCanvas, 0, 0, W, H);
        tctx.restore();
        return;
      }
      tctx.save();
      tctx.globalCompositeOperation = "destination-in";
      let grad = null;
      if (mode === "radial") {
        const cx = origin ? origin.x : (b.minX + b.maxX) / 2;
        const cy = origin ? origin.y : (b.minY + b.maxY) / 2;
        const R = Math.max(
          Math.hypot(b.minX - cx, b.minY - cy), Math.hypot(b.maxX - cx, b.minY - cy),
          Math.hypot(b.minX - cx, b.maxY - cy), Math.hypot(b.maxX - cx, b.maxY - cy), 1
        );
        const feather = 0.12 * R;
        const r1 = Math.max(0.01, p * (R + feather));
        grad = tctx.createRadialGradient(cx, cy, Math.max(0, r1 - feather), cx, cy, r1);
      } else {
        const { horiz, back, front } = wipeFrontEdge(mode, p, b);
        grad = horiz ? tctx.createLinearGradient(back, 0, front, 0) : tctx.createLinearGradient(0, back, 0, front);
      }
      grad.addColorStop(0, "rgba(0,0,0,1)");
      grad.addColorStop(1, "rgba(0,0,0,0)");
      tctx.fillStyle = grad;
      tctx.fillRect(0, 0, W, H);
      tctx.restore();
    }

    // World-space surface-locked or concentric-contour progressive interior hatching clipped cleanly to maskCanvas.
    function drawProgressiveInteriorHatch(geom, geomBounds, {
      hatchColor = "rgba(255,255,255,0.24)",
      hatchSpacing = 18,
      hatchWidth = 3.2,
      hatchSpace = "world",
      hatchRevealMode = "fade",
      hatchProgress = 1.0,
      hatchStagger = 0.62,
      hatchDirection = "ltr",
      hatchAngleDeg = 45,
      hatchEase = "editorial_out",
      hatchRefZoom = null,
      hatchCross = false,
      hatchTipGlow = false,
      hatchGlowHex = null,
      fillRevealMode = "fade",
      fillReveal = 1.0,
      revealTargetBounds = null,
      fillRevealOriginPx = null,
      fillRevealOriginLL = null,
      fillRevealOrganic = null,
      revealAxis = null,
      revealProgress = 1.0,
      revealBounds = null,
      geomKey = "",
      alpha = 1.0,
    } = {}) {
      if (alpha <= 0.005 || hatchProgress <= 0.001) return;
      rimCtx.save();
      rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      rimCtx.clearRect(0, 0, W, H);
      rimCtx.globalCompositeOperation = "source-over";

      const tipPoints = [];
      if (hatchRevealMode === "contour_ripple") {
        // Exact Euclidean interior iso-contours via (S(d) \ S(d - w)) intersected with maskCanvas.
        const count = 5;
        const stepPx = Math.max(8, hatchSpacing * 0.85);
        const bandW = Math.max(1.5, hatchWidth);
        for (let k = 0; k < count; k++) {
          const st = hatchLineRevealState(k, count, hatchProgress, {
            mode: "contour_ripple",
            staggerFrac: hatchStagger,
            direction: hatchDirection,
            ease: hatchEase,
          });
          if (!st.active || st.alpha <= 0.005) continue;
          const dist = (k + 1) * stepPx;
          const lw = Math.max(1.0, bandW * st.widthScale);
          fxCtx.save();
          fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
          fxCtx.clearRect(0, 0, W, H);
          fxCtx.lineJoin = "round";
          fxCtx.lineCap = "round";
          fxCtx.strokeStyle = "#FFFFFF";
          fxCtx.lineWidth = 2 * dist;
          fxCtx.beginPath();
          traceGeom(fxCtx, geom);
          fxCtx.stroke();
          const innerD = Math.max(0, dist - lw);
          if (innerD > 0.25) {
            fxCtx.globalCompositeOperation = "destination-out";
            fxCtx.lineWidth = 2 * innerD;
            fxCtx.beginPath();
            traceGeom(fxCtx, geom);
            fxCtx.stroke();
          }
          fxCtx.globalCompositeOperation = "source-in";
          fxCtx.fillStyle = hatchColor;
          fxCtx.fillRect(0, 0, W, H);
          fxCtx.restore();

          rimCtx.save();
          rimCtx.globalAlpha = st.alpha * (1 - k * 0.12);
          rimCtx.drawImage(fxCanvas, 0, 0, W, H);
          rimCtx.restore();
        }
      } else if (hatchSpace === "screen" || !geomBounds) {
        const angRad = ((hatchAngleDeg ?? 45) * Math.PI) / 180;
        const sp = Math.max(4, hatchSpacing);
        const diag = Math.hypot(W, H);
        const cx = W * 0.5, cy = H * 0.5;
        const ux = Math.cos(angRad), uy = -Math.sin(angRad);
        const nx = Math.sin(angRad), ny = Math.cos(angRad);
        const halfN = diag * 0.65;
        const count = Math.max(2, Math.min(260, Math.ceil((2 * halfN) / sp)));
        rimCtx.strokeStyle = hatchColor;
        rimCtx.lineCap = "round";
        for (let i = 0; i < count; i++) {
          const st = hatchLineRevealState(i, count, hatchProgress, {
            mode: hatchRevealMode,
            staggerFrac: hatchStagger,
            direction: hatchDirection,
            ease: hatchEase,
          });
          if (!st.active || st.alpha <= 0.005) continue;
          const nOff = -halfN + i * sp;
          const u0 = lerp(-halfN, halfN, st.drawFrom);
          const u1 = lerp(-halfN, halfN, st.drawTo);
          rimCtx.save();
          rimCtx.globalAlpha = st.alpha;
          rimCtx.lineWidth = Math.max(0.8, hatchWidth * st.widthScale);
          rimCtx.beginPath();
          rimCtx.moveTo(cx + nOff * nx + u0 * ux, cy + nOff * ny + u0 * uy);
          rimCtx.lineTo(cx + nOff * nx + u1 * ux, cy + nOff * ny + u1 * uy);
          rimCtx.stroke();
          rimCtx.restore();
        }
      } else {
        // World-space surface-locked Mercator hatch with octave blending & progressive per-line reveal.
        const curZoom = map.getZoom();
        const oct = computeOctaveHatchSpacing(hatchSpacing, curZoom, hatchRefZoom);
        const angles = hatchCross ? [hatchAngleDeg, hatchAngleDeg + 90] : [hatchAngleDeg];
        const bObj = {
          minLng: geomBounds[0],
          minLat: geomBounds[1],
          maxLng: geomBounds[2],
          maxLat: geomBounds[3],
        };
        const spacingStep = oct.subAlpha > 0.02 ? oct.subSpacingMerc : oct.primarySpacingMerc;
        const useSubFlag = oct.subAlpha > 0.02;
        for (let ai = 0; ai < angles.length; ai++) {
          const ang = angles[ai];
          const cacheKey = [
            geomKey || geomBounds.map((v) => v.toFixed(3)).join(","),
            ang.toFixed(1),
            oct.octave,
            useSubFlag ? "s" : "p",
            spacingStep.toPrecision(8),
            hatchSpacing,
          ].join("|");
          let lines = __worldHatchCache.get(cacheKey);
          if (!lines) {
            lines = buildWorldHatchLines(bObj, {
              angleDeg: ang,
              spacingMerc: spacingStep,
              maxLines: 180,
              padFrac: 0.14,
              segmentsPerLine: 10,
            });
            if (__worldHatchCache.size > 128) __worldHatchCache.clear();
            __worldHatchCache.set(cacheKey, lines);
          }
          const total = lines.length;
          const passProg = ai === 0 ? hatchProgress : clamp((hatchProgress - 0.18) / 0.82, 0, 1);
          if (passProg <= 0.001 || total === 0) continue;
          rimCtx.strokeStyle = hatchColor;
          rimCtx.lineCap = "round";
          rimCtx.lineJoin = "round";
          for (let i = 0; i < total; i++) {
            const line = lines[i];
            const octaveAlpha = useSubFlag && line.isSub ? oct.subAlpha : 1.0;
            if (octaveAlpha <= 0.01) continue;
            const st = hatchLineRevealState(i, total, passProg, {
              mode: hatchRevealMode,
              staggerFrac: hatchStagger,
              direction: hatchDirection,
              ease: hatchEase,
            });
            if (!st.active || st.alpha <= 0.005) continue;
            const subCoords = slicePolylineFraction(line.coords, st.drawFrom, st.drawTo);
            if (subCoords.length < 2) continue;
            const projSegs = projectPolylineClipped(subCoords);
            if (!projSegs.length) continue;
            rimCtx.save();
            rimCtx.globalAlpha = st.alpha * octaveAlpha * (ai === 1 ? 0.72 : 1.0);
            rimCtx.lineWidth = Math.max(0.8, hatchWidth * st.widthScale);
            rimCtx.beginPath();
            for (const segPts of projSegs) {
              if (segPts.length < 2) continue;
              rimCtx.moveTo(segPts[0].x, segPts[0].y);
              for (let k = 1; k < segPts.length; k++) rimCtx.lineTo(segPts[k].x, segPts[k].y);
            }
            rimCtx.stroke();
            rimCtx.restore();
            if (hatchTipGlow && st.drawTo > 0.02 && st.drawTo < 0.985) {
              const tipSeg = (hatchDirection === "alternate" && i % 2 === 1)
                ? projSegs[0]?.[0]
                : projSegs[projSegs.length - 1]?.[projSegs[projSegs.length - 1].length - 1];
              if (tipSeg && Number.isFinite(tipSeg.x) && Number.isFinite(tipSeg.y)) {
                tipPoints.push({ x: tipSeg.x, y: tipSeg.y, a: st.alpha * octaveAlpha });
              }
            }
          }
        }
      }

      // Optional luminous tip spark riding each actively drawing hatch line (clipped inside silhouette)
      if (tipPoints.length > 0) {
        const gHex = hatchGlowHex || "#FFFFFF";
        rimCtx.save();
        rimCtx.globalCompositeOperation = "lighter";
        for (const tp of tipPoints) {
          const rad = Math.max(6, hatchWidth * 3.2);
          const g = rimCtx.createRadialGradient(tp.x, tp.y, 0, tp.x, tp.y, rad);
          g.addColorStop(0, "rgba(255,255,255," + (0.85 * tp.a).toFixed(3) + ")");
          g.addColorStop(0.45, rgbaStr(gHex, 0.45 * tp.a));
          g.addColorStop(1, rgbaStr(gHex, 0));
          rimCtx.fillStyle = g;
          rimCtx.beginPath();
          rimCtx.arc(tp.x, tp.y, rad, 0, Math.PI * 2);
          rimCtx.fill();
        }
        rimCtx.restore();
      }

      // Mask to active reveal front (if non-fade) and strictly clip inside polygon silhouette
      if (fillRevealMode !== "fade" && fillReveal < 0.999) {
        applyRevealMask(rimCtx, fillRevealMode, fillReveal, revealTargetBounds, fillRevealOriginPx, fillRevealOrganic, geomBounds, fillRevealOriginLL);
      }
      rimCtx.globalCompositeOperation = "destination-in";
      rimCtx.drawImage(maskCanvas, 0, 0, W, H);
      rimCtx.restore();

      ctx.save();
      if (revealAxis && revealProgress < 0.999) {
        applyWorldDirectionalClip(ctx, geom, revealAxis, revealProgress, revealBounds);
      }
      ctx.globalAlpha = alpha * (fillRevealMode === "fade" ? clamp(fillReveal, 0, 1) : 1);
      ctx.drawImage(rimCanvas, 0, 0, W, H);
      ctx.restore();
    }

    // Shape-aware studio spotlight: dims map outside target polygons with soft feathered cutout.
    function drawFocusSpotlight(geoms, { dimAlpha = 0.58, dimHex = "#04101A", featherPx = 36, rimGlowHex = null, rimGlowAlpha = 0.25, alpha = 1.0 } = {}) {
      if (alpha <= 0.005 || dimAlpha <= 0.005) return;
      const list = (geoms || []).filter(Boolean);
      if (!list.length) return;
      maskCtx.save();
      maskCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      maskCtx.clearRect(0, 0, W, H);
      maskCtx.fillStyle = "#FFFFFF";
      maskCtx.beginPath();
      for (const g of list) traceGeom(maskCtx, g);
      maskCtx.fill();
      maskCtx.restore();

      const blurR = clamp(Math.round((Number(featherPx) || 36) * ORG_SCALE), 2, 60);
      organicCtx.save();
      organicCtx.setTransform(ORG_SCALE, 0, 0, ORG_SCALE, 0, 0);
      organicCtx.clearRect(0, 0, W, H);
      organicCtx.filter = "blur(" + blurR + "px)";
      organicCtx.drawImage(maskCanvas, 0, 0, W, H);
      organicCtx.filter = "none";
      organicCtx.restore();

      fxCtx.save();
      fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      fxCtx.clearRect(0, 0, W, H);
      fxCtx.fillStyle = rgbaStr(dimHex, clamp(dimAlpha * alpha, 0, 0.95));
      fxCtx.fillRect(0, 0, W, H);
      fxCtx.globalCompositeOperation = "destination-out";
      fxCtx.drawImage(organicCanvas, 0, 0, W, H);
      fxCtx.restore();

      ctx.save();
      ctx.globalCompositeOperation = "source-over";
      ctx.drawImage(fxCanvas, 0, 0, W, H);
      if (rimGlowHex && rimGlowAlpha > 0.005) {
        fxCtx.save();
        fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
        fxCtx.clearRect(0, 0, W, H);
        fxCtx.drawImage(organicCanvas, 0, 0, W, H);
        fxCtx.globalCompositeOperation = "destination-out";
        fxCtx.drawImage(maskCanvas, 0, 0, W, H);
        fxCtx.globalCompositeOperation = "source-in";
        fxCtx.fillStyle = rimGlowHex;
        fxCtx.fillRect(0, 0, W, H);
        fxCtx.restore();
        ctx.globalCompositeOperation = "screen";
        ctx.globalAlpha = clamp(rimGlowAlpha * alpha, 0, 0.85);
        ctx.drawImage(fxCanvas, 0, 0, W, H);
      }
      ctx.restore();
      applyMicroDither(ctx, 0.025 * alpha);
    }

    const __geomMetaCache = new WeakMap();
    function getCachedGeomMeta(geom) {
      if (geom && typeof geom === "object") {
        let cached = __geomMetaCache.get(geom);
        if (!cached) {
          const rings = polygonRings(geom);
          cached = { bounds: computeGeomBounds(geom), outer: rings.outer, inner: rings.inner };
          __geomMetaCache.set(geom, cached);
        }
        return cached;
      }
      const rings = polygonRings(geom);
      return { bounds: computeGeomBounds(geom), outer: rings.outer, inner: rings.inner };
    }

    // Seamless exterior polygon dissolve + 2.5D lift/bevel/cast-shadow + 2-step pyramid screen bloom +
    // world-space border trace with comet head + world-space progressive hatch & optical lighting sweeps.
    function drawDissolvedPolygon(geom, {
      fillHex,
      fillAlpha = 0.56,
      rimHex = "#F4F1EA",
      rimWidth = 3.0,
      bloomHex = "#22C55E",
      bloomScale = 1.0,
      alpha = 1.0,
      preserveTerrain = true,
      borderReveal = 1.0,
      fillReveal = 1.0,
      revealAxis = null,
      revealProgress = 1.0,
      revealBounds = null,
      outlineOnly = false,
      perimeterProgress = 1.0,
      featherPx = 0,
      hatch = false,
      hatchColor = "rgba(255,255,255,0.22)",
      hatchSpacing = 18,
      hatchWidth = 3.5,
      hatchSpace = "world",
      hatchRevealMode = "fade",
      hatchProgress = 1.0,
      hatchStagger = 0.62,
      hatchDirection = "ltr",
      hatchAngleDeg = 45,
      hatchEase = "editorial_out",
      hatchRefZoom = null,
      hatchCross = false,
      hatchTipGlow = false,
      hatchGlowHex = null,
      flashHex = null,
      flashIntensity = 0,
      traced = false,
      traceProgress = 1.0,
      traceEndS = 0,
      traceHeads = 2,
      traceStart = null,
      traceDir = "cw",
      traceHeadGlow = false,
      flagImg = null,
      flagAlpha = 1.0,
      flagBlend = "source-over",
      flagRotateDeg = 0,
      flagFit = "stretch",
      fillRevealMode = "fade",
      fillRevealOrigin = null,
      fillRevealOrganic = null,
      fillBloomOvershoot = 1.0,
      flagWave = null,
      dissolveSeams = false,
      liftPx = 0,
      liftProgress = 1.0,
      castShadow = null,
      bevelLight = 0,
      lightSweep = null,
      rimGlint = null,
      textureFill = null,
      textureScale = 1.0,
      geomKey = "",
      time = 0,
    } = {}) {
      if (alpha <= 0.005 || !geom) return;
      if (outlineOnly && perimeterProgress < 0.999 && !traced) {
        drawProgressiveGeomPerimeter(geom, perimeterProgress, { rimHex, rimWidth, bloomHex, bloomScale, alpha });
        return;
      }
      if (traced && traceProgress <= 0.001 && fillReveal <= 0.005) return;
      if (revealAxis && revealProgress <= 0.001) return;

      const geomMeta = getCachedGeomMeta(geom);
      const geomBounds = geomMeta.bounds;
      const isMultiPart = Boolean(dissolveSeams) || Array.isArray(geom) || (geom && (geom.type === "FeatureCollection" || geom.type === "GeometryCollection"));
      const needOuter = traced || Boolean(flagImg) || fillRevealMode !== "fade" || Boolean(rimGlint) || Boolean(lightSweep);
      const ringsLL = needOuter ? geomMeta.outer : [];
      const ringsPx = needOuter ? ringsLL.map((r) => projectRingClipped(r)) : [];

      // 1. Build clean solid silhouette mask (seam-bridge stroke only on multi-part dissolved regions)
      maskCtx.save();
      maskCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      maskCtx.clearRect(0, 0, W, H);
      maskCtx.fillStyle = "#FFFFFF";
      maskCtx.beginPath();
      traceGeom(maskCtx, geom);
      maskCtx.fill();
      if (isMultiPart) {
        maskCtx.strokeStyle = "#FFFFFF";
        maskCtx.lineWidth = 3.5;
        maskCtx.lineJoin = "round";
        maskCtx.stroke();
      }
      maskCtx.restore();

      // 2. Optional 2.5D tactile lift & directional cast shadow synced to global SUN_VEC
      const effLiftPx = Math.max(0, Number(liftPx) || 0) * clamp(liftProgress, 0, 1.15);
      const shadowCfg = castShadow === true
        ? { opacity: 0.44, blurPx: Math.max(10, effLiftPx * 0.95 + 8), offsetScale: 1.0 }
        : (castShadow && typeof castShadow === "object"
          ? {
              opacity: clamp(Number(castShadow.opacity ?? 0.44), 0, 0.9),
              blurPx: Math.max(4, Number(castShadow.blur_px ?? (effLiftPx * 0.95 + 10))),
              offsetScale: Math.max(0.2, Number(castShadow.offset_scale ?? 1.0)),
            }
          : (effLiftPx > 0.5 ? { opacity: 0.42, blurPx: Math.max(10, effLiftPx * 0.9 + 6), offsetScale: 1.0 } : null));

      if (shadowCfg && !outlineOnly && fillReveal > 0.01) {
        const shDist = Math.max(6, effLiftPx * 1.15 + 4) * shadowCfg.offsetScale;
        const shDx = SUN_VEC.shadowDx * shDist;
        const shDy = SUN_VEC.shadowDy * shDist;
        const blurOrg = clamp(Math.round(shadowCfg.blurPx * ORG_SCALE), 2, 40);
        organicCtx.save();
        organicCtx.setTransform(ORG_SCALE, 0, 0, ORG_SCALE, 0, 0);
        organicCtx.clearRect(0, 0, W, H);
        organicCtx.filter = "blur(" + blurOrg + "px)";
        organicCtx.drawImage(maskCanvas, shDx, shDy, W, H);
        organicCtx.filter = "none";
        organicCtx.globalCompositeOperation = "source-in";
        organicCtx.fillStyle = "#020A12";
        organicCtx.fillRect(0, 0, W, H);
        organicCtx.restore();

        ctx.save();
        ctx.globalAlpha = alpha * shadowCfg.opacity * clamp(fillReveal, 0, 1);
        ctx.drawImage(organicCanvas, 0, 0, W, H);
        ctx.restore();
      }

      // Faux 2.5D extruded skirt wall beneath lifted country block
      if (effLiftPx > 0.8 && !outlineOnly && fillReveal > 0.01) {
        const skirtColor = mixHex(fillHex || "#16A82A", "#030B12", 0.64);
        fxCtx.save();
        fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
        fxCtx.clearRect(0, 0, W, H);
        const steps = Math.max(2, Math.min(18, Math.ceil(effLiftPx / 1.4)));
        for (let s = 0; s < steps; s++) {
          const yOff = -((s / steps) * effLiftPx);
          fxCtx.drawImage(maskCanvas, 0, yOff, W, H);
        }
        fxCtx.globalCompositeOperation = "destination-out";
        fxCtx.drawImage(maskCanvas, 0, -effLiftPx, W, H);
        fxCtx.globalCompositeOperation = "source-in";
        fxCtx.fillStyle = skirtColor;
        fxCtx.fillRect(0, 0, W, H);
        fxCtx.restore();

        ctx.save();
        ctx.globalAlpha = alpha * Math.min(0.94, fillAlpha + 0.25) * clamp(fillReveal, 0, 1);
        ctx.drawImage(fxCanvas, 0, 0, W, H);
        ctx.restore();
      }

      // 3. Build exterior-only rim ring into supersampled rimCanvas.
      rimCtx.save();
      rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      rimCtx.clearRect(0, 0, W, H);
      rimCtx.globalCompositeOperation = "source-over";
      const rw = Math.max(1.8, rimWidth);
      let traceHeadsPx = [];
      let cometSegsPx = [];
      const cometCloseFade = traced
        ? (traceProgress < 0.999 ? 1.0 : 1.0 - easeOutCubic(seg(time, traceEndS, traceEndS + 0.28)))
        : 0;
      if (traced) {
        if (traceProgress > 0.001) {
          const holesLL = geomMeta.inner;
          const outerRes = perimeterPartialPathsLngLat(ringsLL, traceProgress, {
            ...borderTraceOptions(ringsLL, traceHeads, traceStart, traceDir),
            cometFraction: 0.055,
          });
          const holeRes = holesLL.length
            ? perimeterPartialPathsLngLat(holesLL, traceProgress, {
                ...borderTraceOptions(holesLL, traceHeads, traceStart, traceDir),
                cometFraction: 0.055,
              })
            : { paths: [], comets: [] };
          const allPathsLL = [...outerRes.paths, ...holeRes.paths];
          const allCometsLL = [...outerRes.comets, ...holeRes.comets];

          rimCtx.strokeStyle = "#FFFFFF";
          rimCtx.lineWidth = 2 * (rw + (isMultiPart ? 1.75 : 0.25));
          rimCtx.lineCap = "round";
          rimCtx.lineJoin = "round";
          rimCtx.beginPath();
          for (const pathLL of allPathsLL) {
            const segs = projectPolylineClipped(pathLL);
            for (const pts of segs) {
              if (pts.length < 2) continue;
              rimCtx.moveTo(pts[0].x, pts[0].y);
              for (let i = 1; i < pts.length; i++) rimCtx.lineTo(pts[i].x, pts[i].y);
              if (traceProgress >= 1) rimCtx.closePath();
              if (traceProgress < 1) traceHeadsPx.push(pts[pts.length - 1]);
            }
          }
          rimCtx.stroke();
          if (cometCloseFade > 0.01) {
            for (const cLL of allCometsLL) {
              for (const pts of projectPolylineClipped(cLL)) {
                if (pts.length >= 2) cometSegsPx.push(pts);
              }
            }
          }
        }
      } else if (!isMultiPart) {
        rimCtx.strokeStyle = "#FFFFFF";
        rimCtx.lineWidth = 2 * rw;
        rimCtx.lineCap = "round";
        rimCtx.lineJoin = "round";
        rimCtx.beginPath();
        traceGeom(rimCtx, geom);
        rimCtx.stroke();
      } else {
        const dirs = 16;
        for (let k = 0; k < dirs; k++) {
          const ang = (k / dirs) * Math.PI * 2;
          rimCtx.drawImage(maskCanvas, Math.cos(ang) * rw, Math.sin(ang) * rw, W, H);
        }
      }
      rimCtx.globalCompositeOperation = "destination-out";
      rimCtx.drawImage(maskCanvas, 0, 0, W, H);
      rimCtx.restore();

      // Begin lifted country body coordinate space
      ctx.save();
      if (effLiftPx > 0.05) ctx.translate(0, -effLiftPx);

      // 4. Exterior-only 2-step pyramid screen bloom (0.5x -> 0.25x prevents thin-rim shimmer)
      ctx.save();
      if (revealAxis && revealProgress < 0.999) {
        if (!applyWorldDirectionalClip(ctx, geom, revealAxis, revealProgress, revealBounds)) {
          ctx.restore();
          ctx.restore();
          return;
        }
      } else if (borderReveal < 0.999) {
        ctx.beginPath();
        ctx.rect(0, 0, W, H * clamp(borderReveal, 0, 1));
        ctx.clip();
      }
      const overshootWave = (fillBloomOvershoot > 1.001 && fillReveal > 0.005 && fillReveal < 0.999)
        ? 1.0 + (fillBloomOvershoot - 1.0) * Math.sin(fillReveal * Math.PI) * (1 - 0.35 * fillReveal)
        : 1.0;
      const effBloomHex = (flashHex && flashIntensity > 0.01) ? flashHex : bloomHex;
      const effBloomScale = bloomScale * overshootWave + flashIntensity * 1.15;
      if (effBloomHex && effBloomScale > 0) {
        rimCtx.save();
        rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
        rimCtx.globalCompositeOperation = "source-in";
        rimCtx.fillStyle = effBloomHex;
        rimCtx.fillRect(0, 0, W, H);
        rimCtx.restore();

        // Step 1: smooth 0.5x half-pyramid downsample
        glowHalfCtx.save();
        glowHalfCtx.clearRect(0, 0, glowHalfW, glowHalfH);
        glowHalfCtx.imageSmoothingEnabled = true;
        glowHalfCtx.imageSmoothingQuality = "high";
        glowHalfCtx.drawImage(rimCanvas, 0, 0, glowHalfW, glowHalfH);
        glowHalfCtx.restore();

        // Step 2: multi-radius glow on 0.25x buffer
        glowCtx.save();
        glowCtx.clearRect(0, 0, glowW, glowH);
        glowCtx.imageSmoothingEnabled = true;
        glowCtx.imageSmoothingQuality = "high";
        const passes = [
          [42 * effBloomScale * GLOW_SCALE, Math.min(0.95, 0.42 + flashIntensity * 0.40)],
          [20 * effBloomScale * GLOW_SCALE, Math.min(0.98, 0.62 + flashIntensity * 0.28)],
          [8 * effBloomScale * GLOW_SCALE, Math.min(1.0, 0.78 + flashIntensity * 0.20)],
        ];
        for (const [blurPx, a] of passes) {
          glowCtx.save();
          glowCtx.globalAlpha = a;
          glowCtx.shadowColor = effBloomHex;
          glowCtx.shadowBlur = Math.max(1, blurPx);
          glowCtx.drawImage(glowHalfCanvas, 0, 0, glowW, glowH);
          glowCtx.restore();
        }
        glowCtx.restore();

        ctx.save();
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = "high";
        ctx.globalCompositeOperation = "screen";
        ctx.globalAlpha = clamp(alpha * 0.92, 0, 1);
        ctx.drawImage(glowCanvas, 0, 0, W, H);
        ctx.globalCompositeOperation = "lighter";
        ctx.globalAlpha = clamp(alpha * 0.22, 0, 0.45);
        ctx.drawImage(glowCanvas, 0, 0, W, H);
        ctx.restore();
      }

      // 5. Crisp exterior rim (animated by borderReveal)
      if (rimHex && rimWidth > 0) {
        rimCtx.save();
        rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
        rimCtx.globalCompositeOperation = "source-in";
        rimCtx.fillStyle = (flashHex && flashIntensity > 0.25) ? "#FFFFFF" : rimHex;
        rimCtx.fillRect(0, 0, W, H);
        rimCtx.restore();
        ctx.globalCompositeOperation = "source-over";
        ctx.globalAlpha = alpha * 0.94;
        ctx.drawImage(rimCanvas, 0, 0, W, H);
      }

      // 5b. Travelling specular rim glint riding the exterior rim while polygon holds
      if (rimGlint && (!traced || traceProgress >= 0.99) && ringsLL.length > 0) {
        const gSpeed = Number(rimGlint.speed ?? 0.22);
        const gSpan = clamp(Number(rimGlint.span_frac ?? 0.14), 0.03, 0.45);
        const gCol = rimGlint.color || "#FFFFFF";
        const gInt = clamp(Number(rimGlint.intensity ?? 0.85), 0.05, 1.5);
        const phase = ((time * gSpeed) % 1 + 1) % 1;
        const glintPaths = perimeterWindowPathsLngLat(ringsLL, phase, gSpan);
        if (glintPaths.length > 0) {
          fxCtx.save();
          fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
          fxCtx.clearRect(0, 0, W, H);
          fxCtx.lineCap = "round";
          fxCtx.lineJoin = "round";
          for (const gpLL of glintPaths) {
            for (const pts of projectPolylineClipped(gpLL)) {
              if (pts.length < 2) continue;
              const p0 = pts[0], p1 = pts[pts.length - 1];
              const grad = fxCtx.createLinearGradient(p0.x, p0.y, p1.x, p1.y);
              grad.addColorStop(0, rgbaStr(gCol, 0));
              grad.addColorStop(0.5, rgbaStr(gCol, 0.95));
              grad.addColorStop(1, rgbaStr(gCol, 0));
              fxCtx.strokeStyle = grad;
              fxCtx.lineWidth = rw * 2.6;
              fxCtx.beginPath();
              fxCtx.moveTo(pts[0].x, pts[0].y);
              for (let i = 1; i < pts.length; i++) fxCtx.lineTo(pts[i].x, pts[i].y);
              fxCtx.stroke();
            }
          }
          fxCtx.globalCompositeOperation = "destination-in";
          fxCtx.drawImage(rimCanvas, 0, 0, W, H);
          fxCtx.restore();

          ctx.save();
          ctx.globalCompositeOperation = "lighter";
          ctx.globalAlpha = clamp(alpha * gInt, 0, 1);
          ctx.drawImage(fxCanvas, 0, 0, W, H);
          ctx.restore();
        }
      }

      // 5c. Tapered electric comet draw-head & flare during border_trace
      if (cometSegsPx.length > 0 && cometCloseFade > 0.01) {
        const glowHex = bloomHex || rimHex || "#FFFFFF";
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        for (const pts of cometSegsPx) {
          const p0 = pts[0], p1 = pts[pts.length - 1];
          const cg = ctx.createLinearGradient(p0.x, p0.y, p1.x, p1.y);
          cg.addColorStop(0, rgbaStr(glowHex, 0));
          cg.addColorStop(0.55, rgbaStr(glowHex, 0.72 * alpha * cometCloseFade));
          cg.addColorStop(1, "rgba(255,255,255," + (0.96 * alpha * cometCloseFade).toFixed(3) + ")");
          ctx.strokeStyle = cg;
          ctx.lineWidth = rw * 1.9;
          ctx.beginPath();
          ctx.moveTo(pts[0].x, pts[0].y);
          for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
          ctx.stroke();
        }
        ctx.restore();
      }
      if ((traceHeadGlow || cometSegsPx.length > 0) && traceHeadsPx.length) {
        const glowHex = bloomHex || rimHex;
        const flareScale = traceHeadGlow ? 6.0 : 3.6;
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        for (const hp of traceHeadsPx) {
          const rad = rw * flareScale;
          const g = ctx.createRadialGradient(hp.x, hp.y, 0, hp.x, hp.y, rad);
          g.addColorStop(0, "rgba(255,255,255," + (0.92 * alpha * cometCloseFade).toFixed(3) + ")");
          g.addColorStop(0.32, rgbaStr(glowHex, 0.56 * alpha * cometCloseFade));
          g.addColorStop(1, rgbaStr(glowHex, 0));
          ctx.globalAlpha = 1;
          ctx.fillStyle = g;
          ctx.beginPath(); ctx.arc(hp.x, hp.y, rad, 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore();
      }
      ctx.restore();

      // 6. Interior fill (terrain-preserving tint or flag raster), inner bevel, progressive hatch & light sweep
      if (!outlineOnly && fillReveal > 0.005) {
        const clusters = needOuter ? ringClusters(ringsPx, { viewport: { w: W, h: H } }) : [];
        const fillBounds = clusters.length ? clusters[0].bounds : null;
        const visibleClusters = clusters.filter(
          (c) => c.bounds.maxX > 0 && c.bounds.minX < W && c.bounds.maxY > 0 && c.bounds.minY < H
        );
        const revealTargetBounds = visibleClusters.length
          ? visibleClusters.reduce(
              (acc, c) => ({
                minX: Math.min(acc.minX, c.bounds.minX),
                minY: Math.min(acc.minY, c.bounds.minY),
                maxX: Math.max(acc.maxX, c.bounds.maxX),
                maxY: Math.max(acc.maxY, c.bounds.maxY),
              }),
              visibleClusters[0].bounds
            )
          : fillBounds;
        const fillRevealOriginPx = fillRevealOrigin ? projectPointSafe(fillRevealOrigin) : null;

        rimCtx.save();
        rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
        rimCtx.clearRect(0, 0, W, H);
        rimCtx.globalCompositeOperation = "source-over";
        if (flagImg && fillBounds) {
          for (const cluster of visibleClusters) {
            const cb = cluster.bounds;
            rimCtx.save();
            rimCtx.beginPath();
            rimCtx.rect(cb.minX, cb.minY, cb.maxX - cb.minX, cb.maxY - cb.minY);
            rimCtx.clip();
            drawFlagCover(rimCtx, flagImg, cb, flagRotateDeg, flagFit, flagWave, time);
            if (flagWave) applyClothShade(rimCtx, cb, flagWave, time);
            rimCtx.restore();
          }
          rimCtx.globalCompositeOperation = "destination-in";
          rimCtx.drawImage(maskCanvas, 0, 0, W, H);
        } else if (textureFill === "cracked_earth") {
          const patCanvas = getCrackedEarthCanvas();
          const pat = rimCtx.createPattern(patCanvas, "repeat");
          const centerLL = Array.isArray(geomBounds) && geomBounds.length >= 4
            ? [(geomBounds[0] + geomBounds[2]) * 0.5, (geomBounds[1] + geomBounds[3]) * 0.5]
            : [map.getCenter().lng, map.getCenter().lat];
          const mp = getMapPlaneMatrix(centerLL, 4.4);
          rimCtx.save();
          rimCtx.fillStyle = fillHex || "#9B8768";
          rimCtx.fillRect(0, 0, W, H);
          if (pat) {
            const sc = Math.max(0.25, Number(textureScale) || 1.0);
            rimCtx.transform(mp.a * sc, mp.b * sc, mp.c * sc, mp.d * sc, mp.e, mp.f);
            rimCtx.fillStyle = pat;
            rimCtx.fillRect(-4096, -4096, 8192, 8192);
          }
          rimCtx.restore();
          rimCtx.globalCompositeOperation = "destination-in";
          rimCtx.drawImage(maskCanvas, 0, 0, W, H);
        } else {
          rimCtx.drawImage(maskCanvas, 0, 0, W, H);
          rimCtx.globalCompositeOperation = "source-in";
          rimCtx.fillStyle = fillHex;
          rimCtx.fillRect(0, 0, W, H);
        }
        if (fillRevealMode !== "fade") {
          applyRevealMask(rimCtx, fillRevealMode, fillReveal, revealTargetBounds, fillRevealOriginPx, fillRevealOrganic, geomBounds, fillRevealOrigin);
        }
        rimCtx.restore();
        const revealAlpha = fillRevealMode === "fade" ? clamp(fillReveal, 0, 1) : 1;

        ctx.save();
        if (revealAxis && revealProgress < 0.999) {
          if (!applyWorldDirectionalClip(ctx, geom, revealAxis, revealProgress, revealBounds)) {
            ctx.restore();
            ctx.restore();
            return;
          }
        }
        const useFlag = Boolean(flagImg && fillBounds);
        ctx.globalCompositeOperation = useFlag ? flagBlend : "source-over";
        const baseFillA = (useFlag ? flagAlpha : fillAlpha) * overshootWave;
        ctx.globalAlpha = clamp(alpha * baseFillA * revealAlpha, 0, 1);
        if (featherPx > 0) {
          ctx.shadowColor = fillHex;
          ctx.shadowBlur = featherPx;
        }
        ctx.drawImage(rimCanvas, 0, 0, W, H);
        ctx.restore();

        // 6b. Subtle directional inner bevel (sun-facing inner highlight + opposite inner shadow)
        const bAmt = clamp(Number(bevelLight) || 0, 0, 1);
        if (bAmt > 0.01) {
          const bOff = 2.2;
          // Sun-facing highlight edge
          fxCtx.save();
          fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
          fxCtx.clearRect(0, 0, W, H);
          fxCtx.drawImage(maskCanvas, 0, 0, W, H);
          fxCtx.globalCompositeOperation = "destination-out";
          fxCtx.drawImage(maskCanvas, SUN_VEC.shadowDx * bOff, SUN_VEC.shadowDy * bOff, W, H);
          fxCtx.globalCompositeOperation = "source-in";
          fxCtx.fillStyle = "#FFFFFF";
          fxCtx.fillRect(0, 0, W, H);
          fxCtx.restore();
          ctx.save();
          ctx.globalCompositeOperation = "screen";
          ctx.globalAlpha = alpha * bAmt * 0.42 * revealAlpha;
          ctx.drawImage(fxCanvas, 0, 0, W, H);
          ctx.restore();

          // Shadow-facing inner depth edge
          fxCtx.save();
          fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
          fxCtx.clearRect(0, 0, W, H);
          fxCtx.drawImage(maskCanvas, 0, 0, W, H);
          fxCtx.globalCompositeOperation = "destination-out";
          fxCtx.drawImage(maskCanvas, SUN_VEC.lightDx * bOff, SUN_VEC.lightDy * bOff, W, H);
          fxCtx.globalCompositeOperation = "source-in";
          fxCtx.fillStyle = "#03101A";
          fxCtx.fillRect(0, 0, W, H);
          fxCtx.restore();
          ctx.save();
          ctx.globalCompositeOperation = "multiply";
          ctx.globalAlpha = alpha * bAmt * 0.34 * revealAlpha;
          ctx.drawImage(fxCanvas, 0, 0, W, H);
          ctx.restore();
        }

        // 6c. Progressive world-space / contour interior hatch
        if (hatch) {
          drawProgressiveInteriorHatch(geom, geomBounds, {
            hatchColor,
            hatchSpacing,
            hatchWidth,
            hatchSpace,
            hatchRevealMode,
            hatchProgress,
            hatchStagger,
            hatchDirection,
            hatchAngleDeg,
            hatchEase,
            hatchRefZoom,
            hatchCross,
            hatchTipGlow,
            hatchGlowHex: hatchGlowHex || bloomHex || rimHex,
            fillRevealMode,
            fillReveal,
            revealTargetBounds,
            fillRevealOriginPx,
            fillRevealOriginLL: fillRevealOrigin,
            fillRevealOrganic,
            revealAxis,
            revealProgress,
            revealBounds,
            geomKey,
            alpha,
          });
        }

        // 6d. Optional diagonal specular light sweep across country silhouette
        if (lightSweep && lightSweep.progress > 0.001 && lightSweep.progress < 0.999) {
          const sb = revealTargetBounds || { minX: 0, minY: 0, maxX: W, maxY: H };
          const bw = Math.max(40, sb.maxX - sb.minX);
          const bh = Math.max(40, sb.maxY - sb.minY);
          const diag = Math.hypot(bw, bh);
          const cx = (sb.minX + sb.maxX) * 0.5;
          const cy = (sb.minY + sb.maxY) * 0.5;
          const ang = ((lightSweep.angleDeg ?? 32) * Math.PI) / 180;
          const dx = Math.cos(ang), dy = Math.sin(ang);
          const bandW = diag * clamp(lightSweep.widthFrac ?? 0.24, 0.08, 0.65);
          const travel = lerp(-diag * 0.72 - bandW, diag * 0.72 + bandW, lightSweep.progress);
          const sx0 = cx + dx * (travel - bandW * 0.5);
          const sy0 = cy + dy * (travel - bandW * 0.5);
          const sx1 = cx + dx * (travel + bandW * 0.5);
          const sy1 = cy + dy * (travel + bandW * 0.5);
          const col = lightSweep.color || "#FFFFFF";
          const env = Math.sin(lightSweep.progress * Math.PI);
          const inten = clamp((lightSweep.intensity ?? 0.55) * env, 0, 1);
          if (inten > 0.005) {
            fxCtx.save();
            fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
            fxCtx.clearRect(0, 0, W, H);
            const lg = fxCtx.createLinearGradient(sx0, sy0, sx1, sy1);
            lg.addColorStop(0.0, rgbaStr(col, 0));
            lg.addColorStop(0.28, rgbaStr(col, 0.22 * inten));
            lg.addColorStop(0.50, rgbaStr(col, 0.95 * inten));
            lg.addColorStop(0.76, rgbaStr(col, 0.28 * inten));
            lg.addColorStop(1.0, rgbaStr(col, 0));
            fxCtx.fillStyle = lg;
            fxCtx.fillRect(0, 0, W, H);
            fxCtx.globalCompositeOperation = "destination-in";
            fxCtx.drawImage(maskCanvas, 0, 0, W, H);
            fxCtx.restore();

            ctx.save();
            ctx.globalCompositeOperation = "screen";
            ctx.globalAlpha = alpha * revealAlpha;
            ctx.drawImage(fxCanvas, 0, 0, W, H);
            ctx.restore();
          }
        }

        // 6e. Optional ownership tint-flash surge over interior silhouette
        if (flashHex && flashIntensity > 0.01) {
          rimCtx.save();
          rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
          rimCtx.clearRect(0, 0, W, H);
          rimCtx.globalCompositeOperation = "source-over";
          rimCtx.drawImage(maskCanvas, 0, 0, W, H);
          rimCtx.globalCompositeOperation = "source-in";
          rimCtx.fillStyle = flashHex;
          rimCtx.fillRect(0, 0, W, H);
          rimCtx.restore();
          ctx.save();
          ctx.globalCompositeOperation = "screen";
          ctx.globalAlpha = alpha * Math.min(0.85, flashIntensity * 0.72);
          ctx.drawImage(rimCanvas, 0, 0, W, H);
          ctx.restore();
        }
      }

      // End lifted country body coordinate space
      ctx.restore();
    }

    function drawStandardPolygon(geom, { fillHex, fillAlpha = 0.45, rimHex = "#F4F1EA", rimWidth = 2.2, bloomHex = null, bloomScale = 0.4, alpha = 1.0 } = {}) {
      if (alpha <= 0.005 || !geom) return;
      ctx.save();
      if (bloomHex && bloomScale > 0) {
        for (const [w, a] of [[rimWidth + 18 * bloomScale, 0.22], [rimWidth + 8 * bloomScale, 0.42]]) {
          ctx.beginPath();
          traceGeom(ctx, geom);
          ctx.strokeStyle = bloomHex;
          ctx.lineWidth = w;
          ctx.lineJoin = "round";
          ctx.globalAlpha = alpha * a;
          ctx.stroke();
        }
      }
      ctx.beginPath();
      traceGeom(ctx, geom);
      ctx.fillStyle = rgbaStr(fillHex, fillAlpha);
      ctx.globalAlpha = alpha;
      ctx.fill();
      if (rimHex && rimWidth > 0) {
        ctx.strokeStyle = rimHex;
        ctx.lineWidth = rimWidth;
        ctx.lineJoin = "round";
        ctx.stroke();
      }
      ctx.restore();
    }

    function drawPartialRoute(coords, progress, { color = "#FDE047", bloom = "#F5C542", core = "#FFFFFF", width = 8, dash = null, alpha = 1, cableCasing = false, pulseSpeed = 0, pulseCount = 3, pulseColor = "#FFFFFF", pulseGlow = "#FDE047", pulseTailFrac = 0.12, time = 0 } = {}) {
      if (progress <= 0.001 || alpha <= 0.005 || !coords || coords.length < 2) return;
      const clippedSegs = projectPolylineClipped(coords);
      if (!clippedSegs.length) return;
      const pts = clippedSegs.reduce((best, s) => (s.length >= best.length ? s : best), clippedSegs[0]);
      if (!pts || pts.length < 2) return;
      const lens = [0];
      let tot = 0;
      for (let i = 1; i < pts.length; i++) {
        tot += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
        lens.push(tot);
      }
      const target = tot * clamp(progress, 0, 1);
      const out = [pts[0]];
      for (let i = 1; i < pts.length; i++) {
        if (lens[i] <= target) out.push(pts[i]);
        else {
          const frac = (target - lens[i - 1]) / Math.max(1e-5, lens[i] - lens[i - 1]);
          out.push({ x: lerp(pts[i - 1].x, pts[i].x, frac), y: lerp(pts[i - 1].y, pts[i].y, frac) });
          break;
        }
      }
      if (out.length < 2) return;
      const trace = () => {
        ctx.beginPath();
        ctx.moveTo(out[0].x, out[0].y);
        for (let i = 1; i < out.length; i++) ctx.lineTo(out[i].x, out[i].y);
      };
      ctx.save();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      if (dash) ctx.setLineDash(dash);
      if (cableCasing && !dash) {
        trace(); ctx.strokeStyle = "#03161F"; ctx.globalAlpha = alpha * 0.82; ctx.lineWidth = width * 1.48; ctx.stroke();
      }
      if (bloom) {
        trace(); ctx.strokeStyle = bloom; ctx.globalAlpha = alpha * 0.28; ctx.lineWidth = width * 2.8; ctx.stroke();
        trace(); ctx.strokeStyle = bloom; ctx.globalAlpha = alpha * 0.56; ctx.lineWidth = width * 1.65; ctx.stroke();
      }
      trace(); ctx.strokeStyle = color; ctx.globalAlpha = alpha; ctx.lineWidth = width; ctx.stroke();
      if (core && !dash) {
        trace(); ctx.strokeStyle = core; ctx.globalAlpha = alpha * 0.88; ctx.lineWidth = Math.max(1.8, width * 0.36); ctx.stroke();
      }
      if (pulseSpeed > 0 && !dash && target > 24) {
        const outLens = [0];
        let outTot = 0;
        for (let i = 1; i < out.length; i++) {
          outTot += Math.hypot(out[i].x - out[i - 1].x, out[i].y - out[i - 1].y);
          outLens.push(outTot);
        }
        const sampleOut = (dist) => {
          const d = clamp(dist, 0, outTot);
          for (let i = 1; i < outLens.length; i++) {
            if (outLens[i] >= d || i === outLens.length - 1) {
              const span = Math.max(1e-5, outLens[i] - outLens[i - 1]);
              const f = clamp((d - outLens[i - 1]) / span, 0, 1);
              return { x: lerp(out[i - 1].x, out[i].x, f), y: lerp(out[i - 1].y, out[i].y, f) };
            }
          }
          return out[0];
        };
        ctx.setLineDash([]);
        const count = Math.max(1, Math.round(pulseCount));
        const tailDist = Math.max(18, outTot * pulseTailFrac);
        for (let k = 0; k < count; k++) {
          const phase = ((time * pulseSpeed + k / count) % 1 + 1) % 1;
          const headD = phase * (outTot + tailDist);
          const steps = 10;
          for (let s = 1; s <= steps; s++) {
            const d0 = headD - tailDist * (1 - (s - 1) / steps);
            const d1 = headD - tailDist * (1 - s / steps);
            if (d1 < 0 || d0 > outTot) continue;
            const p0 = sampleOut(d0);
            const p1 = sampleOut(d1);
            const frac = s / steps;
            ctx.strokeStyle = frac > 0.72 ? pulseColor : pulseGlow;
            ctx.globalAlpha = alpha * Math.pow(frac, 1.5) * 0.95;
            ctx.lineWidth = width * (0.45 + 0.85 * frac);
            ctx.beginPath();
            ctx.moveTo(p0.x, p0.y);
            ctx.lineTo(p1.x, p1.y);
            ctx.stroke();
          }
          if (headD >= 0 && headD <= outTot) {
            const hp = sampleOut(headD);
            const hg = ctx.createRadialGradient(hp.x, hp.y, 1, hp.x, hp.y, width * 1.9);
            hg.addColorStop(0, "rgba(255,255,255," + (0.95 * alpha).toFixed(2) + ")");
            hg.addColorStop(0.45, rgbaStr(pulseGlow, 0.72 * alpha));
            hg.addColorStop(1, "rgba(0,0,0,0)");
            ctx.fillStyle = hg;
            ctx.globalAlpha = 1;
            ctx.beginPath();
            ctx.arc(hp.x, hp.y, width * 1.9, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }
      ctx.restore();
    }

    // Local 2x2 MapLibre projection Jacobian (dScreen/dEast, dScreen/dSouth) for 3D surface-locked overlays.
    // Samples a micro-step at the active camera zoom so the probe point never crosses behind the WebGL near plane
    // during high-pitch dive-zooms (preventing inverted/mirrored text), then scales back to refZoom units.`;
}
