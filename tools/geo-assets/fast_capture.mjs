/**
 * High-throughput Chromium CDP JPEG capture & direct FFmpeg image2pipe helpers
 * for offline local MapLibre A-roll baking.
 */

import { spawn, spawnSync } from "node:child_process";

/**
 * Return platform-appropriate Chromium flags with optional backend parity override
 * (`"auto" | "metal" | "swiftshader"`, or `VEDIT_RENDER_BACKEND` env var).
 */
export function getChromeArgs(
  width,
  height,
  { backend = "auto", platform = process.platform } = {}
) {
  const winArg = width && height ? [`--window-size=${width},${height}`] : [];
  const rawBackend = String(
    backend === "auto" ? process.env.VEDIT_RENDER_BACKEND || "auto" : backend
  )
    .trim()
    .toLowerCase();
  if (!["auto", "metal", "swiftshader"].includes(rawBackend)) {
    throw new Error(
      `Unsupported render backend '${rawBackend}'. Expected 'auto', 'metal', or 'swiftshader'.`
    );
  }
  const resolved =
    rawBackend === "auto" ? (platform === "darwin" ? "metal" : "swiftshader") : rawBackend;

  if (resolved === "metal") {
    return [
      "--no-sandbox",
      "--hide-scrollbars",
      "--use-gl=angle",
      "--use-angle=metal",
      ...winArg,
    ];
  }
  return [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--hide-scrollbars",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--enable-webgl",
    ...winArg,
  ];
}

/**
 * Create a persistent CDP session for fast frame capture (`jpeg` or lossless `png`).
 */
export async function createCdpScreenshotter(
  page,
  width,
  height,
  { format = "jpeg", quality = 95 } = {}
) {
  const cdp = await page.createCDPSession();
  const clip = { x: 0, y: 0, width, height, scale: 1 };
  const fmt = format === "png" ? "png" : "jpeg";
  const q = Math.max(50, Math.min(100, Math.round(Number(quality) || 95)));
  const captureParams =
    fmt === "png"
      ? { format: "png", optimizeForSpeed: true, clip }
      : { format: "jpeg", quality: q, optimizeForSpeed: true, clip };

  const captureBuffer = async () => {
    const { data } = await cdp.send("Page.captureScreenshot", captureParams);
    return Buffer.from(data, "base64");
  };

  return {
    format: fmt,
    captureBuffer,
    // Backward-compatible alias used by legacy callers.
    captureJpegBuffer: captureBuffer,
    async close() {
      try {
        await cdp.detach();
      } catch {
        /* ignore already-closed sessions */
      }
    },
  };
}

/**
 * Spawn an FFmpeg encoder accepting raw encoded image buffers on stdin (`mjpeg` or `png`)
 * and emitting a `bt709` `yuv420p` MP4.
 */
export function spawnFramePipeEncoder(
  outMp4,
  { codec = "mjpeg", fps = 30, crf = 16, gop = 1, preset = "fast", useVideoToolbox = false } = {}
) {
  const inputCodec = codec === "png" ? "png" : "mjpeg";
  const codecArgs =
    useVideoToolbox && process.platform === "darwin"
      ? ["-c:v", "h264_videotoolbox", "-q:v", "65", "-profile:v", "high"]
      : ["-c:v", "libx264", "-preset", preset, "-crf", String(crf)];

  const args = [
    "-hide_banner",
    "-loglevel",
    "error",
    "-y",
    "-f",
    "image2pipe",
    "-vcodec",
    inputCodec,
    "-framerate",
    String(fps),
    "-i",
    "pipe:0",
    ...codecArgs,
    "-pix_fmt",
    "yuv420p",
    "-r",
    String(fps),
    "-fps_mode",
    "cfr",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-colorspace",
    "bt709",
    "-color_range",
    "tv",
    "-g",
    String(gop),
    "-movflags",
    "+faststart",
    outMp4,
  ];

  const proc = spawn("ffmpeg", args, { stdio: ["pipe", "ignore", "pipe"] });
  let stderr = "";
  let exited = false;
  let exitError = null;
  proc.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  proc.stdin.on("error", (err) => {
    if (!exitError) exitError = err;
  });

  const done = new Promise((resolve, reject) => {
    proc.on("error", (err) => {
      exited = true;
      exitError = err;
      reject(err);
    });
    proc.on("close", (code) => {
      exited = true;
      if (code === 0) {
        resolve();
      } else {
        const err = new Error(`FFmpeg pipe encode failed (${code}) for ${outMp4}: ${stderr}`);
        exitError = err;
        reject(err);
      }
    });
  });
  // Prevent unhandled rejection if caller aborts before awaiting finish().
  done.catch(() => {});

  return {
    async writeFrame(frameBuffer) {
      if (exited || proc.stdin.destroyed || proc.stdin.writableEnded) {
        throw exitError || new Error(`FFmpeg pipe encoder exited early for ${outMp4}`);
      }
      if (!proc.stdin.write(frameBuffer)) {
        await new Promise((resolve, reject) => {
          const cleanup = () => {
            proc.stdin.off("drain", onDrain);
            proc.stdin.off("error", onError);
            proc.stdin.off("close", onPipeClose);
            proc.off("close", onProcClose);
          };
          const onDrain = () => {
            cleanup();
            resolve();
          };
          const onError = (err) => {
            cleanup();
            reject(
              err instanceof Error
                ? err
                : exitError || new Error(`FFmpeg pipe write error for ${outMp4}: ${String(err)}`)
            );
          };
          const onPipeClose = () => {
            cleanup();
            reject(exitError || new Error(`FFmpeg stdin closed early for ${outMp4}`));
          };
          const onProcClose = (code) => {
            cleanup();
            reject(
              exitError ||
                new Error(`FFmpeg pipe process closed early (code ${code}) for ${outMp4}`)
            );
          };
          proc.stdin.once("drain", onDrain);
          proc.stdin.once("error", onError);
          proc.stdin.once("close", onPipeClose);
          proc.once("close", onProcClose);
          if (exited || proc.stdin.destroyed) {
            onPipeClose();
          }
        });
      }
    },
    async finish() {
      if (!proc.stdin.destroyed && !proc.stdin.writableEnded) {
        proc.stdin.end();
      }
      await done;
    },
    async abort() {
      try {
        if (!proc.stdin.destroyed) proc.stdin.destroy();
      } catch {
        // ignore pipe teardown errors
      }
      if (!exited) {
        try {
          proc.kill("SIGKILL");
        } catch {
          // ignore if process already exited
        }
      }
      await done.catch(() => {});
    },
  };
}

/**
 * Backward-compatible MJPEG pipe encoder wrapper.
 */
export function spawnMjpegPipeEncoder(outMp4, opts = {}) {
  return spawnFramePipeEncoder(outMp4, { ...opts, codec: "mjpeg" });
}

/**
 * Losslessly concatenate ordered MP4 slices into a single faststart MP4.
 */
export function concatMp4Slices(slicePaths, outMp4, listFilePath) {
  const ff = spawnSync(
    "ffmpeg",
    [
      "-hide_banner",
      "-loglevel",
      "error",
      "-y",
      "-f",
      "concat",
      "-safe",
      "0",
      "-i",
      listFilePath,
      "-c",
      "copy",
      "-movflags",
      "+faststart",
      outMp4,
    ],
    { stdio: "inherit" }
  );
  if (ff.status !== 0) {
    throw new Error(`FFmpeg slice concat failed (${ff.status}) for ${outMp4}`);
  }
}
