export function buildLayersRuntime({ allowWorldVoid }) {
  return `
    function drawLayers(layers, t) {
      ctx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      ctx.clearRect(0, 0, W, H);
      const zOf = (l) => {
        if (l && typeof l.z_index === "number") return l.z_index;
        if (l?.z_layer === "under_sprites") return -10;
        if (l?.z_layer === "over_sprites") return 10;
        return 0;
      };
      const ordered = (layers || [])
        .map((layer, idx) => ({ layer, idx, z: zOf(layer) }))
        .sort((a, b) => a.z - b.z || a.idx - b.idx)
        .map((x) => x.layer);
      for (const layer of ordered) {
        const tStart = layer.start_s ?? 0;
        const tEnd = layer.end_s ?? 1e9;
        if (t < tStart - 0.001 || t > tEnd + 0.001) continue;
        const tLoc = t - tStart;
        const fadeIn = layer.fade_in_s ? easeOutCubic(seg(t, tStart, tStart + layer.fade_in_s)) : 1;
        const fadeOut = layer.fade_out_s ? 1 - easeInCubic(seg(t, tEnd - layer.fade_out_s, tEnd)) : 1;
        const baseAlpha = clamp(fadeIn * fadeOut * (layer.opacity ?? 1), 0, 1);

        if (layer.type === "polygon") {
          const geom = resolveGeom(layer.geom_ref);
          let fillHex = layer.fill_hex || "#16A82A";
          let rimHex = layer.rim_hex || "#F4F1EA";
          let bloomHex = layer.bloom_hex || "#22C55E";
          let rimWidth = layer.rim_width ?? 3.0;
          let bloomScale = layer.bloom_scale ?? 1.0;
          let fillAlpha = layer.fill_alpha ?? 0.72;
          if (layer.morph) {
            const m = easeInOutCubic(seg(t, layer.morph.start_s, layer.morph.end_s));
            fillHex = mixHex(fillHex, layer.morph.fill_hex, m);
            if (layer.morph.rim_hex) rimHex = mixHex(rimHex, layer.morph.rim_hex, m);
            if (layer.morph.bloom_hex) bloomHex = mixHex(bloomHex, layer.morph.bloom_hex, m);
            if (layer.morph.rim_width != null) rimWidth = lerp(rimWidth, layer.morph.rim_width, m);
            if (layer.morph.bloom_scale != null) bloomScale = lerp(bloomScale, layer.morph.bloom_scale, m);
            if (layer.morph.fill_alpha != null) fillAlpha = lerp(fillAlpha, layer.morph.fill_alpha, m);
          }
          const borderReveal = layer.border_draw_s
            ? easeOutCubic(seg(t, tStart + (layer.border_delay_s ?? 0), tStart + (layer.border_delay_s ?? 0) + layer.border_draw_s))
            : 1.0;
          // Border trace: exterior rim traces in Web Mercator space, overlapping fill entry at 75%.
          const traceS = Number(layer.border_trace_s || 0);
          const traced = traceS > 0;
          const traceStartS = tStart + (layer.border_trace_delay_s ?? 0);
          const traceEndS = traceStartS + traceS;
          let traceProgress = 1.0;
          if (traced) {
            const u = seg(t, traceStartS, traceEndS);
            const ease = layer.border_trace_ease || "editorial_out";
            traceProgress = evalEase(ease, u);
            const traceHex = layer.border_trace_hex || rimHex;
            const traceWidth = layer.border_trace_width ?? rimWidth;
            const settleS = layer.border_trace_settle_s ?? 0;
            const settle = settleS > 0 ? easeInOutCubic(seg(t, traceEndS, traceEndS + settleS)) : (t >= traceEndS ? 1 : 0);
            if (traceHex !== rimHex) rimHex = mixHex(traceHex, rimHex, settle);
            rimWidth = lerp(traceWidth, rimWidth, settle);
          }
          const fillStartS = layer.fill_delay_s != null
            ? tStart + layer.fill_delay_s
            : (traced ? traceStartS + traceS * 0.75 : tStart);
          const fillDrawS = layer.fill_draw_s ?? (traced ? 0.45 : 0);
          const fillReveal = fillDrawS > 0
            ? editorialOut(seg(t, fillStartS, fillStartS + fillDrawS))
            : (!traced && layer.fill_delay_s == null ? 1.0 : (t >= fillStartS - 0.001 ? 1.0 : 0.0));
          const fillBloomOvershoot = layer.fill_bloom_overshoot != null
            ? clamp(Number(layer.fill_bloom_overshoot), 1.0, 1.6)
            : (traced || fillDrawS > 0 ? 1.18 : 1.0);
          const flagCode = layer.flag_fill ? String(layer.flag_fill).toLowerCase() : null;
          const flagImg = flagCode ? (window.__imgCache[BASE_URL + "/flags/" + flagCode + ".svg"] || null) : null;
          const fillRevealMode = (flagCode ? layer.flag_reveal : null) || layer.fill_reveal_mode || "fade";
          const blendMap = { normal: "source-over", multiply: "multiply", overlay: "overlay", "soft-light": "soft-light", screen: "screen" };
          const flagBlend = blendMap[layer.flag_blend || "normal"] || "source-over";
          const waveAmp = layer.flag_wave === true ? 0.22 : Number(layer.flag_wave) || 0;
          const waveWarp = layer.flag_wave_warp === false
            ? 0
            : (layer.flag_wave_warp === true
              ? 0.036
              : (layer.flag_wave_warp != null ? Number(layer.flag_wave_warp) : (waveAmp > 0 ? 0.036 : 0)));
          const waveGloss = layer.flag_gloss === false
            ? 0
            : (layer.flag_gloss === true
              ? 0.48
              : (layer.flag_gloss != null ? Number(layer.flag_gloss) : (waveAmp > 0 ? 0.48 : 0)));
          const flagWave = waveAmp > 0
            ? {
                amplitude: waveAmp,
                cycles: layer.flag_wave_cycles ?? 2.5,
                speed: layer.flag_wave_speed ?? 0.5,
                angleDeg: layer.flag_wave_angle_deg ?? 20,
                warp: waveWarp,
                gloss: waveGloss,
              }
            : null;
          const revealProgress = layer.reveal_duration_s
            ? easeInOutCubic(seg(t, tStart + (layer.reveal_delay_s ?? 0), tStart + (layer.reveal_delay_s ?? 0) + layer.reveal_duration_s))
            : 1.0;
          const perimeterProgress = layer.perimeter_draw_s
            ? easeOutCubic(seg(t, tStart + (layer.perimeter_delay_s ?? 0), tStart + (layer.perimeter_delay_s ?? 0) + layer.perimeter_draw_s))
            : 1.0;

          // Progressive world-space / contour hatch timing
          const hatchRevealMode = layer.hatch_reveal_mode || (Number(layer.hatch_draw_s || 0) > 0 ? "staggered_draw" : "fade");
          const hatchDrawS = layer.hatch_draw_s != null
            ? Math.max(0, Number(layer.hatch_draw_s) || 0)
            : (hatchRevealMode !== "fade" ? 0.75 : 0);
          const hatchStartS = fillStartS + (layer.hatch_delay_s != null ? Number(layer.hatch_delay_s) : (hatchDrawS > 0 ? 0.08 : 0));
          const hatchProgress = hatchDrawS > 0
            ? seg(t, hatchStartS, hatchStartS + hatchDrawS)
            : (t >= hatchStartS - 0.001 ? 1.0 : 0.0);

          // Optional 2.5D tactile lift & inner bevel
          const liftPx = Math.max(0, Number(layer.lift_px || 0));
          const liftStartS = fillStartS + (layer.lift_delay_s ?? 0);
          const liftDurS = layer.lift_duration_s ?? (liftPx > 0 ? 0.55 : 0);
          const liftProgress = liftDurS > 0
            ? evalEase(layer.lift_ease || "spring_tactile", seg(t, liftStartS, liftStartS + liftDurS))
            : 1.0;
          const bevelLight = layer.bevel_light === true ? 0.65 : clamp(Number(layer.bevel_light || 0), 0, 1);

          // Optional diagonal specular light sweep (opt-in)
          let lightSweep = null;
          if (layer.light_sweep) {
            const lsObj = typeof layer.light_sweep === "object" ? layer.light_sweep : {};
            const lsAt = lsObj.at_s != null
              ? Number(lsObj.at_s)
              : (fillStartS + fillDrawS + Number(lsObj.delay_s ?? 0.08));
            const lsDur = Math.max(0.08, Number(lsObj.duration_s ?? 0.65));
            if (t >= lsAt && t <= lsAt + lsDur) {
              lightSweep = {
                progress: easeInOutCubic(seg(t, lsAt, lsAt + lsDur)),
                angleDeg: lsObj.angle_deg ?? 32,
                color: lsObj.color || "#FFFFFF",
                intensity: lsObj.intensity ?? 0.55,
                widthFrac: lsObj.width_frac ?? 0.24,
              };
            }
          }

          // Optional travelling perimeter rim glint (opt-in)
          const rimGlint = layer.rim_glint === true
            ? { speed: 0.22, span_frac: 0.14, color: "#FFFFFF", intensity: 0.85 }
            : (layer.rim_glint && typeof layer.rim_glint === "object" ? layer.rim_glint : null);

          let flashHex = null;
          let flashIntensity = 0;
          for (const fl of layer.flashes || []) {
            const fd = fl.duration_s ?? 0.65;
            if (t >= fl.at_s && t <= fl.at_s + fd) {
              const u = clamp((t - fl.at_s) / fd, 0, 1);
              const val = Math.sin(u * Math.PI) * (fl.intensity ?? 1.0);
              if (val > flashIntensity) {
                flashIntensity = val;
                flashHex = fl.hex || fillHex;
              }
            }
          }
          if (
            layer.dissolve ||
            layer.dissolve_seams ||
            traced ||
            flagCode ||
            fillRevealMode !== "fade" ||
            fillDrawS > 0 ||
            layer.fill_delay_s != null ||
            Boolean(layer.border_draw_s) ||
            Boolean(layer.reveal_axis) ||
            Boolean(layer.outline_only) ||
            Boolean(layer.hatch) ||
            liftPx > 0 ||
            Boolean(layer.cast_shadow) ||
            bevelLight > 0 ||
            Boolean(layer.light_sweep) ||
            Boolean(rimGlint) ||
            Boolean(layer.texture_fill) ||
            (Array.isArray(layer.flashes) && layer.flashes.length > 0)
          ) {
            drawDissolvedPolygon(geom, {
              traced,
              traceProgress,
              traceEndS,
              traceHeads: layer.border_trace_heads ?? 2,
              traceStart: layer.border_trace_start || null,
              traceDir: layer.border_trace_dir || "cw",
              traceHeadGlow: Boolean(layer.border_trace_head_glow),
              flagImg,
              flagAlpha: layer.flag_alpha ?? 1.0,
              flagBlend,
              flagRotateDeg: layer.flag_rotate_deg ?? 0,
              flagFit: layer.flag_fit === "cover" ? "cover" : "stretch",
              fillRevealMode,
              fillRevealOrigin: layer.fill_reveal_origin || null,
              fillRevealOrganic: { roughness: layer.fill_reveal_roughness ?? 0.22, seed: layer.fill_reveal_seed ?? 1 },
              fillBloomOvershoot,
              flagWave,
              dissolveSeams: Boolean(layer.dissolve_seams),
              liftPx,
              liftProgress,
              castShadow: layer.cast_shadow ?? null,
              bevelLight,
              lightSweep,
              rimGlint,
              textureFill: layer.texture_fill || null,
              textureScale: layer.texture_scale ?? 1.0,
              geomKey: typeof layer.geom_ref === "string" ? layer.geom_ref : (layer.id || ""),
              time: t,
              fillHex,
              fillAlpha,
              rimHex,
              rimWidth,
              bloomHex,
              bloomScale,
              alpha: baseAlpha,
              borderReveal,
              fillReveal,
              revealAxis: layer.reveal_axis || null,
              revealProgress,
              revealBounds: layer.reveal_bounds || null,
              outlineOnly: Boolean(layer.outline_only),
              perimeterProgress,
              featherPx: layer.feather_px ?? 0,
              hatch: Boolean(layer.hatch),
              hatchColor: layer.hatch_color || "rgba(255,255,255,0.24)",
              hatchSpacing: layer.hatch_spacing ?? 18,
              hatchWidth: layer.hatch_width ?? 3.5,
              hatchSpace: layer.hatch_space || "world",
              hatchRevealMode,
              hatchProgress,
              hatchStagger: layer.hatch_stagger ?? 0.62,
              hatchDirection: layer.hatch_direction || "ltr",
              hatchAngleDeg: layer.hatch_angle_deg ?? 45,
              hatchEase: layer.hatch_ease || "editorial_out",
              hatchRefZoom: layer.hatch_ref_zoom ?? null,
              hatchCross: Boolean(layer.hatch_cross),
              hatchTipGlow: Boolean(layer.hatch_tip_glow),
              hatchGlowHex: layer.hatch_glow_hex || null,
              flashHex,
              flashIntensity,
            });
          } else {
            drawStandardPolygon(geom, { fillHex, fillAlpha, rimHex, rimWidth, bloomHex, bloomScale, alpha: baseAlpha });
          }
        } else if (layer.type === "route") {
          let coords = resolveGeom(layer.coords_ref) || layer.coords || [];
          if (layer.reverse) coords = [...coords].reverse();
          // Routes draw on by default (0.9 s); "instant: true" shows the whole line at once.
          const drawS = layer.instant === true ? 0 : (layer.draw_duration_s ?? 0.9);
          const drawFrom = tStart + (layer.draw_delay_s ?? 0);
          const drawEase = layer.draw_ease === "linear" ? (x) => x : layer.draw_ease === "in_out" ? easeInOutCubic : easeOutCubic;
          const prog = drawS > 0 ? drawEase(seg(t, drawFrom, drawFrom + drawS)) : (t >= drawFrom - 0.001 ? 1 : 0);
          // Optional world-space width: doubles per zoom level above "width_ref_zoom" (coupling 1).
          const baseWidth = layer.width || 8;
          const widthPx = scaledWidth(
            baseWidth, map.getZoom(), layer.width_ref_zoom ?? null, layer.width_coupling ?? 1.0,
            layer.width_min_scale ?? 0.4, layer.width_max_scale ?? 6
          );
          const dash = layer.dash ? layer.dash.map((d) => d * (widthPx / baseWidth)) : null;
          drawPartialRoute(coords, prog, {
            color: layer.color || layer.hex || "#FDE047",
            bloom: layer.bloom || "#F5C542",
            core: layer.core ?? "#FFFFFF",
            width: widthPx,
            dash,
            alpha: baseAlpha,
            cableCasing: Boolean(layer.cable_casing),
            pulseSpeed: Number(layer.pulse_speed || 0),
            pulseCount: Number(layer.pulse_count || 3),
            pulseColor: layer.pulse_color || "#FFFFFF",
            pulseGlow: layer.pulse_glow || layer.bloom || "#FDE047",
            pulseTailFrac: Number(layer.pulse_tail_frac || 0.12),
            time: tLoc,
          });
          if (layer.beacon_coord) {
            const bA = baseAlpha * easeOutCubic(seg(t, layer.beacon_start_s ?? tStart, (layer.beacon_start_s ?? tStart) + 0.7));
            const bp = bA > 0.01 ? projectPointSafe(layer.beacon_coord) : null;
            if (bp) {
              const bg = ctx.createRadialGradient(bp.x, bp.y, 10, bp.x, bp.y, 130);
              bg.addColorStop(0, "rgba(255,255,255," + (0.95 * bA).toFixed(2) + ")");
              bg.addColorStop(0.35, rgbaStr(layer.beacon_color || "#4ADE80", 0.78 * bA));
              bg.addColorStop(1, "rgba(34,197,94,0)");
              ctx.fillStyle = bg;
              ctx.beginPath(); ctx.arc(bp.x, bp.y, 130, 0, Math.PI * 2); ctx.fill();
            }
          }
        } else if (layer.type === "glow_label") {
          const preset = layer.carto_role ? (CARTO_TYPO_PRESETS[layer.carto_role] || {}) : {};
          const space = layer.space || (layer.ref_zoom != null ? "map_plane" : "world_billboard");
          const useComicBounce = layer.register === "comic" || layer.pop_bounce === true;
          let sc = layer.pop_scale
            ? lerp(
                useComicBounce ? 0.86 : 0.94,
                1.0,
                (useComicBounce ? easeOutBack : easeOutExpo)(seg(t, tStart, tStart + (layer.pop_duration_s ?? 0.30)))
              )
            : 1.0;
          if (layer.exit_scale_down_s && t > tEnd - layer.exit_scale_down_s) {
            sc *= 1 - easeInCubic(seg(t, tEnd - layer.exit_scale_down_s, tEnd));
          }
          let yFly = 0;
          if (layer.fly_through) {
            const enterP = easeOutExpo(seg(t, tStart, tStart + 0.52));
            const exitP = easeInExpo(seg(t, tEnd - 0.42, tEnd));
            sc = lerp(5.2, 1.0, enterP) * lerp(1.0, 4.8, exitP);
            yFly = lerp(320, 0, enterP) - lerp(0, 220, exitP);
          }
          let displayText = String(layer.text ?? "");
          if (preset.uppercase && !layer.preserve_case) {
            displayText = displayText.toUpperCase();
          }
          let tabularDigits = Boolean(layer.tabular_digits ?? preset.tabularDigits ?? false);
          let typewriterChars = null;
          if (layer.count_to != null) {
            const cStart = tStart + (layer.count_delay_s ?? 0);
            const cDur = layer.count_duration_s ?? 0.85;
            // Critically damped expo-out avoids overshooting numeric metrics past ground truth.
            const cu = easeOutExpo(seg(t, cStart, cStart + cDur));
            const val = Math.round(lerp(layer.count_from ?? 0, layer.count_to, cu));
            displayText = (layer.count_prefix || "") + val.toLocaleString(layer.count_locale || "en-US") + (layer.count_suffix || "");
            tabularDigits = true;
          } else if (layer.typewriter_s) {
            const twStart = tStart + (layer.typewriter_delay_s ?? 0);
            const twU = clamp(seg(t, twStart, twStart + layer.typewriter_s), 0, 1);
            typewriterChars = Math.max(0, Math.round(displayText.length * twU));
          }
          let curCoord = layer.coord;
          if (curCoord && layer.move_to_coord && layer.move_start_s != null) {
            const mu = easeInOutCubic(seg(t, layer.move_start_s, layer.move_start_s + (layer.move_duration_s ?? 0.6)));
            curCoord = [
              lerp(curCoord[0], layer.move_to_coord[0], mu),
              lerp(curCoord[1], layer.move_to_coord[1], mu),
            ];
          }
          let subPill = null;
          if (layer.sub_pill) {
            const spStart = layer.sub_pill.start_s ?? (tStart + (layer.sub_pill.delay_s ?? 0));
            const spEnd = layer.sub_pill.end_s ?? tEnd;
            if (t >= spStart && t <= spEnd) {
              const spEase = useComicBounce ? easeOutBack : easeOutExpo;
              const spIn = lerp(useComicBounce ? 0.82 : 0.94, 1.0, spEase(seg(t, spStart, spStart + (layer.sub_pill.pop_s ?? 0.26))));
              const spOut = layer.sub_pill.fade_out_s ? 1 - seg(t, spEnd - layer.sub_pill.fade_out_s, spEnd) : 1;
              subPill = {
                ...layer.sub_pill,
                alpha: clamp(spOut, 0, 1),
                scale: clamp(spIn, 0, useComicBounce ? 1.12 : 1.0),
              };
            }
          }
          const angDeg = layer.angle_end != null
            ? lerp(layer.angle_start || 0, layer.angle_end, seg(t, tStart, tEnd))
            : (layer.angle || 0);
          const angRad = angDeg * Math.PI / 180;
          const baseFont = layer.font_px || 64;
          let letterSpacing = layer.letter_spacing ?? (preset.letterSpacingEm != null ? (preset.letterSpacingEm + "em") : 0);
          if (layer.tracking_from_em != null && layer.tracking_to_em != null) {
            const trU = easeOutExpo(seg(t, tStart, tStart + (layer.tracking_duration_s ?? 0.9)));
            letterSpacing = lerp(layer.tracking_from_em, layer.tracking_to_em, trU).toFixed(4) + "em";
          }
          const hasExplicitGlow = layer.glow_hex != null || (layer.glow_strength != null && layer.glow_strength !== "none");
          const strokeMult = preset.strokeMult ?? 0;
          const defaultHaloW = strokeMult > 0 ? Math.max(1.2, Math.min(3.2, baseFont * strokeMult)) : 0;
          const slideX = layer.slide_from_x_px != null || layer.slide_to_x_px != null
            ? lerp(layer.slide_from_x_px ?? 0, layer.slide_to_x_px ?? 0, easeOutCubic(seg(t, tStart, tEnd)))
            : 0;
          const textOpts = {
            fill: layer.fill || preset.fill || "#F4F1EA",
            glowHex: hasExplicitGlow ? (layer.glow_hex ?? "#F5C542") : null,
            glowStrength: layer.glow_strength ?? (layer.glow_hex ? "subtle" : (preset.glowStrength ?? "none")),
            angle: angRad,
            scale: sc,
            alpha: baseAlpha,
            family: layer.family || preset.family || "Montserrat",
            weight: layer.weight || preset.weight || 800,
            fontStyle: layer.font_style || preset.fontStyle || "normal",
            letterSpacing,
            strokeHex: layer.stroke_hex !== undefined ? layer.stroke_hex : (preset.strokeHex ?? null),
            strokeWidth: layer.stroke_width !== undefined ? layer.stroke_width : defaultHaloW,
            lineHeightMult: layer.line_height_mult ?? 1.08,
            tabularDigits,
            typewriterChars,
            typewriterLeadHex: layer.typewriter_lead_hex || null,
            subPill,
            shadowBlurMult: layer.shadow_blur_mult ?? preset.shadowBlurMult ?? 0.22,
            shadowAlpha: layer.shadow_alpha ?? preset.shadowAlpha ?? 0.46,
            shadowOffsetYMult: layer.shadow_offset_y_mult ?? preset.shadowOffsetYMult ?? 0.055,
            dividerRule: Boolean(layer.divider_rule ?? preset.dividerRule ?? false),
            dividerColor: layer.divider_color ?? null,
          };
          if (space === "map_plane" && curCoord && !layer.fly_through) {
            const m = getMapPlaneMatrix(curCoord, layer.ref_zoom ?? map.getZoom());
            const mag = Math.hypot(m.a, m.b);
            const minSc = layer.min_scale ?? 0.35;
            const maxSc = layer.max_scale ?? 3.2;
            const clampFactor = mag > 1e-4 ? clamp(mag, minSc, maxSc) / mag : 1.0;
            ctx.save();
            ctx.transform(m.a * clampFactor, m.b * clampFactor, m.c * clampFactor, m.d * clampFactor, m.e, m.f);
            drawGlowingText(displayText, (layer.dx || 0) + slideX, layer.dy || 0, baseFont, textOpts);
            ctx.restore();
          } else if (curCoord) {
            const pt = projectPointSafe(curCoord);
            if (pt) {
              if (layer.ref_zoom != null) {
                const coupling = layer.scale_coupling ?? 0.45;
                const zScale = Math.pow(2, (map.getZoom() - layer.ref_zoom) * coupling);
                sc *= clamp(zScale, layer.min_scale ?? 0.45, layer.max_scale ?? 2.4);
                textOpts.scale = sc;
              }
              drawGlowingText(displayText, pt.x + (layer.dx || 0) + slideX, pt.y + (layer.dy || 0) + yFly, baseFont, textOpts);
            }
          } else if (layer.x_pct != null || layer.y_pct != null) {
            drawGlowingText(
              displayText,
              W * (layer.x_pct ?? 0.5) + (layer.dx || 0) + slideX,
              H * (layer.y_pct ?? 0.25) + (layer.dy || 0) + yFly,
              baseFont,
              textOpts
            );
          }
        } else if (layer.type === "curved_label") {
          const preset = CARTO_TYPO_PRESETS[layer.carto_role || "water"] || CARTO_TYPO_PRESETS.water;
          const rawCoords = resolveGeom(layer.coords_ref) || layer.coords || [];
          const segs = projectPolylineClipped(rawCoords);
          if (segs.length && segs[0].length >= 2) {
            const fPx = layer.font_px || 42;
            const revealP = layer.reveal_s ? easeOutExpo(seg(t, tStart, tStart + layer.reveal_s)) : 1.0;
            let txt = String(layer.text ?? "");
            if (preset.uppercase && !layer.preserve_case) txt = txt.toUpperCase();
            const lsEm = layer.letter_spacing_em ?? preset.letterSpacingEm ?? 0.08;
            drawCurvedMapLabel(segs[0], txt, fPx, {
              fill: layer.fill || preset.fill || "#A8D8FF",
              family: layer.family || preset.family || "Lora",
              weight: layer.weight || preset.weight || 600,
              fontStyle: layer.font_style || preset.fontStyle || "italic",
              letterSpacingPx: lsEm * fPx,
              strokeHex: layer.stroke_hex ?? preset.strokeHex ?? "rgba(3,22,31,0.78)",
              strokeWidth: layer.stroke_width ?? Math.max(1.6, Math.min(3.5, fPx * (preset.strokeMult ?? 0.042))),
              alpha: baseAlpha,
              offsetPx: layer.offset_px ?? 0,
              revealProgress: revealP,
              maxCharAngleDeg: layer.max_char_angle_deg ?? 22,
            });
          }
        } else if (layer.type === "crimson_x") {
          const pt = projectPointSafe(layer.coord);
          if (pt) {
            const slash = slashCrossProgress(tLoc, {
              slashDurS: layer.slash_duration_s ?? 0.22,
              gapS: layer.gap_s ?? 0.11,
              impactDurS: layer.impact_duration_s ?? 0.36,
            });
            const szBase = lerp(layer.size_start || 84, layer.size_end || 118, seg(t, tStart, tEnd));
            const sz = szBase * (1 + slash.impactPulse * 0.12);
            drawCrimsonX(pt.x + (layer.dx || 0), pt.y + (layer.dy || 0), sz, baseAlpha, {
              stroke1: slash.stroke1,
              stroke2: slash.stroke2,
              impactPulse: slash.impactPulse,
              shockwave: layer.shockwave !== false,
              strokeHex: layer.stroke_hex || "#DC2626",
              glowHex: layer.glow_hex || "#EF4444",
              coreHex: layer.core_hex || "#FFFFFF",
              strikeAngleDeg: layer.strike_angle_deg || 0,
            });
          }
        } else if (layer.type === "skull") {
          const pt = projectPointSafe(layer.coord);
          if (pt) {
            const pop = easeOutBack(seg(t, tStart, tStart + 0.32));
            const refZoom = layer.ref_zoom ?? 7.3;
            const zoomScale = Math.pow(2, map.getZoom() - refZoom);
            const sz = (layer.size_start || 155) * zoomScale * clamp(pop, 0, 1.15);
            const rotRad = -map.getBearing() * Math.PI / 180;
            const pitchScale = Math.cos((map.getPitch() || 0) * Math.PI / 180);
            drawSkull(pt.x, pt.y + (layer.dy || 0), sz, baseAlpha, { rotRad, pitchScale });
          }
        } else if (layer.type === "endpoint_dots") {
          const pulse = 1 + 0.16 * Math.sin(t * 14);
          const dr = lerp(layer.r_start || 12, layer.r_end || 28, seg(t, tStart, tEnd)) * pulse;
          for (const c of layer.coords || []) {
            const pt = projectPointSafe(c);
            if (!pt) continue;
            const g = ctx.createRadialGradient(pt.x, pt.y, dr * 0.2, pt.x, pt.y, dr * 2.2);
            g.addColorStop(0, "rgba(255,65,65,0.96)");
            g.addColorStop(0.5, "rgba(220,38,38,0.56)");
            g.addColorStop(1, "rgba(220,38,38,0)");
            ctx.save();
            ctx.globalAlpha = baseAlpha;
            ctx.fillStyle = g; ctx.beginPath(); ctx.arc(pt.x, pt.y, dr * 2.2, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = "#EF4444"; ctx.beginPath(); ctx.arc(pt.x, pt.y, dr * 0.72, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = "#FFFFFF"; ctx.beginPath(); ctx.arc(pt.x, pt.y, dr * 0.28, 0, Math.PI * 2); ctx.fill();
            ctx.restore();
          }
        } else if (layer.type === "measurement_arrow") {
          const p1 = projectPointSafe(layer.from);
          const p2 = projectPointSafe(layer.to);
          if (p1 && p2) {
            const arrP = easeOutExpo(seg(t, tStart, tStart + (layer.draw_s || 0.75)));
            const val = Math.round(lerp(layer.count_from ?? 0, layer.count_to ?? 160, easeOutCubic(seg(t, tStart, tStart + (layer.count_s || 1.1)))));
            drawDoubleArrow(p1, p2, val + " " + (layer.unit || "km"), arrP, baseAlpha);
          }
        } else if (layer.type === "weather_clouds_rain") {
          const pt = projectPointSafe(layer.coord);
          if (pt) {
            const sc = lerp(layer.scale_start || 0.85, layer.scale_end || 1.22, easeOutCubic(seg(t, tStart, tStart + 0.8)));
            drawWeatherCloudsRain(pt.x, pt.y + (layer.dy || -30), sc, baseAlpha, tLoc);
          }
        } else if (layer.type === "migrant_swarm") {
          const count = layer.count || 28;
          const [sLng0, sLat0, sLng1, sLat1] = layer.from_box;
          const [eLng0, eLat0, eLng1, eLat1] = layer.to_box;
          const lossStart = layer.loss_start_s ?? (tStart + 2.4);
          for (let i = 0; i < count; i++) {
            const sd1 = ((i * 197 + 31) % 100) / 100;
            const sd2 = ((i * 313 + 17) % 100) / 100;
            const delay = (i % 7) * 0.2;
            const mt = tLoc - delay;
            if (mt < 0) continue;
            const prog = clamp(mt * (0.14 + (i % 4) * 0.024), 0, 1.15);
            const pt = projectPointSafe([
              lerp(lerp(sLng0, sLng1, sd1), lerp(eLng0, eLng1, sd1), prog),
              lerp(lerp(sLat0, sLat1, sd2), lerp(eLat0, eLat1, sd2), prog),
            ]);
            if (!pt) continue;
            let dotA = baseAlpha * Math.min(1, mt * 3);
            let isRed = false;
            const isLost = i % 4 === 1;
            const lostAt = lossStart + (i % 6) * 0.22;
            if (isLost && t >= lostAt) {
              isRed = true;
              dotA *= 1 - seg(t, lostAt + 0.15, lostAt + 0.85);
            }
            if (dotA <= 0.01) continue;
            ctx.save();
            ctx.globalAlpha = dotA;
            const g = ctx.createRadialGradient(pt.x, pt.y, 2, pt.x, pt.y, 26);
            g.addColorStop(0, "#FFFFFF");
            g.addColorStop(0.36, isRed ? "rgba(239,68,68,0.88)" : "rgba(92,225,255,0.88)");
            g.addColorStop(1, "rgba(0,0,0,0)");
            ctx.fillStyle = g; ctx.beginPath(); ctx.arc(pt.x, pt.y, 26, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = isRed ? "#EF4444" : "#38BDF8"; ctx.beginPath(); ctx.arc(pt.x, pt.y, 9.5, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = "#FFFFFF"; ctx.beginPath(); ctx.arc(pt.x, pt.y, 4.2, 0, Math.PI * 2); ctx.fill();
            ctx.restore();
          }
        } else if (layer.type === "wildlife_pins") {
          for (const item of layer.items || []) {
            if (t < item.start_s) continue;
            const pop = easeOutBack(seg(t, item.start_s, item.start_s + 0.3));
            const pt = projectPointSafe(item.coord);
            if (pt) drawTeardropPin(pt.x, pt.y, (layer.radius || 76) * clamp(pop, 0, 1.15), item.kind, baseAlpha);
          }
        } else if (layer.type === "prohibition_badge") {
          const pt = projectPointSafe(layer.coord);
          if (pt) {
            const inP = easeOutExpo(seg(t, tStart, tStart + 0.65));
            const outP = easeInCubic(seg(t, tEnd - 0.95, tEnd));
            const rad = lerp(layer.r_enter || 340, layer.r_hold || 150, inP) * lerp(1.0, 2.8, outP);
            const cy = lerp(220, pt.y - 20, inP) - outP * 380;
            drawNoPoliceBadge(pt.x, cy, rad, baseAlpha);
          }
        } else if (layer.type === "radar_rings") {
          for (const hub of layer.hubs || []) {
            if (t < hub.start_s) continue;
            const age = t - hub.start_s;
            const pt = projectPointSafe(hub.coord);
            if (!pt) continue;
            ctx.save();
            ctx.globalAlpha = baseAlpha;
            ctx.fillStyle = hub.color || "#DC2626";
            ctx.beginPath(); ctx.arc(pt.x, pt.y, 16, 0, Math.PI * 2); ctx.fill();
            for (let k = 0; k < 3; k++) {
              const ph = (age * 0.85 + k / 3) % 1;
              const rr = lerp(18, hub.max_r || 175, ph);
              ctx.strokeStyle = rgbaStr(hub.color || "#EF4444", (1 - ph) * 0.88);
              ctx.lineWidth = lerp(8.5, 2.5, ph);
              ctx.beginPath(); ctx.arc(pt.x, pt.y, rr, 0, Math.PI * 2); ctx.stroke();
            }
            ctx.restore();
          }
        } else if (layer.type === "vignette_grade") {
          const pt = (layer.coord ? projectPointSafe(layer.coord) : null) || { x: W * 0.5, y: H * 0.48 };
          ctx.save();
          const vg = ctx.createRadialGradient(pt.x, pt.y, layer.inner_r || 130, pt.x, pt.y, layer.outer_r || 1050);
          vg.addColorStop(0, "rgba(4,10,14," + (0.22 * baseAlpha).toFixed(3) + ")");
          vg.addColorStop(0.5, "rgba(4,9,12," + (0.76 * baseAlpha).toFixed(3) + ")");
          vg.addColorStop(1, "rgba(2,5,8," + (0.95 * baseAlpha).toFixed(3) + ")");
          ctx.fillStyle = vg;
          ctx.fillRect(0, 0, W, H);
          ctx.restore();
          applyMicroDither(ctx, 0.025 * baseAlpha);
        } else if (layer.type === "focus_spotlight") {
          const refs = Array.isArray(layer.geom_refs)
            ? layer.geom_refs
            : (layer.geom_ref ? [layer.geom_ref] : []);
          const geoms = refs.map((r) => resolveGeom(r)).filter(Boolean);
          drawFocusSpotlight(geoms, {
            dimAlpha: layer.dim_alpha ?? 0.58,
            dimHex: layer.dim_hex || "#04101A",
            featherPx: layer.feather_px ?? 36,
            rimGlowHex: layer.rim_glow_hex || null,
            rimGlowAlpha: layer.rim_glow_alpha ?? 0.25,
            alpha: baseAlpha,
          });
        } else if (layer.type === "color_flash") {
          ctx.save();
          ctx.fillStyle = rgbaStr(layer.hex || "#D8A8F5", (layer.max_alpha ?? 0.82) * baseAlpha);
          ctx.fillRect(0, 0, W, H);
          ctx.restore();
        } else if (layer.type === "jungle_emoji_ending") {
          drawJungleEmojiEnding(tLoc, layer.gag_at_s ?? 1.12);
        } else if (layer.type === "equator_laser") {
          const lat = layer.lat ?? 0.0;
          const lngMin = layer.lng_min ?? 90.0;
          const lngMax = layer.lng_max ?? 130.0;
          const steps = 40;
          const coords = [];
          for (let i = 0; i <= steps; i++) coords.push([lerp(lngMin, lngMax, i / steps), lat]);
          const prog = layer.draw_duration_s ? easeOutExpo(seg(t, tStart, tStart + layer.draw_duration_s)) : 1;
          drawPartialRoute(coords, prog, {
            color: layer.color || "#F5C542",
            bloom: layer.bloom || "#F5C542",
            core: layer.core ?? "#FFFFFF",
            width: layer.width || 6,
            dash: layer.dash || null,
            alpha: baseAlpha,
          });
          if (layer.label && prog > 0.35) {
            const lp = projectPointSafe([layer.label_lng ?? ((lngMin + lngMax) * 0.5), lat]);
            if (lp) drawGlowingText(layer.label, lp.x + (layer.dx || 0), lp.y + (layer.dy || -34), layer.font_px || 36, {
              fill: "#FFFBEB",
              glowHex: layer.bloom || "#F5C542",
              glowStrength: "luminous",
              alpha: baseAlpha * easeOutCubic(seg(prog, 0.35, 0.7)),
            });
          }
        } else if (layer.type === "year_badge") {
          const x = W * (layer.x_pct ?? 0.5);
          const y = H * (layer.y_pct ?? 0.21);
          const sc = lerp(0.94, 1.0, easeOutExpo(seg(t, tStart, tStart + 0.30)));
          const fPx = layer.font_px || 96;
          drawGlowingText(String(layer.text || "1928"), x, y, fPx, {
            fill: layer.fill || "#F4F1EA",
            glowHex: layer.glow_hex || "#F5C542",
            glowStrength: layer.glow_strength || "subtle",
            strokeHex: "rgba(3,22,31,0.84)",
            strokeWidth: Math.max(2.2, fPx * 0.04),
            family: layer.family || "IBM Plex Mono",
            weight: layer.weight || 700,
            tabularDigits: true,
            scale: sc,
            alpha: baseAlpha,
          });
          if (layer.subtitle) {
            drawGlowingText(String(layer.subtitle), x, y + 66, 30, {
              fill: "#DCE8F5",
              strokeHex: "rgba(3,22,31,0.84)",
              strokeWidth: 1.8,
              family: layer.subtitle_family || "Inter",
              weight: 600,
              letterSpacing: "0.06em",
              alpha: baseAlpha * 0.95,
            });
          }
        } else if (layer.type === "void_wipe") {
          const dir = layer.direction || "rtl";
          const wipeS = layer.wipe_s ?? tStart;
          const wipeDur = layer.wipe_duration_s ?? 0.28;
          const unwipeS = layer.unwipe_s ?? (tEnd - 0.35);
          const unwipeDur = layer.unwipe_duration_s ?? 0.32;
          const pIn = easeInOutCubic(seg(t, wipeS, wipeS + wipeDur));
          const pOut = layer.unwipe_s != null ? easeInOutCubic(seg(t, unwipeS, unwipeS + unwipeDur)) : 0;
          const voidAlpha = (layer.void_alpha ?? 0.88) * baseAlpha * (1 - pOut);
          if (voidAlpha > 0.005 && pIn > 0.001) {
            ctx.save();
            ctx.fillStyle = rgbaStr(layer.void_hex || "#0C0E11", voidAlpha);
            let barX = -100;
            if (dir === "rtl") {
              const x0 = lerp(W, 0, pIn);
              ctx.fillRect(x0, 0, W - x0, H);
              barX = x0;
            } else {
              const w0 = lerp(0, W, pIn);
              ctx.fillRect(0, 0, w0, H);
              barX = w0;
            }
            if (pIn > 0.01 && pIn < 0.995) {
              ctx.save();
              ctx.shadowColor = layer.bar_glow || "#FFFFFF";
              ctx.shadowBlur = 28;
              ctx.fillStyle = "#FFFFFF";
              ctx.globalAlpha = baseAlpha * Math.sin(pIn * Math.PI);
              ctx.fillRect(barX - 4, 0, 8, H);
              ctx.restore();
            }
            ctx.restore();
          }
        } else if (layer.type === "flag_pin") {
          const code = String(layer.code || "es").toLowerCase();
          const img = window.__imgCache[BASE_URL + "/flags/" + code + ".svg"];
          if (img) {
            const pop = easeOutBack(seg(t, tStart, tStart + 0.30));
            const popSc = clamp(pop, 0, 1.15);
            const space = layer.space || "world_billboard";
            const fwBase = layer.width_px || 136;
            const fhBase = fwBase * (layer.aspect ?? 0.667);
            ctx.save();
            ctx.globalAlpha = baseAlpha;
            if (space === "map_plane" && layer.coord) {
              const m = getMapPlaneMatrix(layer.coord, layer.ref_zoom ?? map.getZoom());
              const mag = Math.hypot(m.a, m.b);
              const cf = mag > 1e-4 ? clamp(mag, layer.min_scale ?? 0.35, layer.max_scale ?? 2.8) / mag : 1.0;
              ctx.transform(m.a * cf, m.b * cf, m.c * cf, m.d * cf, m.e, m.f);
              ctx.translate(layer.dx || 0, layer.dy || 0);
              if (layer.angle) ctx.rotate((layer.angle * Math.PI) / 180);
              ctx.scale(popSc, popSc);
            } else {
              const pt = projectPointSafe(layer.coord);
              if (!pt) { ctx.restore(); continue; }
              const coupling = layer.scale_coupling ?? 0.45;
              const zoomScale = layer.ref_zoom != null
                ? clamp(Math.pow(2, (map.getZoom() - layer.ref_zoom) * coupling), layer.min_scale ?? 0.45, layer.max_scale ?? 2.4)
                : 1.0;
              ctx.translate(pt.x + (layer.dx || 0), pt.y + (layer.dy || 0));
              if (layer.angle) ctx.rotate((layer.angle * Math.PI) / 180);
              ctx.scale(zoomScale * popSc, zoomScale * popSc);
            }
            const fx = -fwBase * 0.5;
            const fy = -fhBase * 0.5;
            ctx.shadowColor = "rgba(0,0,0,0.62)";
            ctx.shadowBlur = 18;
            ctx.shadowOffsetY = 6;
            if (layer.wave === true) {
              const slices = 18;
              const sw = img.width / slices;
              const dw = fwBase / slices;
              for (let i = 0; i < slices; i++) {
                const ph = (i / slices) * Math.PI * 2.2 - tLoc * 5.2;
                const dyW = Math.sin(ph) * (fhBase * 0.055) * (0.2 + 0.8 * (i / slices));
                ctx.drawImage(img, i * sw, 0, sw + 0.5, img.height, fx + i * dw, fy + dyW, dw + 0.8, fhBase);
              }
            } else {
              const bw = layer.border_px ?? 4;
              ctx.fillStyle = layer.border_color || "#FFFFFF";
              ctx.fillRect(fx - bw, fy - bw, fwBase + bw * 2, fhBase + bw * 2);
              ctx.shadowBlur = 0;
              ctx.drawImage(img, fx, fy, fwBase, fhBase);
            }
            ctx.restore();
          }
        } else if (layer.type === "dashed_distance") {
          const dSegs = projectPolylineClipped([layer.from, layer.to]);
          if (dSegs.length && dSegs[0].length >= 2) {
            const p1 = dSegs[0][0];
            const p2 = dSegs[0][dSegs[0].length - 1];
          const prog = layer.draw_s ? easeOutCubic(seg(t, tStart, tStart + layer.draw_s)) : 1.0;
          const qx = lerp(p1.x, p2.x, prog);
          const qy = lerp(p1.y, p2.y, prog);
          const col = layer.color || "#FDE047";
          ctx.save();
          ctx.globalAlpha = baseAlpha;
          ctx.lineCap = "butt";
          ctx.setLineDash(layer.dash || [16, 12]);
          ctx.strokeStyle = col;
          ctx.shadowColor = "rgba(0,0,0,0.75)";
          ctx.shadowBlur = 10;
          ctx.lineWidth = layer.width || 7;
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(qx, qy);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.restore();
          const labelAlpha = baseAlpha * easeOutCubic(seg(prog, 0.25, 0.7));
          const primaryTxt = layer.primary || layer.metric_label;
          const secondaryTxt = layer.secondary || layer.imperial_label;
          if (labelAlpha > 0.01 && primaryTxt) {
            const mx = (p1.x + p2.x) * 0.5 + (layer.dx || 0);
            const my = (p1.y + p2.y) * 0.5 + (layer.dy || 0);
            const fPx = layer.font_px || 54;
            let angRad = ((layer.angle_deg ?? 0) * Math.PI) / 180;
            if (layer.align_to_line) {
              angRad = Math.atan2(p2.y - p1.y, p2.x - p1.x);
              if (angRad > Math.PI / 2) angRad -= Math.PI;
              if (angRad < -Math.PI / 2) angRad += Math.PI;
            }
            const lblCol = layer.label_color || col;
            ctx.save();
            ctx.translate(mx, my);
            if (angRad) ctx.rotate(angRad);
            drawGlowingText(String(primaryTxt), 0, -fPx * 0.25, fPx, {
              fill: lblCol,
              strokeHex: "rgba(3,22,31,0.85)",
              strokeWidth: Math.max(2.0, fPx * 0.045),
              glowStrength: "none",
              alpha: labelAlpha,
              family: layer.family || "Barlow Condensed",
              weight: layer.weight || 800,
              tabularDigits: true,
            });
            if (secondaryTxt) {
              const secPx = Math.round(fPx * 0.56);
              drawGlowingText(String(secondaryTxt), 0, fPx * 0.55, secPx, {
                fill: lblCol,
                strokeHex: "rgba(3,22,31,0.85)",
                strokeWidth: Math.max(1.6, secPx * 0.05),
                glowStrength: "none",
                alpha: labelAlpha * 0.96,
                family: layer.secondary_family || "IBM Plex Mono",
                weight: 700,
                tabularDigits: true,
              });
            }
            ctx.restore();
          }
          }
        } else if (layer.type === "curved_arc_arrow") {
          const aSegs = projectPolylineClipped([layer.from, layer.to]);
          const prog = layer.draw_s ? easeOutCubic(seg(t, tStart, tStart + layer.draw_s)) : 1.0;
          if (prog > 0.01 && aSegs.length && aSegs[0].length >= 2) {
            const p1 = aSegs[0][0];
            const p2 = aSegs[0][aSegs[0].length - 1];
            const dx = p2.x - p1.x, dy = p2.y - p1.y;
            const len = Math.max(1, Math.hypot(dx, dy));
            const nx = -dy / len, ny = dx / len;
            const bend = layer.arc_offset_px != null ? layer.arc_offset_px : len * (layer.arc_ratio ?? 0.26);
            const cx = (p1.x + p2.x) * 0.5 + nx * bend;
            const cy = (p1.y + p2.y) * 0.5 + ny * bend;
            const bez = sampleQuadraticBezierTo(p1, { x: cx, y: cy }, p2, prog, 40);
            const pts = bez.points;
            const col = layer.color || "#EF4444";
            const bloom = layer.bloom || col;
            const w = layer.width || 9;
            ctx.save();
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            const traceArc = () => {
              ctx.beginPath();
              ctx.moveTo(pts[0].x, pts[0].y);
              for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
            };
            ctx.strokeStyle = bloom; ctx.globalAlpha = baseAlpha * 0.38; ctx.lineWidth = w * 2.4; traceArc(); ctx.stroke();
            ctx.strokeStyle = col; ctx.globalAlpha = baseAlpha; ctx.lineWidth = w; traceArc(); ctx.stroke();
            // Arrowhead at exact Bezier tip using analytic tangent
            const tip = bez.tip;
            const ang = bez.angleRad;
            const ah = Math.max(20, w * 2.6);
            ctx.translate(tip.x, tip.y);
            ctx.rotate(ang);
            ctx.fillStyle = col;
            ctx.beginPath();
            ctx.moveTo(ah * 0.35, 0);
            ctx.lineTo(-ah, -ah * 0.58);
            ctx.lineTo(-ah * 0.65, 0);
            ctx.lineTo(-ah, ah * 0.58);
            ctx.closePath();
            ctx.fill();
            ctx.restore();
          }
        } else if (layer.type === "ghost_overlay") {
          const geom = resolveGeom(layer.geom_ref);
          if (geom) {
            const slideP = layer.slide_s ? easeOutCubic(seg(t, tStart, tStart + layer.slide_s)) : 1.0;
            const dxSlide = lerp(layer.slide_from_dx ?? -420, layer.dx ?? 0, slideP);
            const dySlide = lerp(layer.slide_from_dy ?? 0, layer.dy ?? 0, slideP);
            ctx.save();
            ctx.translate(dxSlide, dySlide);
            drawDissolvedPolygon(geom, {
              fillHex: layer.fill_hex || "#38BDF8",
              fillAlpha: layer.fill_alpha ?? 0.42,
              rimHex: layer.rim_hex || "#BAE6FD",
              rimWidth: layer.rim_width ?? 2.8,
              bloomHex: layer.bloom_hex || "#38BDF8",
              bloomScale: layer.bloom_scale ?? 0.85,
              alpha: baseAlpha,
            });
            if (layer.label && layer.label_coord) {
              const lp = projectPointSafe(layer.label_coord);
              if (lp) drawGlowingText(String(layer.label), lp.x + (layer.label_dx || 0), lp.y + (layer.label_dy || -90), layer.font_px || 54, {
                fill: "#E0F2FE",
                glowHex: layer.bloom_hex || "#38BDF8",
                glowStrength: "luminous",
                alpha: baseAlpha * slideP,
                family: layer.family || "Barlow Condensed",
                weight: layer.weight || 800,
              });
            }
            ctx.restore();
          }
        } else if (layer.type === "counter_odometer") {
          const steps = layer.steps || [{ at_s: tStart, value: "0" }];
          const useComicBounce = layer.register === "comic" || layer.pop_bounce === true;
          const flyP = (useComicBounce ? easeOutBack : easeOutExpo)(seg(t, tStart, tStart + (layer.fly_up_s ?? 0.28)));
          const cx = W * (layer.x_pct ?? 0.5);
          const cy = H * (layer.y_pct ?? 0.22) + lerp(240, 0, clamp(flyP, 0, useComicBounce ? 1.06 : 1.0));
          const fPx = layer.font_px || 152;
          let curIdx = 0;
          for (let i = 0; i < steps.length; i++) {
            if (t >= steps[i].at_s) curIdx = i;
          }
          const curStep = steps[curIdx];
          const prevStep = curIdx > 0 ? steps[curIdx - 1] : null;
          const rollDur = layer.roll_s ?? 0.14;
          const rollP = prevStep ? easeOutExpo(seg(t, curStep.at_s, curStep.at_s + rollDur)) : 1.0;
          const odoFamily = layer.family || "Barlow Condensed";
          const odoWeight = layer.weight || 800;
          ctx.save();
          ctx.translate(cx, cy);
          ctx.rotate(((layer.angle_deg ?? 0) * Math.PI) / 180);
          ctx.beginPath();
          ctx.rect(-W * 0.46, -fPx * 1.05, W * 0.92, fPx * 2.10);
          ctx.clip();
          if (prevStep && rollP < 0.995) {
            drawGlowingText(String(prevStep.value), 0, lerp(0, -fPx * 0.72, rollP), fPx, {
              fill: layer.fill || "#F5C542",
              glowHex: layer.glow_hex || "#F59E0B",
              glowStrength: layer.glow_strength || "subtle",
              strokeHex: "rgba(3,22,31,0.88)",
              strokeWidth: Math.max(2.8, fPx * 0.032),
              alpha: baseAlpha * Math.pow(1 - rollP, 2.0),
              family: odoFamily,
              weight: odoWeight,
              tabularDigits: true,
            });
          }
          drawGlowingText(String(curStep.value), 0, lerp(fPx * 0.72, 0, rollP), fPx, {
            fill: layer.fill || "#F5C542",
            glowHex: layer.glow_hex || "#F59E0B",
            glowStrength: layer.glow_strength || "subtle",
            strokeHex: "rgba(3,22,31,0.88)",
            strokeWidth: Math.max(2.8, fPx * 0.032),
            alpha: prevStep ? baseAlpha * Math.pow(rollP, 1.15) : baseAlpha,
            family: odoFamily,
            weight: odoWeight,
            tabularDigits: true,
          });
          ctx.restore();
        } else if (layer.type === "question_arc") {
          const pt = projectPointSafe(layer.coord);
          if (pt) {
            const count = layer.count || 5;
            const spread = layer.spread_px || 260;
            const lift = layer.arc_lift_px || 52;
            const stagger = layer.stagger_s || 0.08;
            for (let i = 0; i < count; i++) {
              const it = tStart + i * stagger;
              if (t < it) continue;
              const pop = easeOutBack(seg(t, it, it + 0.24));
              const frac = count > 1 ? i / (count - 1) - 0.5 : 0;
              const qx = pt.x + (layer.dx || 0) + frac * spread;
              const qy = pt.y + (layer.dy || -80) - Math.cos(frac * Math.PI) * lift;
              drawGlowingText("?", qx, qy, layer.font_px || 66, {
                fill: layer.fill || "#FDE047",
                glowHex: layer.glow_hex || "#F59E0B",
                glowStrength: "intense",
                angle: frac * 0.35,
                scale: clamp(pop, 0, 1.15),
                alpha: baseAlpha,
                family: "Rubik",
                weight: 900,
              });
            }
          }
        } else if (layer.type === "shifting_route") {
          const coordsA = resolveGeom(layer.coords_a_ref) || layer.coords_a || [];
          const coordsB = resolveGeom(layer.coords_b_ref) || layer.coords_b || [];
          if (coordsA.length >= 2 && coordsA.length === coordsB.length) {
            const shiftU = layer.shift_start_s != null
              ? easeInOutCubic(seg(t, layer.shift_start_s, layer.shift_end_s ?? (layer.shift_start_s + 0.55)))
              : 0;
            const blended = coordsA.map((c, idx) => [
              lerp(c[0], coordsB[idx][0], shiftU),
              lerp(c[1], coordsB[idx][1], shiftU),
            ]);
            const prog = layer.draw_duration_s ? easeOutCubic(seg(t, tStart, tStart + layer.draw_duration_s)) : 1.0;
            drawPartialRoute(blended, prog, {
              color: layer.color || "#FDE047",
              bloom: layer.bloom || "#F5C542",
              core: layer.core ?? "#FFFFFF",
              width: layer.width || 9,
              dash: layer.dash || null,
              alpha: baseAlpha,
            });
          }
        } else if (layer.type === "curved_pointer_label") {
          const anchor = layer.coord ? projectPointSafe(layer.coord) : { x: W * (layer.x_pct ?? 0.5), y: H * (layer.y_pct ?? 0.25) };
          if (!anchor) continue;
          const bx = anchor.x + (layer.dx || 0);
          const by = anchor.y + (layer.dy || 0);
          const pop = easeOutCubic(seg(t, tStart, tStart + 0.28));
          const fPx = layer.font_px || 64;
          const lines = layer.lines || [String(layer.text || "")];
          const lineH = Math.round(fPx * 1.12);
          ctx.save();
          ctx.translate(bx, by);
          ctx.rotate(((layer.angle_deg ?? 0) * Math.PI) / 180);
          ctx.globalAlpha = baseAlpha * pop;
          const ptrFamily = layer.family || "Barlow Condensed";
          const ptrWeight = layer.weight || 800;
          ctx.font = ptrWeight + " " + fPx + "px '" + ptrFamily + "', " + inferFontFallback(ptrFamily);
          ctx.textBaseline = "middle";
          for (let li = 0; li < lines.length; li++) {
            const ly = (li - (lines.length - 1) * 0.5) * lineH;
            const ln = String(lines[li]);
            if (li === 0 && layer.highlight_prefix && ln.startsWith(layer.highlight_prefix)) {
              const pre = layer.highlight_prefix;
              const rest = ln.slice(pre.length);
              const wPre = ctx.measureText(pre).width;
              const wTot = ctx.measureText(ln).width;
              const x0 = -wTot * 0.5;
              // Red/neon radial glow behind highlighted prefix word (e.g. "NOT")
              const glowCol = layer.highlight_glow || "#EF4444";
              for (const [blurR, a] of [[fPx * 0.9, 0.72], [fPx * 0.45, 0.92], [fPx * 0.18, 1.0]]) {
                ctx.save();
                ctx.globalAlpha = baseAlpha * pop * a;
                ctx.shadowColor = glowCol;
                ctx.shadowBlur = blurR;
                ctx.fillStyle = "#FFFFFF";
                ctx.textAlign = "left";
                ctx.fillText(pre, x0, ly);
                ctx.restore();
              }
              ctx.save();
              ctx.globalAlpha = baseAlpha * pop;
              ctx.shadowColor = "rgba(0,0,0,0.85)";
              ctx.shadowBlur = 12;
              ctx.shadowOffsetY = 3;
              ctx.fillStyle = "#FFFFFF";
              ctx.textAlign = "left";
              ctx.fillText(pre, x0, ly);
              ctx.fillText(rest, x0 + wPre, ly);
              ctx.restore();
            } else {
              drawGlowingText(ln, 0, ly, fPx, {
                fill: layer.fill || "#F4F1EA",
                strokeHex: layer.stroke_hex ?? "rgba(3,22,31,0.84)",
                strokeWidth: layer.stroke_width ?? Math.max(2.0, fPx * 0.045),
                glowStrength: layer.glow_strength || "none",
                alpha: baseAlpha * pop,
                family: ptrFamily,
                weight: ptrWeight,
              });
            }
          }
          ctx.restore();
          // Graceful hand-drawn curved white Bezier arrow with open chevron tip
          if (layer.pointer_coord) {
            const tp = projectPointSafe(layer.pointer_coord);
            const sx = bx + (layer.arrow_start_dx || 0);
            const sy = by + (layer.arrow_start_dy ?? Math.round(lines.length * lineH * 0.5 + 14));
            const arrowProg = tp ? easeOutCubic(seg(t, tStart + 0.08, tStart + 0.44)) : 0;
            if (arrowProg > 0.01) {
              const dx = tp.x - sx, dy = tp.y - sy;
              const len = Math.max(1, Math.hypot(dx, dy));
              const nx = -dy / len, ny = dx / len;
              const bend = layer.arrow_bend_px ?? (len * 0.24);
              const cx = (sx + tp.x) * 0.5 + nx * bend;
              const cy = (sy + tp.y) * 0.5 + ny * bend;
              const bez = sampleQuadraticBezierTo({ x: sx, y: sy }, { x: cx, y: cy }, tp, arrowProg, 36);
              const pts = bez.points;
              ctx.save();
              ctx.globalAlpha = baseAlpha;
              ctx.strokeStyle = "#FFFFFF";
              ctx.lineWidth = layer.arrow_width || 5;
              ctx.lineCap = "round";
              ctx.lineJoin = "round";
              ctx.shadowColor = "rgba(0,0,0,0.75)";
              ctx.shadowBlur = 10;
              ctx.beginPath();
              ctx.moveTo(pts[0].x, pts[0].y);
              for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
              ctx.stroke();
              // Open chevron V-head at exact Bezier tip
              const tip = bez.tip;
              const ang = bez.angleRad;
              const ah = layer.arrow_head_px || 22;
              ctx.translate(tip.x, tip.y);
              ctx.rotate(ang);
              ctx.beginPath();
              ctx.moveTo(-ah, -ah * 0.52);
              ctx.lineTo(0, 0);
              ctx.lineTo(-ah, ah * 0.52);
              ctx.stroke();
              ctx.restore();
            }
          }
        } else if (layer.type === "pin_label") {
          const pt = projectPointSafe(layer.coord);
          if (!pt) continue;
          const pop = easeOutCubic(seg(t, tStart, tStart + 0.28));
          const coupling = layer.scale_coupling ?? 0.42;
          const zSc = layer.ref_zoom != null
            ? clamp(Math.pow(2, (map.getZoom() - layer.ref_zoom) * coupling), layer.min_scale ?? 0.55, layer.max_scale ?? 2.2)
            : 1.0;
          const stemH = (layer.stem_px ?? 58) * pop * zSc;
          ctx.save();
          ctx.globalAlpha = baseAlpha;
          ctx.shadowColor = "rgba(0,0,0,0.75)";
          ctx.shadowBlur = 8;
          ctx.strokeStyle = "#FFFFFF";
          ctx.lineWidth = Math.max(2, 3 * zSc);
          ctx.beginPath();
          ctx.moveTo(pt.x, pt.y);
          ctx.lineTo(pt.x, pt.y - stemH);
          ctx.stroke();
          ctx.fillStyle = "#FFFFFF";
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, Math.max(4, 6 * zSc), 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
          const pinFontPx = layer.font_px || 40;
          const pinPreset = layer.carto_role ? (CARTO_TYPO_PRESETS[layer.carto_role] || {}) : CARTO_TYPO_PRESETS.city;
          drawGlowingText(String(layer.text || ""), pt.x + (layer.dx || 0), pt.y - stemH - pinFontPx * 0.65 * zSc + (layer.dy || 0), pinFontPx, {
            fill: layer.fill || pinPreset.fill || "#F4F1EA",
            strokeHex: layer.stroke_hex ?? pinPreset.strokeHex ?? "rgba(3,22,31,0.82)",
            strokeWidth: layer.stroke_width ?? Math.max(1.8, pinFontPx * 0.045),
            glowStrength: layer.glow_strength || "none",
            scale: zSc,
            alpha: baseAlpha * pop,
            family: layer.family || pinPreset.family || "Inter",
            weight: layer.weight || pinPreset.weight || 700,
            fontStyle: layer.font_style || pinPreset.fontStyle || "normal",
            letterSpacing: layer.letter_spacing ?? (pinPreset.letterSpacingEm != null ? (pinPreset.letterSpacingEm + "em") : 0),
          });
        } else if (layer.type === "human_silhouette_row") {
          const count = layer.count || 10;
          const figH = layer.figure_h_px || 66;
          const spacing = layer.spacing_px || (figH * 0.50);
          const stagger = layer.pop_stagger_s ?? 0.055;
          const popDur = layer.pop_duration_s ?? 0.22;
          const splitAt = layer.split_at_s;
          const splitDur = layer.split_duration_s ?? 0.55;
          const splitLeftCount = layer.split_left_count ?? 2;
          const splitU = splitAt != null ? easeInOutCubic(seg(t, splitAt, splitAt + splitDur)) : 0;
          const exitScale = (layer.exit_scale_down_s && t > tEnd - layer.exit_scale_down_s)
            ? 1 - easeInCubic(seg(t, tEnd - layer.exit_scale_down_s, tEnd))
            : 1.0;

          const basePt = projectPointSafe(layer.coord);
          if (!basePt) continue;
          const leftPt = (layer.left_coord ? projectPointSafe(layer.left_coord) : null) || basePt;
          const rightPt = (layer.right_coord ? projectPointSafe(layer.right_coord) : null) || basePt;
          const refZoom = layer.ref_zoom ?? map.getZoom();
          const coupling = layer.scale_coupling ?? 0.85;
          const zSc = clamp(Math.pow(2, (map.getZoom() - refZoom) * coupling), layer.min_scale ?? 0.35, layer.max_scale ?? 2.6) * exitScale;

          for (let i = 0; i < count; i++) {
            const p = easeOutBack(seg(t, tStart + i * stagger, tStart + i * stagger + popDur));
            if (p <= 0.01) continue;
            const unifiedX = basePt.x + (layer.dx || 0) + (i - (count - 1) * 0.5) * spacing * zSc;
            const unifiedY = basePt.y + (layer.dy || 0);
            let tx = unifiedX;
            let ty = unifiedY;
            if (splitAt != null && splitU > 0.001) {
              if (i < splitLeftCount) {
                const lx = leftPt.x + (layer.left_dx || 0) + (i - (splitLeftCount - 1) * 0.5) * spacing * zSc;
                const ly = leftPt.y + (layer.left_dy || 0);
                tx = lerp(unifiedX, lx, splitU);
                ty = lerp(unifiedY, ly, splitU);
              } else {
                const rIdx = i - splitLeftCount;
                const rCount = count - splitLeftCount;
                const rx = rightPt.x + (layer.right_dx || 0) + (rIdx - (rCount - 1) * 0.5) * spacing * zSc;
                const ry = rightPt.y + (layer.right_dy || 0);
                tx = lerp(unifiedX, rx, splitU);
                ty = lerp(unifiedY, ry, splitU);
              }
            }
            let figAlpha = baseAlpha;
            if (i < splitLeftCount && layer.left_end_s != null) {
              if (t > layer.left_end_s) continue;
              if (layer.left_fade_out_s) figAlpha *= 1 - seg(t, layer.left_end_s - layer.left_fade_out_s, layer.left_end_s);
            }
            if (i >= splitLeftCount && layer.right_end_s != null) {
              if (t > layer.right_end_s) continue;
              if (layer.right_fade_out_s) figAlpha *= 1 - seg(t, layer.right_end_s - layer.right_fade_out_s, layer.right_end_s);
            }
            drawHumanFigure(tx, ty, figH * zSc * clamp(p, 0, 1.18), layer.color || "#FFFFFF", figAlpha);
          }
        } else if (layer.type === "landmark_silhouette") {
          let curCoord = layer.coord;
          let headingDeg = layer.angle_deg || 0;
          if (Array.isArray(layer.path) && layer.path.length >= 2) {
            const moveDur = layer.move_duration_s ?? (tEnd - tStart);
            const u = clamp(seg(t, tStart, tStart + moveDur), 0, 1);
            curCoord = samplePolylineCoord(layer.path, u);
            if (layer.auto_heading) {
              const pA = projectPointSafe(samplePolylineCoord(layer.path, Math.max(0, u - 0.02)));
              const pB = projectPointSafe(samplePolylineCoord(layer.path, Math.min(1, u + 0.02)));
              if (pA && pB && Math.hypot(pB.x - pA.x, pB.y - pA.y) > 0.5) {
                headingDeg = (Math.atan2(pB.y - pA.y, pB.x - pA.x) * 180) / Math.PI;
              }
            }
          }
          const pt = projectPointSafe(curCoord);
          if (!pt) continue;
          const coupling = layer.scale_coupling ?? 0.55;
          const zSc = layer.ref_zoom != null
            ? clamp(Math.pow(2, (map.getZoom() - layer.ref_zoom) * coupling), layer.min_scale ?? 0.45, layer.max_scale ?? 2.4)
            : 1.0;
          const riseP = layer.rise_duration_s
            ? easeOutBack(seg(t, tStart, tStart + layer.rise_duration_s))
            : 1.0;
          const exitScale = (layer.exit_scale_down_s && t > tEnd - layer.exit_scale_down_s)
            ? 1 - easeInCubic(seg(t, tEnd - layer.exit_scale_down_s, tEnd))
            : 1.0;
          drawLandmarkSilhouette(
            pt.x + (layer.dx || 0),
            pt.y + (layer.dy || 0),
            (layer.height_px || 190) * zSc * exitScale,
            layer.landmark || "statue_of_liberty",
            {
              fillHex: layer.fill_hex || "#94A3B8",
              accentHex: layer.accent_hex || "#CBD5E1",
              rimHex: layer.rim_hex || "#E2E8F0",
              alpha: baseAlpha,
              riseProgress: clamp(riseP, 0, 1.08),
              time: tLoc,
              angleDeg: headingDeg,
            },
          );
        } else if (layer.type === "cloud_system") {
          const refZoom = layer.ref_zoom ?? map.getZoom();
          const coupling = layer.scale_coupling ?? 0.85;
          const zSc = clamp(Math.pow(2, (map.getZoom() - refZoom) * coupling), layer.min_scale ?? 0.35, layer.max_scale ?? 3.0);
          for (let ci = 0; ci < (layer.clouds || []).length; ci++) {
            const cl = layer.clouds[ci];
            const cStart = cl.start_s ?? tStart;
            const cEnd = cl.end_s ?? tEnd;
            if (t < cStart - 0.001 || t > cEnd + 0.001) continue;
            const cIn = easeOutCubic(seg(t, cStart, cStart + (cl.fade_in_s ?? 0.45)));
            const cOut = 1 - seg(t, cEnd - (cl.fade_out_s ?? 0.45), cEnd);
            const cAlpha = baseAlpha * clamp(cIn * cOut * (cl.opacity ?? 0.96), 0, 1);
            const moveDur = cl.move_duration_s ?? (cEnd - cStart);
            const rawU = seg(t, cStart, cStart + moveDur);
            const u = cl.easing === "linear" ? rawU : cl.easing === "ease_in_out" ? easeInOutCubic(rawU) : easeOutCubic(rawU);
            const coord = samplePolylineCoord(cl.path, u);
            const pt = projectPointSafe(coord);
            if (!pt) continue;
            drawShadedCloud(
              pt.x + (cl.dx || 0),
              pt.y + (cl.dy || 0),
              (cl.radius_px || 78) * zSc,
              cAlpha,
              t - cStart,
              cl.seed ?? (ci + 1),
              (cl.shadow_dx ?? 18) * zSc,
              (cl.shadow_dy ?? 34) * zSc,
            );
          }
        } else if (layer.type === "wind_streamlines") {
          for (const st of layer.streams || []) {
            const sStart = st.start_s ?? tStart;
            const sEnd = st.end_s ?? tEnd;
            if (t < sStart || t > sEnd) continue;
            const dur = st.duration_s ?? 1.4;
            const rep = st.repeat_s ?? 0;
            const localT = t - sStart;
            const tailFrac = st.tail_frac ?? 0.42;
            const cycles = rep > 0 ? Math.floor(localT / rep) + 1 : 1;
            for (let c = 0; c < cycles; c++) {
              const ct = localT - c * rep;
              if (ct < 0 || ct > dur * (1 + tailFrac)) continue;
              const headU = (ct / dur) * (1 + tailFrac);
              drawWindStreamline(st.coords, headU, tailFrac, {
                widthPx: st.width_px ?? 4.8,
                color: st.color || "#FFFFFF",
                glowHex: st.glow_hex || "#7CE0F9",
                alpha: baseAlpha * (st.opacity ?? 0.88),
              });
            }
          }
        } else if (layer.type === "prohibition_pins") {
          const refZoom = layer.ref_zoom ?? map.getZoom();
          const coupling = layer.scale_coupling ?? 0.72;
          const zSc = clamp(Math.pow(2, (map.getZoom() - refZoom) * coupling), layer.min_scale ?? 0.40, layer.max_scale ?? 2.2);
          for (const pin of layer.pins || []) {
            const pStart = pin.pop_s ?? tStart;
            if (t < pStart) continue;
            const popP = easeOutBack(seg(t, pStart, pStart + (pin.pop_duration_s ?? 0.26)));
            const slashStart = pStart + (pin.slash_delay_s ?? 0.36);
            const slashP = easeOutCubic(seg(t, slashStart, slashStart + (pin.slash_duration_s ?? 0.24)));
            const pt = projectPointSafe(pin.coord);
            if (!pt) continue;
            drawProhibitionPin(
              pt.x + (pin.dx || 0),
              pt.y + (pin.dy || 0),
              (pin.radius_px || 44) * zSc,
              pin.icon || "water_drop",
              clamp(popP, 0, 1.15),
              slashP,
              baseAlpha,
              pin.shape || layer.shape || "teardrop",
            );
          }
        } else if (layer.type === "tree_belt") {
          drawTreeBelt(layer, t, tStart, tEnd, baseAlpha);
        } else if (layer.type === "dust_storm_plume") {
          drawDustStormPlume(layer, t, tStart, tEnd, baseAlpha);
        } else if (layer.type === "parchment_sheet") {
          drawParchmentSheet(layer, t, tStart, tEnd, baseAlpha);
        } else if (layer.type === "map_sprites") {
          const refZoom = layer.ref_zoom ?? map.getZoom();
          const coupling = layer.scale_coupling ?? 0.75;
          const zSc = clamp(Math.pow(2, (map.getZoom() - refZoom) * coupling), layer.min_scale ?? 0.35, layer.max_scale ?? 2.8);
          for (const item of layer.sprites || layer.items || []) {
            drawMapSprite(item, t, tStart, tEnd, baseAlpha, zSc);
          }
        }
      }
    }

    const ALLOW_WORLD_VOID = ${allowWorldVoid};
    const stageEl = document.getElementById("stage");`;
}
