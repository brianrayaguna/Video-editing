/**
 * Conservative static-hold frame deduplication helpers for declarative map scenes.
 *
 * A frame is only eligible for buffer reuse when the camera, cut-blur, shutter
 * state, and every active layer are provably stationary across `prevT -> t`.
 */

export const CONTINUOUSLY_ANIMATED_LAYER_TYPES = new Set([
  "flag_fill",
  "weather_clouds_rain",
  "radar_rings",
  "map_sprites",
  "model_3d",
  "counter_odometer",
  "void_wipe",
  "cable_3d",
  "volume_3d",
  "country_block_3d",
  "curved_arc_arrow",
  "route_arrow",
  "pulse_beacon",
  "seismic_ripples",
  "water_flow",
  "particles",
  "animated_polyline",
  "polyline",
  "dashed_distance",
]);

function isLayerVisibleAt(layer, t) {
  const start = Number(layer.start_s ?? layer.t_start ?? 0);
  const end = layer.end_s != null ? Number(layer.end_s) : layer.t_end != null ? Number(layer.t_end) : Infinity;
  return t >= start && t <= end;
}

/**
 * Return `true` iff `layer` has identical visual output at `prevT` and `t`.
 */
export function isLayerStaticAtFrame(layer, t, prevT) {
  if (!layer || typeof layer !== "object") return true;

  const visNow = isLayerVisibleAt(layer, t);
  const visPrev = isLayerVisibleAt(layer, prevT);
  if (!visNow && !visPrev) return true;
  if (visNow !== visPrev) return false;

  const type = String(layer.type || "");
  if (CONTINUOUSLY_ANIMATED_LAYER_TYPES.has(type)) return false;

  // Any explicit animated flags or dynamic properties disqualify static dedup.
  if (
    layer.flag_fill ||
    layer.pulse ||
    layer.animate ||
    layer.animation ||
    layer.animated ||
    layer.keyframes ||
    layer.orbit_speed ||
    layer.flow_speed ||
    layer.wave_speed
  ) {
    return false;
  }

  const start = Number(layer.start_s ?? layer.t_start ?? 0);
  const end = layer.end_s != null ? Number(layer.end_s) : layer.t_end != null ? Number(layer.t_end) : Infinity;
  const fadeIn = Math.max(
    0,
    Number(layer.fade_in_s ?? layer.entrance_s ?? layer.draw_duration_s ?? layer.reveal_s ?? 0.35)
  );
  const fadeOut = Math.max(0, Number(layer.fade_out_s ?? layer.exit_s ?? 0.3));

  const settledStart = start + fadeIn + 1e-4;
  const settledEnd = Number.isFinite(end) ? end - fadeOut - 1e-4 : Infinity;

  if (prevT < settledStart || t < settledStart) return false;
  if (prevT > settledEnd || t > settledEnd) return false;

  return true;
}

function quant(v) {
  return Number.isFinite(Number(v)) ? Number(v).toFixed(6) : "0.000000";
}

/**
 * Compute a deterministic state key for a map frame, or `null` when the frame
 * must be freshly rendered (blur, shutter subframes, or any animated layer).
 */
export function computeMapFrameStateKey({ cam, layers, t, prevT, blurAmt = 0, subN = 1 }) {
  if (!cam || prevT == null || !Number.isFinite(t) || !Number.isFinite(prevT)) {
    return null;
  }
  if (Number(blurAmt) > 0.002 || Number(subN) > 1) {
    return null;
  }
  const activeMask = [];
  const layerList = Array.isArray(layers) ? layers : [];
  for (let i = 0; i < layerList.length; i++) {
    const layer = layerList[i];
    if (!isLayerStaticAtFrame(layer, t, prevT)) {
      return null;
    }
    if (isLayerVisibleAt(layer, t)) {
      activeMask.push(i);
    }
  }
  const c0 = Array.isArray(cam.center) ? cam.center[0] : 0;
  const c1 = Array.isArray(cam.center) ? cam.center[1] : 0;
  return [
    quant(c0),
    quant(c1),
    quant(cam.zoom),
    quant(cam.bearing || 0),
    quant(cam.pitch || 0),
    quant(cam.roll || 0),
    activeMask.join(","),
  ].join("|");
}
