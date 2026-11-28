/**
 * Conservative static-hold frame deduplication helpers for declarative map scenes.
 *
 * Uses a strict default-deny allowlist: a frame is only eligible for buffer reuse
 * when the camera, cut-blur, shutter state, and every active layer belong to the
 * static-safe allowlist and are provably stationary across `prevT -> t`.
 */

export const CONTINUOUSLY_ANIMATED_LAYER_TYPES = new Set([
  "flag_fill",
  "weather_clouds_rain",
  "radar_rings",
  "map_sprites",
  "model_3d",
  "endpoint_dots",
  "migrant_swarm",
  "crimson_x",
  "cloud_system",
  "wind_streamlines",
  "dust_storm_plume",
  "landmark_silhouette",
  "counter_odometer",
  "void_wipe",
  "cable_3d",
  "volume_3d",
  "country_block_3d",
  "curved_arc_arrow",
  "route_arrow",
  "route",
  "measurement_arrow",
  "parchment_sheet",
  "human_silhouette_row",
  "prohibition_pins",
  "pulse_beacon",
  "seismic_ripples",
  "water_flow",
  "particles",
  "animated_polyline",
  "polyline",
  "dashed_distance",
]);

export const STATIC_HOLD_SAFE_LAYER_TYPES = new Set([
  "glow_label",
  "pin_label",
  "curved_pointer_label",
  "polygon",
  "flag_pin",
  "region_outline",
  "border_line",
  "vignette",
  "tint",
]);

const DYNAMIC_PROP_KEYS = [
  "flag_fill",
  "pulse",
  "pulse_speed",
  "wave",
  "rim_glint",
  "light_sweep",
  "flashes",
  "lift_px",
  "fly_through",
  "count_to",
  "typewriter_s",
  "move_to_coord",
  "sub_pill",
  "angle_end",
  "tracking_from_em",
  "slide_from_x_px",
  "split_at_s",
  "animate",
  "animation",
  "animated",
  "keyframes",
  "orbit_speed",
  "flow_speed",
  "wave_speed",
];

function isLayerVisibleAt(layer, t) {
  const start = Number(layer.start_s ?? layer.t_start ?? 0);
  const end = layer.end_s != null ? Number(layer.end_s) : layer.t_end != null ? Number(layer.t_end) : Infinity;
  return t >= start && t <= end;
}

function resolveSettleInSeconds(layer, type) {
  const explicitFade = Math.max(
    0,
    Number(layer.fade_in_s ?? layer.entrance_s ?? layer.draw_duration_s ?? layer.reveal_s ?? 0.4)
  );
  const drawDelay = Math.max(0, Number(layer.draw_delay_s ?? 0));
  const drawDur = Math.max(0, Number(layer.draw_duration_s ?? 0));
  let settle = Math.max(explicitFade, drawDelay + drawDur);

  if (type === "polygon") {
    const hatchDelay = Math.max(0, Number(layer.hatch_delay_s ?? 0));
    const hatchDraw = layer.hatch_draw_s != null ? Number(layer.hatch_draw_s) : 0.75;
    const liftDelay = Math.max(0, Number(layer.lift_delay_s ?? 0));
    const liftDur = layer.lift_duration_s != null ? Number(layer.lift_duration_s) : 0.55;
    settle = Math.max(settle, hatchDelay + hatchDraw, liftDelay + liftDur);
  } else if (type === "glow_label" || type === "pin_label" || type === "curved_pointer_label") {
    const countDur = Math.max(0, Number(layer.count_duration_s ?? 0));
    const trackDur = Math.max(0, Number(layer.tracking_duration_s ?? 0));
    settle = Math.max(settle, countDur, trackDur);
  }
  return settle;
}

/**
 * Return `true` iff `layer` is provably stationary with identical output at `prevT` and `t`.
 */
export function isLayerStaticAtFrame(layer, t, prevT) {
  if (!layer || typeof layer !== "object") return true;

  const visNow = isLayerVisibleAt(layer, t);
  const visPrev = isLayerVisibleAt(layer, prevT);
  if (!visNow && !visPrev) return true;
  if (visNow !== visPrev) return false;

  const type = String(layer.type || "");
  if (CONTINUOUSLY_ANIMATED_LAYER_TYPES.has(type) || !STATIC_HOLD_SAFE_LAYER_TYPES.has(type)) {
    return false;
  }

  for (const key of DYNAMIC_PROP_KEYS) {
    if (layer[key]) return false;
  }

  const start = Number(layer.start_s ?? layer.t_start ?? 0);
  const end = layer.end_s != null ? Number(layer.end_s) : layer.t_end != null ? Number(layer.t_end) : Infinity;
  const settleIn = resolveSettleInSeconds(layer, type);
  const fadeOut = Math.max(0, Number(layer.fade_out_s ?? layer.exit_s ?? 0.35));

  const settledStart = start + settleIn + 1e-4;
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
 * must be freshly rendered (blur, shutter subframes, or any non-static layer).
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
