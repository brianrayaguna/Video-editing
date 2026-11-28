import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { isAbsolute, join, resolve, sep } from "node:path";
import { createCdpScreenshotter, spawnFramePipeEncoder } from "../fast_capture.mjs";
import { cutBlurAmount, shutterSubframeSchedule } from "../map_draw_math.mjs";
import { DEFAULT_MAP_CENTER } from "../geo_defaults.mjs";
import { buildDynamicFontFaceCss } from "./font_css.mjs";
import { buildBlueprintHtml } from "./html_blueprint.mjs";
import { buildCutaway2dHtml } from "./html_cutaway.mjs";
import { buildMapSceneHtml, defaultTileSource } from "./html_map_scene.mjs";

export function wrapDeltaDeg(fromDeg, toDeg) {
  return ((((toDeg - fromDeg) + 180) % 360) + 360) % 360 - 180;
}

export function sampleCameraAt(samples, frameIndex, subOffset = 0) {
  if (!samples || samples.length === 0) return { center: [0, 0], zoom: 2, bearing: 0, pitch: 0, shutter_samples: 1 };
  const exact = frameIndex + subOffset;
  if (exact <= 0) return samples[0];
  if (exact >= samples.length - 1) return samples[samples.length - 1];
  const i0 = Math.floor(exact);
  const i1 = Math.min(samples.length - 1, i0 + 1);
  const u = exact - i0;
  const a = samples[i0], b = samples[i1];
  return {
    center: [
      a.center[0] + wrapDeltaDeg(a.center[0], b.center[0]) * u,
      a.center[1] + (b.center[1] - a.center[1]) * u,
    ],
    zoom: a.zoom + (b.zoom - a.zoom) * u,
    bearing: (a.bearing || 0) + wrapDeltaDeg(a.bearing || 0, b.bearing || 0) * u,
    pitch: (a.pitch || 0) + ((b.pitch || 0) - (a.pitch || 0)) * u,
    roll: (a.roll || 0) + ((b.roll || 0) - (a.roll || 0)) * u,
    shutter_samples: a.shutter_samples || 1,
  };
}


export async function bakeAct(browser, baseUrl, vectorsJson, width, height, fps, act, outDir, opts = {}) {
  const previewCount = Number(opts.previewKeyframes || 0);
  const isPreview = previewCount > 0;
  const outName = act.output_file || act.output_name || `${act.act_id}.mp4`;
  const outMp4 = resolve(outDir, outName);
  const resolvedOutDir = resolve(outDir);
  if (!outMp4.startsWith(resolvedOutDir + sep)) {
    throw new Error(`Output path escapes output directory (${resolvedOutDir}): ${outName}`);
  }
  const actKind = act.kind || act.mode || act.type || "map";
  const totalFrames = Math.max(1, Math.round(act.duration_s * fps));
  if (actKind !== "blueprint_paper") {
    const REJECTED_LAYERS = new Set([
      "coord_plaque",
      "scale_comparison",
      "survey_pin",
      "orbital_sightlines",
      "culmination_sun",
      "callout_badge",
    ]);
    for (const layer of act.layers || []) {
      if (REJECTED_LAYERS.has(layer.type)) {
        throw new Error(
          `Rejected legacy chrome layer type "${layer.type}" in act "${act.act_id}". ` +
          `Use calibrated boxless primitives instead (glow_label, pin_label, curved_pointer_label, dashed_distance, curved_arc_arrow, void_wipe, counter_odometer, ghost_overlay, prohibition_pins).`
        );
      }
    }
  }
  console.log(`\n=== ${isPreview ? "Previewing" : "Baking"} ${act.act_id} (${actKind}): ${act.duration_s.toFixed(3)}s (${totalFrames} frames) -> ${isPreview ? "keyframes" : outMp4} ===`);

  const captureFormat = act.capture_format || opts.captureFormat || "jpeg";
  const captureQuality = act.capture_quality ?? opts.captureQuality ?? 95;
  const t0 = Date.now();
  const trackLog = [];
  const previewFrames = [];
  let succeeded = false;
  let page = null;
  let shotter = null;
  let encoder = null;

  const sampleIndices = (() => {
    if (!isPreview) return null;
    const count = Math.max(1, Math.min(totalFrames, previewCount));
    if (count === 1) return [0];
    const s = new Set([0, totalFrames - 1]);
    for (let i = 1; i < count - 1; i++) {
      s.add(Math.min(totalFrames - 1, Math.round((i / (count - 1)) * (totalFrames - 1))));
    }
    return [...s].sort((a, b) => a - b);
  })();

  try {
    page = await browser.newPage();
    page.on("pageerror", (err) => console.error(`  [${act.act_id} pageerror]`, err));
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    shotter = await createCdpScreenshotter(page, width, height, {
      format: captureFormat,
      quality: captureQuality,
    });
    encoder = isPreview
      ? null
      : spawnFramePipeEncoder(outMp4, {
          codec: captureFormat === "png" ? "png" : "mjpeg",
          fps,
          crf: 15,
          gop: 1,
          preset: "fast",
          useVideoToolbox: false,
        });
    if (actKind === "blueprint_paper") {
      await page.setContent(buildBlueprintHtml(baseUrl, width, height, vectorsJson, act), { waitUntil: "load" });
      await page.evaluate(() => document.fonts.ready);
      const framesToRun = sampleIndices || Array.from({ length: totalFrames }, (_, i) => i);
      for (const f of framesToRun) {
        await page.evaluate((sec) => window.__renderBlueprint(sec), f / fps);
        const buf = await shotter.captureJpegBuffer();
        if (isPreview) previewFrames.push({ act_id: act.act_id, frame: f, t_s: f / fps, buf });
        else await encoder.writeFrame(buf);
        if (!isPreview && (f % 60 === 0 || f === totalFrames - 1)) {
          console.log(`  [${act.act_id}] frame ${f + 1}/${totalFrames} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
        }
      }
    } else if (actKind === "cutaway_2d") {
      let cutawayHtml;
      if (typeof act.custom_html === "string" && act.custom_html.trim()) {
        cutawayHtml = act.custom_html;
      } else if (typeof act.html_file === "string" && act.html_file.trim()) {
        const htmlPath = isAbsolute(act.html_file)
          ? act.html_file
          : resolve(opts.baseDir || process.cwd(), act.html_file);
        if (!existsSync(htmlPath)) {
          throw new Error(`Act '${act.act_id}' cutaway_2d html_file not found: ${htmlPath}`);
        }
        cutawayHtml = readFileSync(htmlPath, "utf8");
      } else {
        cutawayHtml = buildCutaway2dHtml(baseUrl, width, height, act);
      }
      if (typeof act.custom_html === "string" || typeof act.html_file === "string") {
        const safeSpec = JSON.stringify(act).replace(/</g, "\\u003c");
        cutawayHtml = cutawayHtml
          .replaceAll("{{BASE_URL}}", baseUrl)
          .replaceAll("{{WIDTH}}", String(width))
          .replaceAll("{{HEIGHT}}", String(height))
          .replaceAll("{{SPEC_JSON}}", safeSpec)
          .replaceAll("{{FONT_FACE_CSS}}", buildDynamicFontFaceCss(baseUrl));
      }
      await page.setContent(cutawayHtml, { waitUntil: "load" });
      await page.evaluate((specObj, urlStr) => {
        window.__CUTAWAY_SPEC = specObj;
        window.__BASE_URL = urlStr;
      }, act, baseUrl);
      await page.evaluate(() => document.fonts.ready);
      const framesToRun = sampleIndices || Array.from({ length: totalFrames }, (_, i) => i);
      for (const f of framesToRun) {
        await page.evaluate((sec) => {
          if (typeof window.__renderCutaway === "function") window.__renderCutaway(sec);
          else if (typeof window.__renderFrame === "function") window.__renderFrame(sec);
          else throw new Error("Custom cutaway_2d HTML must define window.__renderCutaway(t) or window.__renderFrame(t).");
        }, f / fps);
        const buf = await shotter.captureJpegBuffer();
        if (isPreview) previewFrames.push({ act_id: act.act_id, frame: f, t_s: f / fps, buf });
        else await encoder.writeFrame(buf);
        if (!isPreview && (f % 60 === 0 || f === totalFrames - 1)) {
          console.log(`  [${act.act_id}] frame ${f + 1}/${totalFrames} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
        }
      }
    } else {
      const has3d = (act.layers || []).some(
        (l) => l && (l.type === "cable_3d" || l.type === "model_3d" || l.type === "volume_3d" || l.type === "country_block_3d")
      );
      const initialCam = sampleCameraAt(act.camera_samples || [], 0, 0);
      const maxPitch = Math.max(
        Number(initialCam.pitch || 0),
        ...(act.camera_samples || []).map((s) => Number(s?.pitch || 0))
      );
      await page.setContent(
        buildMapSceneHtml(baseUrl, width, height, vectorsJson, {
          tile_source: act.tile_source || defaultTileSource(),
          projection: act.projection || "mercator",
          terrain_3d: Boolean(act.terrain_3d),
          terrain_exaggeration: act.terrain_exaggeration ?? 2.4,
          dem_maxzoom: act.dem_maxzoom ?? 10,
          allow_world_void: Boolean(act.allow_world_void),
          has_3d: has3d,
          origin_coord: act.origin_coord || initialCam.center,
          initial_camera: initialCam,
          max_pitch: maxPitch,
          ov_scale: act.ov_scale ?? opts.ovScale ?? 1.5,
          sun_azimuth_deg: act.sun_azimuth_deg ?? opts.sunAzimuthDeg ?? 335,
          sun_elevation_deg: act.sun_elevation_deg ?? opts.sunElevationDeg ?? 42,
          atmosphere: act.atmosphere ?? null,
          hdr_bloom: act.hdr_bloom ?? opts.hdrBloom ?? true,
          imagery_credit: act.imagery_credit ?? opts.imageryCredit ?? null,
          show_credit: act.show_credit ?? opts.showCredit ?? true,
        }),
        { waitUntil: "load" }
      );
      await page.evaluate(() => window.__ready);
      const samples = act.camera_samples || [];
      const layers = act.layers || [];
      // Deterministically preload Canvas 2D font faces before frame 0 so measureText/fillText never hit FOUT.
      const fontSpecs = new Set([
        "700 48px 'Montserrat'",
        "800 64px 'Montserrat'",
        "900 84px 'Montserrat'",
        "700 48px 'Outfit'",
        "800 64px 'Outfit'",
        "700 48px 'Barlow Condensed'",
        "800 64px 'Barlow Condensed'",
        "600 40px 'Inter'",
        "700 48px 'Inter'",
        "700 56px 'Rubik'",
        "italic 600 42px 'Lora'",
        "700 42px 'Lora'",
        "700 42px 'IBM Plex Mono'",
        "400 64px 'Archivo Black'",
      ]);
      for (const layer of layers) {
        if (layer.family) {
          const st = layer.font_style === "italic" ? "italic " : "";
          const wt = layer.weight || 700;
          fontSpecs.add(`${st}${wt} 48px '${layer.family}'`);
        }
      }
      await page.evaluate(async (specs) => {
        await Promise.allSettled(specs.map((s) => document.fonts.load(s)));
        await document.fonts.ready;
      }, [...fontSpecs]);
      const preloadUrls = [];
      const preloadModelUrls = [];
      for (const layer of layers) {
        if (layer.type === "flag_pin" && layer.code) {
          preloadUrls.push(`${baseUrl}/flags/${String(layer.code).toLowerCase()}.svg`);
        }
        if ((layer.type === "polygon" || layer.type === "country_block_3d") && layer.flag_fill) {
          preloadUrls.push(`${baseUrl}/flags/${String(layer.flag_fill).toLowerCase()}.svg`);
        }
        if (layer.type === "model_3d" && layer.gltf_url) {
          const u = String(layer.gltf_url);
          preloadModelUrls.push(u.startsWith("http") ? u : `${baseUrl}/${u.replace(/^\/+/, "")}`);
        }
        if (layer.type === "map_sprites") {
          for (const sp of layer.sprites || layer.items || []) {
            const rawU = sp?.svg_url || sp?.image_url;
            if (rawU) {
              const u = String(rawU);
              preloadUrls.push(u.startsWith("http") ? u : `${baseUrl}/${u.replace(/^\/+/, "")}`);
            }
          }
        }
      }
      if (preloadUrls.length > 0) {
        await page.evaluate((urls) => window.__preloadAssets(urls), preloadUrls);
        const missing = await page.evaluate((urls) => urls.filter((u) => !window.__imgCache[u]), [...new Set(preloadUrls)]);
        for (const u of missing) {
          console.warn(`  [${act.act_id}] warning: flag asset not found (${u.split("/").pop()}); layer falls back to its colour fill`);
        }
      }
      if (preloadModelUrls.length > 0) {
        await page.evaluate((urls) => window.__preloadModels(urls), preloadModelUrls);
        const missingM = await page.evaluate((urls) => urls.filter((u) => !window.__gltfCache[u]), [...new Set(preloadModelUrls)]);
        for (const u of missingM) {
          console.warn(`  [${act.act_id}] warning: glTF asset failed to load (${u}); falling back to procedural geometry`);
        }
      }
      // Sub-frame shutter accumulation is opt-in so frames stay crisp by default.
      const enableShutter = act.optical_shutter_blur === true;
      // Radial zoom blur that peaks on the act's first and/or last frame (cut accents).
      const cutBlurIn = Number(act.cut_blur_in_s) || 0;
      const cutBlurOut = Number(act.cut_blur_out_s) || 0;
      const cutBlurStrength = act.cut_blur_strength ?? 0.12;
      const IDLE_WAIT_MS = 6000;
      let pendingFrames = 0;

      // Pre-warm tiles across act timeline (skip for fast keyframe preview)
      if (!isPreview) {
        for (let f = 0; f < totalFrames; f += Math.max(15, Math.floor(totalFrames / 8))) {
          const cam = sampleCameraAt(samples, f, 0);
          await page.evaluate((c) => window.__setSceneCamera(c), cam);
          await page.evaluate((ms) => window.__waitIdle(ms), 1500);
        }
      }

      const framesToRun = sampleIndices || Array.from({ length: totalFrames }, (_, i) => i);
      for (const f of framesToRun) {
        const cam = sampleCameraAt(samples, f, 0);
        const subN = !isPreview && enableShutter ? Math.min(16, Math.max(1, cam.shutter_samples || 1)) : 1;
        const blurAmt = cutBlurAmount(f, totalFrames, fps, cutBlurIn, cutBlurOut, cutBlurStrength);
        const applyCutBlur = async () => {
          if (blurAmt > 0.002) await page.evaluate((a) => window.__cutBlurComposite(a, 12), blurAmt);
        };
        if (subN > 1 && f > 0) {
          let pending = false;
          const schedule = shutterSubframeSchedule(subN, act.shutter_angle_deg ?? 180, act.shutter_profile || "cosine");
          let cumWeight = 0;
          await page.evaluate(() => window.__beginShutterAccum());
          for (const entry of schedule) {
            const subOff = entry.offset;
            cumWeight += entry.weight;
            const subCam = sampleCameraAt(samples, f, subOff);
            const subT = Math.max(0, (f + subOff) / fps);
            await page.evaluate((c) => window.__setSceneCamera(c), subCam);
            pending = (await page.evaluate((ms) => window.__waitIdle(ms), IDLE_WAIT_MS)) || pending;
            await page.evaluate(([ls, sec]) => window.__drawSceneLayers(ls, sec), [layers, subT]);
            await page.evaluate(([w, cw]) => window.__accumSubframe(w, cw), [entry.weight, cumWeight]);
          }
          if (pending) pendingFrames++;
          await applyCutBlur();
          await encoder.writeFrame(await shotter.captureBuffer());
          await page.evaluate(() => window.__endShutterAccum());
        } else {
          await page.evaluate((c) => window.__setSceneCamera(c), cam);
          if (await page.evaluate((ms) => window.__waitIdle(ms), IDLE_WAIT_MS)) pendingFrames++;
          await page.evaluate(([ls, sec]) => window.__drawSceneLayers(ls, sec), [layers, f / fps]);
          await applyCutBlur();
          const buf = await shotter.captureBuffer();
          if (isPreview) previewFrames.push({ act_id: act.act_id, frame: f, t_s: f / fps, buf });
          else await encoder.writeFrame(buf);
          if (blurAmt > 0.002) await page.evaluate(() => window.__endShutterAccum());
        }
        if (!isPreview && act.export_camera_track) {
          trackLog.push({ frame: f, t: Number((f / fps).toFixed(4)), ...cam });
        }
        if (!isPreview && (f % 60 === 0 || f === totalFrames - 1)) {
          console.log(`  [${act.act_id}] frame ${f + 1}/${totalFrames} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
        }
      }
      console.log(`  [${act.act_id}] frames captured with tiles still pending: ${pendingFrames}`);
      if (!isPreview && act.export_camera_track) {
        writeFileSync(join(outDir, `${act.act_id}_camera_track.json`), JSON.stringify(trackLog));
      }
    }
    succeeded = true;
  } finally {
    if (shotter) await shotter.close().catch(() => {});
    if (page) await page.close().catch(() => {});
    if (!succeeded && encoder) {
      await encoder.abort().catch(() => {});
    }
  }
  if (encoder) await encoder.finish();
  return previewFrames;
}

/**
 * Coverage pass for one map act: step the camera over every 2nd frame (plus the last), waiting
 * for tiles, without drawing overlays or capturing frames. The tile server records every raster
 * tile it had to synthesise from an upscaled ancestor.
 */
export async function coverageAct(browser, baseUrl, vectorsJson, width, height, fps, act) {
  const actKind = act.kind || act.mode || act.type || "map";
  if (actKind === "blueprint_paper" || actKind === "cutaway_2d") return;
  const samples = act.camera_samples || [];
  const totalFrames = Math.max(
    1,
    act.duration_s != null ? Math.round(act.duration_s * fps) : samples.length || Math.round(fps)
  );
  const initialCam = sampleCameraAt(samples, 0, 0);
  const page = await browser.newPage();
  try {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await page.setContent(
      buildMapSceneHtml(baseUrl, width, height, vectorsJson, {
        tile_source: act.tile_source || "realistic",
        projection: act.projection || "mercator",
        terrain_3d: Boolean(act.terrain_3d),
        terrain_exaggeration: act.terrain_exaggeration ?? 2.4,
        dem_maxzoom: act.dem_maxzoom ?? 10,
        allow_world_void: Boolean(act.allow_world_void),
        initial_camera: initialCam,
      }),
      { waitUntil: "load" }
    );
    await page.evaluate(() => window.__ready);
    const frames = [];
    for (let f = 0; f < totalFrames; f += 2) frames.push(f);
    if (frames[frames.length - 1] !== totalFrames - 1) frames.push(totalFrames - 1);
    for (const f of frames) {
      await page.evaluate((c) => window.__setSceneCamera(c), sampleCameraAt(samples, f, 0));
      await page.evaluate((ms) => window.__waitIdle(ms), 6000);
    }
  } finally {
    await page.close();
  }
}

