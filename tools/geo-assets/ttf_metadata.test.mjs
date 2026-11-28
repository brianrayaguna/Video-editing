import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const GEO_DIR = fileURLToPath(new URL(".", import.meta.url));
const REPO_ROOT = fileURLToPath(new URL("../..", import.meta.url));

/**
 * Build a minimal valid SFNT binary buffer containing optional `fvar`, `OS/2`, and `name` tables.
 */
function buildSyntheticTtf({ familyName = null, staticWeight = null, varRange = null } = {}) {
  const tables = [];

  if (varRange) {
    const fvar = Buffer.alloc(16 + 20);
    fvar.writeUInt16BE(1, 0); // majorVersion
    fvar.writeUInt16BE(0, 2); // minorVersion
    fvar.writeUInt16BE(16, 4); // axesArrayOffset
    fvar.writeUInt16BE(2, 6); // reserved
    fvar.writeUInt16BE(1, 8); // axisCount
    fvar.writeUInt16BE(20, 10); // axisSize
    fvar.write("wght", 16, 4, "ascii");
    fvar.writeInt32BE(Math.round(varRange[0] * 65536), 20);
    fvar.writeInt32BE(Math.round(400 * 65536), 24);
    fvar.writeInt32BE(Math.round(varRange[1] * 65536), 28);
    tables.push({ tag: "fvar", data: fvar });
  }

  if (staticWeight !== null) {
    const os2 = Buffer.alloc(10);
    os2.writeUInt16BE(4, 0); // version
    os2.writeInt16BE(500, 2); // xAvgCharWidth
    os2.writeUInt16BE(staticWeight, 4); // usWeightClass
    tables.push({ tag: "OS/2", data: os2 });
  }

  if (familyName) {
    const strBuf = Buffer.from(familyName, "utf16le").swap16();
    const headerLen = 6 + 12;
    const name = Buffer.alloc(headerLen + strBuf.length);
    name.writeUInt16BE(0, 0); // format
    name.writeUInt16BE(1, 2); // count
    name.writeUInt16BE(headerLen, 4); // stringOffset
    name.writeUInt16BE(3, 6); // platformId (Windows)
    name.writeUInt16BE(1, 8); // encodingId
    name.writeUInt16BE(0x0409, 10); // languageId
    name.writeUInt16BE(16, 12); // nameId (typographic family)
    name.writeUInt16BE(strBuf.length, 14);
    name.writeUInt16BE(0, 16);
    strBuf.copy(name, headerLen);
    tables.push({ tag: "name", data: name });
  }

  const headerSize = 12 + tables.length * 16;
  const totalSize = headerSize + tables.reduce((acc, t) => acc + t.data.length, 0);
  const out = Buffer.alloc(totalSize);
  out.writeUInt32BE(0x00010000, 0);
  out.writeUInt16BE(tables.length, 4);
  let cursor = headerSize;
  for (let i = 0; i < tables.length; i += 1) {
    const rec = 12 + i * 16;
    out.write(tables[i].tag, rec, 4, "ascii");
    out.writeUInt32BE(0, rec + 4);
    out.writeUInt32BE(cursor, rec + 8);
    out.writeUInt32BE(tables[i].data.length, rec + 12);
    tables[i].data.copy(out, cursor);
    cursor += tables[i].data.length;
  }
  return out;
}

test("tools/geo-assets has its own hermetic package.json and zero cross-package createRequire", () => {
  const pkgPath = join(GEO_DIR, "package.json");
  assert.ok(existsSync(pkgPath), "tools/geo-assets/package.json must exist");
  const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
  assert.ok(pkg.dependencies?.["puppeteer-core"], "puppeteer-core must be declared in tools/geo-assets/package.json");
  assert.ok(pkg.dependencies?.sharp, "sharp must be declared in tools/geo-assets/package.json");

  const scripts = readdirSync(GEO_DIR).filter(
    (f) => f.endsWith(".mjs") && f !== "ttf_metadata.test.mjs"
  );
  for (const script of scripts) {
    const src = readFileSync(join(GEO_DIR, script), "utf8");
    assert.doesNotMatch(
      src,
      /createRequire\([\s\S]{0,120}hf-compiler-ts/,
      `${script} must not borrow dependencies via createRequire from hf-compiler-ts`
    );
  }
});

test("geo-assets and hf-compiler-ts SFNT TTF metadata parsers stay in exact parity", async () => {
  const { readTtfMetadata: readGeoMeta, readTtfWeightAxis } = await import("./lib/ttf_metadata.mjs");
  const { readTtfMetadata: readTsMeta } = await import(
    join(REPO_ROOT, "packages/hf-compiler-ts/dist/ttf_metadata.js")
  );

  const tmpDir = mkdtempSync(join(tmpdir(), "vedit-ttf-parity-"));
  try {
    const varPath = join(tmpDir, "SampleVariable.ttf");
    const staticPath = join(tmpDir, "SampleBold.ttf");
    writeFileSync(varPath, buildSyntheticTtf({ familyName: "Editorial Sans", varRange: [100, 900] }));
    writeFileSync(staticPath, buildSyntheticTtf({ familyName: "Editorial Mono", staticWeight: 700 }));

    assert.deepEqual(readGeoMeta(varPath), readTsMeta(varPath));
    assert.deepEqual(readGeoMeta(varPath), {
      familyName: "Editorial Sans",
      weightAxis: { isVariable: true, minWeight: 100, maxWeight: 900 },
    });
    assert.deepEqual(readTtfWeightAxis(varPath), { isVariable: true, minWeight: 100, maxWeight: 900 });

    assert.deepEqual(readGeoMeta(staticPath), readTsMeta(staticPath));
    assert.deepEqual(readGeoMeta(staticPath), {
      familyName: "Editorial Mono",
      weightAxis: { isVariable: false, minWeight: 700, maxWeight: 700 },
    });
    assert.deepEqual(readTtfWeightAxis(staticPath), { isVariable: false, minWeight: 700, maxWeight: 700 });
  } finally {
    rmSync(tmpDir, { recursive: true, force: true });
  }
});
