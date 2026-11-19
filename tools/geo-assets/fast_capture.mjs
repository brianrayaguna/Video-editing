/**
 * High-throughput Chromium CDP JPEG capture & direct FFmpeg image2pipe helpers
 * for offline local MapLibre A-roll baking.
 */

import { spawn, spawnSync } from "node:child_process";

/**
 * Return platform-appropriate Chromium flags (Metal ANGLE on macOS, SwiftShader on Linux).
 */
export function getChromeArgs(width, height) {
  const winArg = width && height ? [`--window-size=${width},${height}`] : [];
  if (process.platform === "darwin") {
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
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--enable-webgl",
    ...winArg,
  ];
}

/**
 * Create a persistent CDP session for fast JPEG capture with `optimizeForSpeed: true`.
 */
export async function createCdpScreenshotter(page, width, height, { quality = 92 } = {}) {
  const cdp = await page.createCDPSession();
  const clip = { x: 0, y: 0, width, height, scale: 1 };
  return {
    async captureJpegBuffer() {
      const { data } = await cdp.send("Page.captureScreenshot", {
        format: "jpeg",
        quality,
        optimizeForSpeed: true,
        clip,
      });
      return Buffer.from(data, "base64");
    },
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
 * Spawn an FFmpeg encoder accepting raw JPEG buffers on stdin (`image2pipe` MJPEG)
 * and emitting a `bt709` `yuv420p` MP4.
 */
export function spawnMjpegPipeEncoder(
  outMp4,
  { fps = 30, crf = 16, gop = 1, preset = "fast", useVideoToolbox = false } = {}
) {
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
    "mjpeg",
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
  proc.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });

  const done = new Promise((resolve, reject) => {
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`FFmpeg pipe encode failed (${code}) for ${outMp4}: ${stderr}`));
    });
  });

  return {
    async writeFrame(jpegBuffer) {
      if (!proc.stdin.write(jpegBuffer)) {
        await new Promise((resolve) => proc.stdin.once("drain", resolve));
      }
    },
    async finish() {
      proc.stdin.end();
      await done;
    },
  };
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
