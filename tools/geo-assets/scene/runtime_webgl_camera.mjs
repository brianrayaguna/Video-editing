export function buildWebglCameraRuntime({ terrain3d }) {
  return `
    window.__currentRoll = 0;

    function clampMercatorCamera(cam) {
      if (ALLOW_WORLD_VOID) return cam;
      const bearing = cam.bearing || 0;
      const pitch = Math.max(0, Math.min(72, cam.pitch || 0));
      const roll = Math.max(-12, Math.min(12, cam.roll || 0));
      const minZoom = Math.log2(H / 512) + 0.08;
      const z = Math.max(cam.zoom, minZoom);
      const worldPx = 512 * Math.pow(2, z);
      const halfY = (H * 0.5) / worldPx + 0.012;
      const lat = Math.max(-85.0, Math.min(85.0, cam.center[1]));
      const sinLat = Math.sin(lat * Math.PI / 180);
      let yNorm = 0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI);
      if (halfY < 0.49) {
        yNorm = Math.max(halfY, Math.min(1 - halfY, yNorm));
      } else {
        yNorm = 0.5;
      }
      const n = Math.PI - 2 * Math.PI * yNorm;
      const clampedLat = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
      return {
        center: [cam.center[0], clampedLat],
        zoom: z,
        bearing,
        pitch,
        roll,
      };
    }

    function computeRollOverscan(rollDeg) {
      const r = Math.abs(rollDeg || 0) * Math.PI / 180;
      return Math.cos(r) + Math.sin(r) * Math.max(W / H, H / W);
    }

    // Smooth camera sampling (pre-expanded camera_samples or scale-coupled inline keyframes)
    window.__setSceneCamera = function(cam) {
      const safe = clampMercatorCamera(cam);
      window.__currentRoll = safe.roll || 0;
      if (Math.abs(window.__currentRoll) > 0.01) {
        const sc = computeRollOverscan(window.__currentRoll);
        stageEl.style.transform = "rotate(" + window.__currentRoll.toFixed(3) + "deg) scale(" + sc.toFixed(5) + ")";
      } else {
        stageEl.style.transform = "";
      }
      map.jumpTo({
        center: safe.center,
        zoom: safe.zoom,
        bearing: safe.bearing,
        pitch: safe.pitch,
      });
    };

    function initThreeMapLayer() {
      const originLng = ORIGIN_COORD[0] || 0;
      const originLat = ORIGIN_COORD[1] || 0;
      const originMerc = maplibregl.MercatorCoordinate.fromLngLat([originLng, originLat], 0);
      const meterScale = originMerc.meterInMercatorCoordinateUnits();
      const sceneOriginMat = new THREE.Matrix4()
        .makeTranslation(originMerc.x, originMerc.y, originMerc.z)
        .scale(new THREE.Vector3(meterScale, -meterScale, meterScale));

      function lngLatAltToLocal(lng, lat, altM = 0) {
        const mc = maplibregl.MercatorCoordinate.fromLngLat([lng, lat], altM);
        return new THREE.Vector3(
          (mc.x - originMerc.x) / meterScale,
          -(mc.y - originMerc.y) / meterScale,
          (mc.z - originMerc.z) / meterScale
        );
      }

      function groundElevM(lng, lat) {
        if (${terrain3d} && typeof map.queryTerrainElevation === "function") {
          const e = map.queryTerrainElevation([lng, lat], { exaggerated: true });
          if (Number.isFinite(e) && e > 0) return e;
        }
        return 0;
      }

      function metersForScreenPx(px, lat, curZoom, refZoom, coupling = 0.45, minScale = 0.4, maxScale = 3.2) {
        const baseZ = refZoom != null ? refZoom : curZoom;
        const mpp = (156543.03392 * Math.max(0.2, Math.cos((lat * Math.PI) / 180))) / Math.pow(2, curZoom);
        const ratio = Math.pow(2, (curZoom - baseZ) * coupling);
        return px * mpp * clamp(ratio, minScale, maxScale);
      }

      // Procedural PBR textures built once per WebGL scene
      function makeShadowDiscTex() {
        const c = document.createElement("canvas");
        c.width = 128; c.height = 128;
        const cx = c.getContext("2d");
        const g = cx.createRadialGradient(64, 64, 4, 64, 64, 62);
        g.addColorStop(0, "rgba(2,8,14,0.68)");
        g.addColorStop(0.55, "rgba(2,8,14,0.30)");
        g.addColorStop(1, "rgba(2,8,14,0)");
        cx.fillStyle = g;
        cx.fillRect(0, 0, 128, 128);
        const tex = new THREE.CanvasTexture(c);
        tex.needsUpdate = true;
        return tex;
      }

      function makeSolarCellTex() {
        const c = document.createElement("canvas");
        c.width = 256; c.height = 256;
        const cx = c.getContext("2d");
        const bg = cx.createLinearGradient(0, 0, 256, 256);
        bg.addColorStop(0, "#102B63");
        bg.addColorStop(0.5, "#1D4D9F");
        bg.addColorStop(1, "#0B1D42");
        cx.fillStyle = bg;
        cx.fillRect(0, 0, 256, 256);
        cx.strokeStyle = "rgba(186, 230, 253, 0.55)";
        cx.lineWidth = 2;
        for (let i = 1; i < 8; i++) {
          const p = (i * 256) / 8;
          cx.beginPath(); cx.moveTo(p, 0); cx.lineTo(p, 256); cx.stroke();
          cx.beginPath(); cx.moveTo(0, p); cx.lineTo(256, p); cx.stroke();
        }
        cx.strokeStyle = "#CBD5E1";
        cx.lineWidth = 8;
        cx.strokeRect(4, 4, 248, 248);
        const tex = new THREE.CanvasTexture(c);
        tex.anisotropy = 4;
        return tex;
      }

      function makeVolumeTopTex(edgeHex) {
        const c = document.createElement("canvas");
        c.width = 256; c.height = 256;
        const cx = c.getContext("2d");
        cx.fillStyle = "rgba(245, 158, 11, 0.24)";
        cx.fillRect(0, 0, 256, 256);
        cx.strokeStyle = edgeHex || "#FEF08A";
        cx.lineWidth = 2;
        for (let i = 1; i < 8; i++) {
          const p = (i * 256) / 8;
          cx.beginPath(); cx.moveTo(p, 0); cx.lineTo(p, 256); cx.stroke();
          cx.beginPath(); cx.moveTo(0, p); cx.lineTo(256, p); cx.stroke();
        }
        cx.lineWidth = 6;
        cx.strokeRect(3, 3, 250, 250);
        const tex = new THREE.CanvasTexture(c);
        return tex;
      }

      const armorTexCache = new Map();
      function getArmorTexSet(armorHex, jacketHex) {
        const key = (armorHex || "#D4A037") + "|" + (jacketHex || "#1E293B");
        if (armorTexCache.has(key)) return armorTexCache.get(key);
        const W_TEX = 256, H_TEX = 256;
        const cCol = document.createElement("canvas");
        cCol.width = W_TEX; cCol.height = H_TEX;
        const xCol = cCol.getContext("2d");
        xCol.fillStyle = jacketHex || "#1E293B";
        xCol.fillRect(0, 0, W_TEX, H_TEX);

        const cBump = document.createElement("canvas");
        cBump.width = W_TEX; cBump.height = H_TEX;
        const xBump = cBump.getContext("2d");
        xBump.fillStyle = "#303030";
        xBump.fillRect(0, 0, W_TEX, H_TEX);

        // Diagonal helical steel-wire & armored brass/copper strands wrapping continuously across UV tile
        const strands = 12;
        for (let i = -strands; i <= strands * 2; i++) {
          const u0 = (i / strands) * W_TEX;
          const isAccent = (Math.abs(i) % 3 === 0);
          xCol.strokeStyle = isAccent ? (armorHex || "#E5B449") : "#64748B";
          xCol.lineWidth = isAccent ? 12 : 9;
          xCol.beginPath(); xCol.moveTo(u0, 0); xCol.lineTo(u0 + W_TEX, H_TEX); xCol.stroke();

          // Dark crevice between wrapped wires
          xCol.strokeStyle = "#0F172A";
          xCol.lineWidth = 3;
          xCol.beginPath(); xCol.moveTo(u0 + 6, 0); xCol.lineTo(u0 + 6 + W_TEX, H_TEX); xCol.stroke();

          // Cylindrical ridge in bump map
          xBump.strokeStyle = "#FFFFFF";
          xBump.lineWidth = 10;
          xBump.beginPath(); xBump.moveTo(u0, 0); xBump.lineTo(u0 + W_TEX, H_TEX); xBump.stroke();
        }
        // Subtle specular highlight band along longitudinal center
        const shine = xCol.createLinearGradient(0, 0, 0, H_TEX);
        shine.addColorStop(0, "rgba(0,0,0,0.22)");
        shine.addColorStop(0.5, "rgba(255,255,255,0.20)");
        shine.addColorStop(1, "rgba(0,0,0,0.22)");
        xCol.fillStyle = shine;
        xCol.fillRect(0, 0, W_TEX, H_TEX);

        const makeWrapped = (canvas) => {
          const t = new THREE.CanvasTexture(canvas);
          t.wrapS = THREE.RepeatWrapping;
          t.wrapT = THREE.RepeatWrapping;
          t.anisotropy = 8;
          return t;
        };
        const out = { colCanvas: cCol, bumpCanvas: cBump, makeWrapped };
        armorTexCache.set(key, out);
        return out;
      }

      const shadowTex = makeShadowDiscTex();
      const solarTex = makeSolarCellTex();

      function makeBeamBetween(a, b, r, mat) {
        const dir = new THREE.Vector3().subVectors(b, a);
        const len = dir.length();
        const geo = new THREE.CylinderGeometry(r, r, len, 6, 1);
        geo.rotateX(Math.PI / 2);
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.copy(a).add(b).multiplyScalar(0.5);
        mesh.lookAt(b);
        return mesh;
      }

      function addGroundShadow(group, radiusXY) {
        const sGeo = new THREE.PlaneGeometry(radiusXY * 2, radiusXY * 2);
        const sMat = new THREE.MeshBasicMaterial({
          map: shadowTex,
          transparent: true,
          depthWrite: false,
          opacity: 0.72,
        });
        const m = new THREE.Mesh(sGeo, sMat);
        m.position.set(0, 0, 0.004);
        group.add(m);
      }

      function buildTransmissionTowerModel(layer) {
        const root = new THREE.Group();
        const powered = layer.powered !== false;
        const accentHex = layer.accent_hex || "#FDE047";
        const steelMat = new THREE.MeshStandardMaterial({
          color: powered ? 0xe2e8f0 : 0x475569,
          metalness: powered ? 0.82 : 0.45,
          roughness: powered ? 0.28 : 0.65,
        });
        const concreteMat = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.85, metalness: 0.1 });
        const termMat = powered
          ? new THREE.MeshStandardMaterial({
              color: new THREE.Color(accentHex),
              emissive: new THREE.Color(accentHex),
              emissiveIntensity: 0.9,
              roughness: 0.2,
              metalness: 0.3,
            })
          : new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.7, metalness: 0.2 });

        addGroundShadow(root, 0.42);
        const cornersBase = [[-0.17, -0.17], [0.17, -0.17], [0.17, 0.17], [-0.17, 0.17]];
        for (const [cx, cy] of cornersBase) {
          const pad = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.11, 0.045), concreteMat);
          pad.position.set(cx, cy, 0.022);
          root.add(pad);
        }
        const levelZ = [0.03, 0.24, 0.46, 0.66, 0.85, 1.0];
        const levelW = [0.165, 0.125, 0.092, 0.068, 0.046, 0.008];
        for (let bay = 0; bay < levelZ.length - 1; bay++) {
          const z0 = levelZ[bay], z1 = levelZ[bay + 1];
          const w0 = levelW[bay], w1 = levelW[bay + 1];
          const bPts = [[-w0, -w0, z0], [w0, -w0, z0], [w0, w0, z0], [-w0, w0, z0]];
          const tPts = [[-w1, -w1, z1], [w1, -w1, z1], [w1, w1, z1], [-w1, w1, z1]];
          for (let k = 0; k < 4; k++) {
            const kn = (k + 1) % 4;
            const a = new THREE.Vector3(...bPts[k]);
            const b = new THREE.Vector3(...tPts[k]);
            const an = new THREE.Vector3(...bPts[kn]);
            const bn = new THREE.Vector3(...tPts[kn]);
            root.add(makeBeamBetween(a, b, 0.017, steelMat));
            root.add(makeBeamBetween(b, bn, 0.011, steelMat));
            if (bay < 4) {
              root.add(makeBeamBetween(a, bn, 0.009, steelMat));
              root.add(makeBeamBetween(an, b, 0.009, steelMat));
            }
          }
        }
        // Two 3D cross-arm assemblies with hanging ceramic insulators & energized corona spheres
        const arms = [[0.64, 0.36, 0.068], [0.83, 0.26, 0.048]];
        const insMat = new THREE.MeshStandardMaterial({ color: powered ? 0xf8fafc : 0x475569, roughness: 0.35, metalness: 0.2 });
        for (const [az, span, bodyW] of arms) {
          for (const side of [-1, 1]) {
            const tip = new THREE.Vector3(side * span, 0, az);
            const innerUp = new THREE.Vector3(side * bodyW, 0, az + 0.07);
            const innerF = new THREE.Vector3(side * bodyW, bodyW, az);
            const innerB = new THREE.Vector3(side * bodyW, -bodyW, az);
            root.add(makeBeamBetween(tip, innerUp, 0.013, steelMat));
            root.add(makeBeamBetween(tip, innerF, 0.013, steelMat));
            root.add(makeBeamBetween(tip, innerB, 0.013, steelMat));
            const insTop = new THREE.Vector3(side * (span * 0.94), 0, az);
            const insBot = new THREE.Vector3(side * (span * 0.94), 0, az - 0.11);
            root.add(makeBeamBetween(insTop, insBot, 0.014, insMat));
            const orb = new THREE.Mesh(new THREE.SphereGeometry(0.030, 12, 10), termMat);
            orb.position.copy(insBot);
            root.add(orb);
          }
        }
        const apexOrb = new THREE.Mesh(new THREE.SphereGeometry(0.028, 12, 10), termMat);
        apexOrb.position.set(0, 0, 1.015);
        root.add(apexOrb);
        return root;
      }

      function buildSubstationModel(layer) {
        const root = new THREE.Group();
        const powered = layer.powered !== false;
        const accentHex = layer.accent_hex || "#38BDF8";
        addGroundShadow(root, 0.85);
        const padMat = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.88, metalness: 0.08 });
        const hallMat = new THREE.MeshStandardMaterial({
          color: powered ? 0x1e293b : 0x334155,
          metalness: 0.65,
          roughness: 0.35,
        });
        const roofMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.72, roughness: 0.3 });
        const glowMat = powered
          ? new THREE.MeshStandardMaterial({
              color: new THREE.Color(accentHex),
              emissive: new THREE.Color(accentHex),
              emissiveIntensity: 0.85,
              roughness: 0.25,
            })
          : new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.75 });

        const pad = new THREE.Mesh(new THREE.BoxGeometry(1.36, 0.96, 0.06), padMat);
        pad.position.set(0, 0, 0.03);
        root.add(pad);

        const hall = new THREE.Mesh(new THREE.BoxGeometry(0.92, 0.56, 0.56), hallMat);
        hall.position.set(-0.12, 0.06, 0.34);
        root.add(hall);

        const roof = new THREE.Mesh(new THREE.BoxGeometry(0.98, 0.62, 0.06), roofMat);
        roof.position.set(-0.12, 0.06, 0.65);
        root.add(roof);

        const strip = new THREE.Mesh(new THREE.BoxGeometry(0.94, 0.58, 0.065), glowMat);
        strip.position.set(-0.12, 0.06, 0.52);
        root.add(strip);

        // 3 outdoor cylindrical HVDC converter transformers + high-voltage ceramic bushings
        for (let i = 0; i < 3; i++) {
          const tx = 0.44;
          const ty = -0.26 + i * 0.26;
          const tank = new THREE.Mesh(new THREE.CylinderGeometry(0.085, 0.095, 0.36, 14), roofMat);
          tank.rotation.x = Math.PI / 2;
          tank.position.set(tx, ty, 0.24);
          root.add(tank);

          const bush = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.024, 0.28, 10), roofMat);
          bush.rotation.x = Math.PI / 2;
          bush.position.set(tx, ty, 0.55);
          root.add(bush);

          const tip = new THREE.Mesh(new THREE.SphereGeometry(0.036, 10, 8), glowMat);
          tip.position.set(tx, ty, 0.71);
          root.add(tip);
        }
        return root;
      }

      function buildSolarFarmModel(layer) {
        const root = new THREE.Group();
        addGroundShadow(root, 1.25);
        const baseMat = new THREE.MeshStandardMaterial({ color: 0x5c3a28, roughness: 0.95, metalness: 0.04 });
        const steelMat = new THREE.MeshStandardMaterial({ color: 0xcbd5e1, metalness: 0.8, roughness: 0.3 });
        const panelMat = new THREE.MeshStandardMaterial({
          map: solarTex,
          metalness: 0.52,
          roughness: 0.18,
          emissive: new THREE.Color("#0F2A6B"),
          emissiveIntensity: 0.18,
        });
        const accentMat = new THREE.MeshStandardMaterial({
          color: 0xfde047,
          emissive: 0xf59e0b,
          emissiveIntensity: 0.75,
        });

        const apron = new THREE.Mesh(new THREE.BoxGeometry(2.0, 1.65, 0.04), baseMat);
        apron.position.set(0, 0, 0.02);
        root.add(apron);

        const rows = 4, cols = 4;
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            const px = -0.66 + c * 0.44;
            const py = -0.54 + r * 0.34;
            const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.022, 0.18, 6), steelMat);
            leg.rotation.x = Math.PI / 2;
            leg.position.set(px, py, 0.12);
            root.add(leg);

            const tbl = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.25, 0.024), panelMat);
            tbl.position.set(px, py, 0.21);
            tbl.rotation.x = 0.48;
            root.add(tbl);
          }
        }
        // Inverter / collector cabin + glowing energy bus
        const inv = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.22, 0.22), steelMat);
        inv.position.set(0.82, 0.62, 0.15);
        root.add(inv);
        const beacon = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.24, 0.05), accentMat);
        beacon.position.set(0.82, 0.62, 0.27);
        root.add(beacon);
        return root;
      }

      function buildSurveyVesselModel(layer) {
        const root = new THREE.Group();
        addGroundShadow(root, 0.95);
        const hullMat = new THREE.MeshStandardMaterial({ color: 0x0f2744, metalness: 0.45, roughness: 0.38 });
        const keelMat = new THREE.MeshStandardMaterial({ color: 0xb91c1c, roughness: 0.55, metalness: 0.2 });
        const deckMat = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.72, metalness: 0.25 });
        const bridgeMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.32, metalness: 0.15 });
        const glassMat = new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0ea5e9, emissiveIntensity: 0.45, metalness: 0.8, roughness: 0.15 });
        const drumMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, emissive: 0xd97706, emissiveIntensity: 0.25, metalness: 0.65, roughness: 0.28 });

        // Hull plan extruded along Z (Bow pointing toward +Y)
        const shape = new THREE.Shape();
        shape.moveTo(-0.22, -0.78);
        shape.lineTo(0.22, -0.78);
        shape.lineTo(0.24, 0.36);
        shape.quadraticCurveTo(0.14, 0.82, 0, 0.98);
        shape.quadraticCurveTo(-0.14, 0.82, -0.24, 0.36);
        shape.closePath();

        const keelGeo = new THREE.ExtrudeGeometry(shape, { depth: 0.08, bevelEnabled: false });
        const keel = new THREE.Mesh(keelGeo, keelMat);
        keel.position.z = 0.01;
        root.add(keel);

        const hullGeo = new THREE.ExtrudeGeometry(shape, { depth: 0.16, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.015, bevelSegments: 2 });
        const hull = new THREE.Mesh(hullGeo, hullMat);
        hull.position.z = 0.09;
        root.add(hull);

        const deck = new THREE.Mesh(new THREE.BoxGeometry(0.40, 1.05, 0.03), deckMat);
        deck.position.set(0, -0.18, 0.27);
        root.add(deck);

        // Bridge superstructure near bow
        const br1 = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.36, 0.24), bridgeMat);
        br1.position.set(0, 0.30, 0.39);
        root.add(br1);
        const br2 = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.24, 0.14), bridgeMat);
        br2.position.set(0, 0.32, 0.56);
        root.add(br2);
        const win = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.14, 0.07), glassMat);
        win.position.set(0, 0.40, 0.57);
        root.add(win);

        // Radar mast & aft cable carousel drum
        const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.018, 0.28, 8), bridgeMat);
        mast.rotation.x = Math.PI / 2;
        mast.position.set(0, 0.28, 0.76);
        root.add(mast);

        const drum = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.16, 20), drumMat);
        drum.rotation.z = Math.PI / 2;
        drum.position.set(0, -0.34, 0.40);
        root.add(drum);

        // Stern A-frame gantry crane
        const gantryL = makeBeamBetween(new THREE.Vector3(-0.18, -0.72, 0.27), new THREE.Vector3(-0.12, -0.76, 0.58), 0.016, bridgeMat);
        const gantryR = makeBeamBetween(new THREE.Vector3(0.18, -0.72, 0.27), new THREE.Vector3(0.12, -0.76, 0.58), 0.016, bridgeMat);
        const gantryT = makeBeamBetween(new THREE.Vector3(-0.12, -0.76, 0.58), new THREE.Vector3(0.12, -0.76, 0.58), 0.016, bridgeMat);
        root.add(gantryL, gantryR, gantryT);

        // Subtle V-shaped foam wake on sea behind stern
        const wakeMat = new THREE.MeshBasicMaterial({ color: 0xe0f2fe, transparent: true, opacity: 0.48, side: THREE.DoubleSide, depthWrite: false });
        for (const s of [-1, 1]) {
          const wMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.06, 0.85), wakeMat);
          wMesh.position.set(s * 0.26, -1.16, 0.02);
          wMesh.rotation.z = s * 0.28;
          root.add(wMesh);
        }
        return root;
      }

      function buildAircraftModel(layer) {
        const root = new THREE.Group();
        const bodyMat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(layer.body_hex || "#F8FAFC"),
          metalness: 0.32,
          roughness: 0.24,
        });
        const wingMat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(layer.wing_hex || "#CBD5E1"),
          metalness: 0.42,
          roughness: 0.30,
        });
        const accentMat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(layer.accent_hex || "#0284C7"),
          emissive: new THREE.Color(layer.accent_hex || "#0284C7"),
          emissiveIntensity: 0.32,
          metalness: 0.35,
          roughness: 0.28,
        });
        const glassMat = new THREE.MeshStandardMaterial({
          color: 0x0f172a,
          emissive: 0x38bdf8,
          emissiveIntensity: 0.45,
          metalness: 0.85,
          roughness: 0.12,
        });
        const engMat = new THREE.MeshStandardMaterial({
          color: 0x334155,
          metalness: 0.72,
          roughness: 0.25,
        });

        // Sculpted fuselage aligned along +Y (nose at +Y, Z-up)
        const fuse = new THREE.Mesh(new THREE.CylinderGeometry(0.095, 0.088, 1.15, 20), bodyMat);
        fuse.position.set(0, 0.02, 0.14);
        root.add(fuse);

        const nose = new THREE.Mesh(new THREE.SphereGeometry(0.095, 20, 14), bodyMat);
        nose.scale.set(1, 2.25, 0.94);
        nose.position.set(0, 0.59, 0.13);
        root.add(nose);

        const tailCone = new THREE.Mesh(new THREE.ConeGeometry(0.088, 0.46, 20), bodyMat);
        tailCone.rotation.x = Math.PI;
        tailCone.position.set(0, -0.78, 0.15);
        root.add(tailCone);

        // Cockpit visor
        const cockpit = new THREE.Mesh(new THREE.SphereGeometry(0.078, 16, 10), glassMat);
        cockpit.scale.set(1.02, 1.55, 0.65);
        cockpit.position.set(0, 0.61, 0.18);
        root.add(cockpit);

        // Swept main wings with upturned winglets
        for (const s of [-1, 1]) {
          const wShape = new THREE.Shape();
          wShape.moveTo(0, 0.26);
          wShape.lineTo(s * 0.94, -0.22);
          wShape.lineTo(s * 0.94, -0.34);
          wShape.lineTo(0, -0.10);
          wShape.closePath();
          const wGeo = new THREE.ExtrudeGeometry(wShape, {
            depth: 0.028,
            bevelEnabled: true,
            bevelThickness: 0.008,
            bevelSize: 0.008,
            bevelSegments: 2,
          });
          const wing = new THREE.Mesh(wGeo, wingMat);
          wing.position.set(0, 0, 0.10);
          root.add(wing);

          // Upturned winglet + navigation light
          const winglet = new THREE.Mesh(new THREE.BoxGeometry(0.022, 0.14, 0.14), accentMat);
          winglet.position.set(s * 0.94, -0.28, 0.17);
          winglet.rotation.y = s * 0.26;
          root.add(winglet);

          const navCol = s < 0 ? 0xef4444 : 0x22c55e;
          const navMat = new THREE.MeshBasicMaterial({ color: navCol });
          const nav = new THREE.Mesh(new THREE.SphereGeometry(0.024, 10, 8), navMat);
          nav.position.set(s * 0.96, -0.27, 0.22);
          root.add(nav);

          // Underwing turbofan engine nacelle
          const eng = new THREE.Mesh(new THREE.CylinderGeometry(0.052, 0.044, 0.24, 16), engMat);
          eng.position.set(s * 0.34, 0.06, 0.06);
          root.add(eng);

          // Horizontal tail stabilizer
          const hShape = new THREE.Shape();
          hShape.moveTo(0, -0.62);
          hShape.lineTo(s * 0.34, -0.86);
          hShape.lineTo(s * 0.34, -0.94);
          hShape.lineTo(0, -0.82);
          hShape.closePath();
          const hTail = new THREE.Mesh(
            new THREE.ExtrudeGeometry(hShape, { depth: 0.018, bevelEnabled: false }),
            wingMat
          );
          hTail.position.set(0, 0, 0.15);
          root.add(hTail);
        }

        // Swept vertical tail fin
        const vFin = new THREE.Mesh(new THREE.BoxGeometry(0.024, 0.28, 0.34), accentMat);
        vFin.position.set(0, -0.78, 0.33);
        vFin.rotation.x = -0.35;
        root.add(vFin);

        return root;
      }

      function computeParallelFrames(pts) {
        const n = pts.length;
        const tangents = [];
        const normals = [];
        const binormals = [];
        const worldUp = new THREE.Vector3(0, 0, 1);
        for (let i = 0; i < n; i++) {
          const a = pts[Math.max(0, i - 1)];
          const b = pts[Math.min(n - 1, i + 1)];
          const tan = new THREE.Vector3().subVectors(b, a).normalize();
          if (tan.lengthSq() < 1e-8) tan.set(1, 0, 0);
          tangents.push(tan);
        }
        let n0 = new THREE.Vector3().crossVectors(tangents[0], worldUp);
        if (n0.lengthSq() < 1e-5) n0.set(1, 0, 0);
        n0.normalize();
        normals.push(n0);
        binormals.push(new THREE.Vector3().crossVectors(tangents[0], n0).normalize());
        for (let i = 1; i < n; i++) {
          const prevN = normals[i - 1].clone();
          const tPrev = tangents[i - 1];
          const tCur = tangents[i];
          const axis = new THREE.Vector3().crossVectors(tPrev, tCur);
          if (axis.lengthSq() > 1e-9) {
            axis.normalize();
            const ang = Math.acos(clamp(tPrev.dot(tCur), -1, 1));
            prevN.applyAxisAngle(axis, ang);
          }
          prevN.normalize();
          normals.push(prevN);
          binormals.push(new THREE.Vector3().crossVectors(tCur, prevN).normalize());
        }
        return { tangents, normals, binormals };
      }

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera();
      camera.matrixAutoUpdate = false;

      scene.add(new THREE.AmbientLight(0xffffff, 0.22));
      scene.add(new THREE.HemisphereLight(0xdbeafe, 0x162432, 0.52));
      const keySun = new THREE.DirectionalLight(0xfff5e0, 1.25);
      keySun.position.set(SUN_VEC.x * 1000, SUN_VEC.y * 1000, SUN_VEC.z * 1000);
      keySun.castShadow = true;
      keySun.shadow.mapSize.set(2048, 2048);
      keySun.shadow.bias = -0.0005;
      keySun.shadow.normalBias = 0.02;
      scene.add(keySun);
      scene.add(keySun.target);

      const rimSun = new THREE.DirectionalLight(0x7dd3fc, 0.36);
      rimSun.position.set(-SUN_VEC.x * 1000, -SUN_VEC.y * 1000, Math.max(0.45, SUN_VEC.z * 0.7) * 1000);
      scene.add(rimSun);

      // Physical ground shadow receiver plane dynamically fitted to active 3D bounds
      const shadowGroundMat = new THREE.ShadowMaterial({ opacity: 0.44, depthWrite: false });
      const shadowGround = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), shadowGroundMat);
      shadowGround.receiveShadow = true;
      shadowGround.frustumCulled = false;
      shadowGround.visible = false;
      scene.add(shadowGround);

      // Shared camera position vector in local scene meters (extracted each frame from projectionMatrix)
      const camLocalPos = new THREE.Vector3(0, 0, 500000);
      const invProjMat = new THREE.Matrix4();
      function updateCameraLocalPos(projMat) {
        invProjMat.copy(projMat).invert();
        const e = invProjMat.elements;
        if (Math.abs(e[11]) > 1e-9) {
          camLocalPos.set(e[8] / e[11], e[9] / e[11], Math.abs(e[10] / e[11]));
        }
      }

      // Native zero-addon Dual-Kawase HDR Bloom + ACESFilmic composite pipeline
      let renderer = null;
      let bloomState = null;

      function disposeBloomTargets(st) {
        if (!st) return;
        if (st.sceneRT) st.sceneRT.dispose();
        for (const rt of st.downRTs || []) rt.dispose();
        for (const rt of st.upRTs || []) rt.dispose();
      }

      function initDualKawaseBloom(gl) {
        const fsCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
        const fsGeo = new THREE.PlaneGeometry(2, 2);
        const fsVert = [
          "varying vec2 vUv;",
          "void main() {",
          "  vUv = uv;",
          "  gl_Position = vec4(position.xy, 0.0, 1.0);",
          "}",
        ].join("\\n");

        const brightMat = new THREE.ShaderMaterial({
          vertexShader: fsVert,
          fragmentShader: [
            "uniform sampler2D tInput;",
            "uniform float uThreshold;",
            "uniform float uKnee;",
            "varying vec2 vUv;",
            "void main() {",
            "  vec4 c = texture2D(tInput, vUv);",
            "  vec3 col = c.rgb;",
            "  float br = max(col.r, max(col.g, col.b));",
            "  float soft = clamp(br - uThreshold + uKnee, 0.0, 2.0 * uKnee);",
            "  soft = (soft * soft) / max(4.0 * uKnee, 1e-4);",
            "  float contrib = max(soft, br - uThreshold) / max(br, 1e-4);",
            "  gl_FragColor = vec4(col * max(contrib, 0.0), 1.0);",
            "}",
          ].join("\\n"),
          uniforms: {
            tInput: { value: null },
            uThreshold: { value: 1.15 },
            uKnee: { value: 0.22 },
          },
          depthTest: false,
          depthWrite: false,
        });

        // Dual-Kawase 5-tap downsample kernel (1/2 center + four 1/8 half-pixel corners)
        const downMat = new THREE.ShaderMaterial({
          vertexShader: fsVert,
          fragmentShader: [
            "uniform sampler2D tInput;",
            "uniform vec2 uHalfPixel;",
            "uniform float uOffset;",
            "varying vec2 vUv;",
            "void main() {",
            "  vec2 d = uHalfPixel * uOffset;",
            "  vec4 sum = texture2D(tInput, vUv) * 4.0;",
            "  sum += texture2D(tInput, vUv - d);",
            "  sum += texture2D(tInput, vUv + d);",
            "  sum += texture2D(tInput, vUv + vec2(d.x, -d.y));",
            "  sum += texture2D(tInput, vUv - vec2(d.x, -d.y));",
            "  gl_FragColor = sum * 0.125;",
            "}",
          ].join("\\n"),
          uniforms: {
            tInput: { value: null },
            uHalfPixel: { value: new THREE.Vector2(0.001, 0.001) },
            uOffset: { value: 1.5 },
          },
          depthTest: false,
          depthWrite: false,
        });

        // Dual-Kawase 8-tap tent upsample kernel (four 1/6 inner diagonals + four 1/12 outer cardinals)
        const upMat = new THREE.ShaderMaterial({
          vertexShader: fsVert,
          fragmentShader: [
            "uniform sampler2D tInput;",
            "uniform sampler2D tBlend;",
            "uniform vec2 uHalfPixel;",
            "uniform float uOffset;",
            "uniform float uBlendWeight;",
            "varying vec2 vUv;",
            "void main() {",
            "  vec2 d = uHalfPixel * uOffset;",
            "  vec4 sum = texture2D(tInput, vUv + vec2(-d.x * 2.0, 0.0));",
            "  sum += texture2D(tInput, vUv + vec2(-d.x, d.y)) * 2.0;",
            "  sum += texture2D(tInput, vUv + vec2(0.0, d.y * 2.0));",
            "  sum += texture2D(tInput, vUv + vec2(d.x, d.y)) * 2.0;",
            "  sum += texture2D(tInput, vUv + vec2(d.x * 2.0, 0.0));",
            "  sum += texture2D(tInput, vUv + vec2(d.x, -d.y)) * 2.0;",
            "  sum += texture2D(tInput, vUv + vec2(0.0, -d.y * 2.0));",
            "  sum += texture2D(tInput, vUv + vec2(-d.x, -d.y)) * 2.0;",
            "  vec4 up = sum / 12.0;",
            "  vec4 base = texture2D(tBlend, vUv);",
            "  gl_FragColor = up + base * uBlendWeight;",
            "}",
          ].join("\\n"),
          uniforms: {
            tInput: { value: null },
            tBlend: { value: null },
            uHalfPixel: { value: new THREE.Vector2(0.001, 0.001) },
            uOffset: { value: 1.5 },
            uBlendWeight: { value: 0.45 },
          },
          depthTest: false,
          depthWrite: false,
        });

        // ACESFilmic HDR tone-mapping + premultiplied alpha composite onto MapLibre framebuffer
        const compMat = new THREE.ShaderMaterial({
          vertexShader: fsVert,
          fragmentShader: [
            "uniform sampler2D tScene;",
            "uniform sampler2D tBloom;",
            "uniform float uBloomStrength;",
            "uniform float uExposure;",
            "varying vec2 vUv;",
            "vec3 acesFilmic(vec3 x) {",
            "  const float a = 2.51;",
            "  const float b = 0.03;",
            "  const float c = 2.43;",
            "  const float d = 0.59;",
            "  const float e = 0.14;",
            "  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);",
            "}",
            "vec3 linearToSRGB(vec3 c) {",
            "  vec3 lo = c * 12.92;",
            "  vec3 hi = 1.055 * pow(max(c, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055;",
            "  return mix(lo, hi, step(vec3(0.0031308), c));",
            "}",
            "void main() {",
            "  vec4 sc = texture2D(tScene, vUv);",
            "  vec3 bl = texture2D(tBloom, vUv).rgb * uBloomStrength;",
            "  float a = clamp(sc.a, 0.0, 1.0);",
            "  vec3 unpremul = a > 1e-4 ? (sc.rgb / a) : vec3(0.0);",
            "  vec3 sceneMapped = linearToSRGB(acesFilmic(unpremul * uExposure)) * a;",
            "  vec3 bloomMapped = linearToSRGB(acesFilmic(bl * uExposure));",
            "  vec3 outRgb = sceneMapped + bloomMapped;",
            "  gl_FragColor = vec4(outRgb, a);",
            "}",
          ].join("\\n"),
          uniforms: {
            tScene: { value: null },
            tBloom: { value: null },
            uBloomStrength: { value: 0.28 },
            uExposure: { value: 0.92 },
          },
          transparent: true,
          blending: THREE.CustomBlending,
          blendEquation: THREE.AddEquation,
          blendSrc: THREE.OneFactor,
          blendDst: THREE.OneMinusSrcAlphaFactor,
          depthTest: false,
          depthWrite: false,
        });

        const quad = new THREE.Mesh(fsGeo, brightMat);
        const fsScene = new THREE.Scene();
        fsScene.add(quad);

        const hasHalfFloat = Boolean(
          gl.getExtension("EXT_color_buffer_float") ||
          gl.getExtension("EXT_color_buffer_half_float")
        );
        return {
          fsCam,
          fsScene,
          quad,
          brightMat,
          downMat,
          upMat,
          compMat,
          texType: hasHalfFloat ? THREE.HalfFloatType : THREE.UnsignedByteType,
          rtW: 0,
          rtH: 0,
          sceneRT: null,
          downRTs: [],
          upRTs: [],
          rendered: false,
        };
      }

      function ensureBloomTargets(st, widthPx, heightPx) {
        const w = Math.max(64, Math.round(widthPx || W));
        const h = Math.max(64, Math.round(heightPx || H));
        if (st.rtW === w && st.rtH === h && st.sceneRT) return;
        disposeBloomTargets(st);
        const mkRT = (rw, rh, withDepth) => {
          const rt = new THREE.WebGLRenderTarget(Math.max(16, rw), Math.max(16, rh), {
            type: st.texType,
            minFilter: THREE.LinearFilter,
            magFilter: THREE.LinearFilter,
            wrapS: THREE.ClampToEdgeWrapping,
            wrapT: THREE.ClampToEdgeWrapping,
            depthBuffer: withDepth,
            stencilBuffer: false,
          });
          return rt;
        };
        st.sceneRT = mkRT(w, h, true);
        st.downRTs = [
          mkRT(w >> 1, h >> 1, false),
          mkRT(w >> 2, h >> 2, false),
          mkRT(w >> 3, h >> 3, false),
        ];
        st.upRTs = [
          mkRT(w >> 1, h >> 1, false),
          mkRT(w >> 2, h >> 2, false),
        ];
        st.rtW = w;
        st.rtH = h;
      }

      let hasActive3D = false;
      const customLayer = {
        id: "vedit-three-3d",
        type: "custom",
        renderingMode: "3d",
        onAdd(m, gl) {
          renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl, antialias: true });
          renderer.autoClear = false;
          renderer.shadowMap.enabled = true;
          renderer.shadowMap.autoUpdate = false;
          renderer.shadowMap.type = THREE.PCFSoftShadowMap;
          if (window.THREE_ADDONS && window.THREE_ADDONS.RoomEnvironment && typeof THREE.PMREMGenerator === "function") {
            const pmrem = new THREE.PMREMGenerator(renderer);
            const envTex = pmrem.fromScene(new window.THREE_ADDONS.RoomEnvironment(), 0.04).texture;
            scene.environment = envTex;
            if ("environmentIntensity" in scene) scene.environmentIntensity = 0.26;
            pmrem.dispose();
          }
          if (HDR_BLOOM_ENABLED) {
            try {
              bloomState = initDualKawaseBloom(gl);
            } catch {
              bloomState = null;
            }
          }
        },
        prerender(gl, options) {
          if (!renderer || !hasActive3D) {
            if (bloomState) bloomState.rendered = false;
            return;
          }
          const rawMat = (options && options.defaultProjectionData && options.defaultProjectionData.mainMatrix) || options;
          if (!rawMat) return;
          camera.projectionMatrix = new THREE.Matrix4().fromArray(rawMat).multiply(sceneOriginMat);
          updateCameraLocalPos(camera.projectionMatrix);

          const prevFbo = gl.getParameter(gl.FRAMEBUFFER_BINDING);
          const prevVp = gl.getParameter(gl.VIEWPORT);
          if (!bloomState) {
            renderer.resetState();
            renderer.shadowMap.needsUpdate = true;
            renderer.shadowMap.render(scene, camera);
            renderer.setRenderTarget(null);
            gl.bindFramebuffer(gl.FRAMEBUFFER, prevFbo);
            if (prevVp) gl.viewport(prevVp[0], prevVp[1], prevVp[2], prevVp[3]);
            renderer.resetState();
            return;
          }
          ensureBloomTargets(bloomState, gl.drawingBufferWidth, gl.drawingBufferHeight);

          renderer.resetState();
          renderer.shadowMap.needsUpdate = true;
          // 1. Render 3D HDR scene + PCF soft shadows into sceneRT
          renderer.setRenderTarget(bloomState.sceneRT);
          renderer.setClearColor(0x000000, 0);
          renderer.clear(true, true, false);
          renderer.render(scene, camera);

          // 2. Bright-pass threshold -> downRTs[0] (1/2 res)
          bloomState.brightMat.uniforms.tInput.value = bloomState.sceneRT.texture;
          bloomState.quad.material = bloomState.brightMat;
          renderer.setRenderTarget(bloomState.downRTs[0]);
          renderer.clear(true, false, false);
          renderer.render(bloomState.fsScene, bloomState.fsCam);

          // 3. Dual-Kawase 5-tap downsample pyramid (1/2 -> 1/4 -> 1/8)
          bloomState.quad.material = bloomState.downMat;
          for (let i = 0; i < 2; i++) {
            const src = bloomState.downRTs[i];
            const dst = bloomState.downRTs[i + 1];
            bloomState.downMat.uniforms.tInput.value = src.texture;
            bloomState.downMat.uniforms.uHalfPixel.value.set(0.5 / src.width, 0.5 / src.height);
            bloomState.downMat.uniforms.uOffset.value = 1.6;
            renderer.setRenderTarget(dst);
            renderer.render(bloomState.fsScene, bloomState.fsCam);
          }

          // 4. Dual-Kawase 8-tap tent upsample pyramid (1/8 -> 1/4 -> 1/2)
          bloomState.quad.material = bloomState.upMat;
          // 1/8 -> upRTs[1] (1/4) blended with downRTs[1]
          bloomState.upMat.uniforms.tInput.value = bloomState.downRTs[2].texture;
          bloomState.upMat.uniforms.tBlend.value = bloomState.downRTs[1].texture;
          bloomState.upMat.uniforms.uHalfPixel.value.set(0.5 / bloomState.downRTs[2].width, 0.5 / bloomState.downRTs[2].height);
          bloomState.upMat.uniforms.uOffset.value = 1.6;
          bloomState.upMat.uniforms.uBlendWeight.value = 0.55;
          renderer.setRenderTarget(bloomState.upRTs[1]);
          renderer.render(bloomState.fsScene, bloomState.fsCam);

          // upRTs[1] (1/4) -> upRTs[0] (1/2) blended with downRTs[0]
          bloomState.upMat.uniforms.tInput.value = bloomState.upRTs[1].texture;
          bloomState.upMat.uniforms.tBlend.value = bloomState.downRTs[0].texture;
          bloomState.upMat.uniforms.uHalfPixel.value.set(0.5 / bloomState.upRTs[1].width, 0.5 / bloomState.upRTs[1].height);
          bloomState.upMat.uniforms.uOffset.value = 1.6;
          bloomState.upMat.uniforms.uBlendWeight.value = 0.42;
          renderer.setRenderTarget(bloomState.upRTs[0]);
          renderer.render(bloomState.fsScene, bloomState.fsCam);

          bloomState.rendered = true;
          renderer.setRenderTarget(null);
          gl.bindFramebuffer(gl.FRAMEBUFFER, prevFbo);
          if (prevVp) gl.viewport(prevVp[0], prevVp[1], prevVp[2], prevVp[3]);
          renderer.resetState();
        },
        render(gl, options) {
          if (!renderer || !hasActive3D) return;
          const rawMat = (options && options.defaultProjectionData && options.defaultProjectionData.mainMatrix) || options;
          camera.projectionMatrix = new THREE.Matrix4().fromArray(rawMat).multiply(sceneOriginMat);
          updateCameraLocalPos(camera.projectionMatrix);
          if (bloomState && bloomState.rendered) {
            renderer.resetState();
            bloomState.compMat.uniforms.tScene.value = bloomState.sceneRT.texture;
            bloomState.compMat.uniforms.tBloom.value = bloomState.upRTs[0].texture;
            bloomState.quad.material = bloomState.compMat;
            renderer.render(bloomState.fsScene, bloomState.fsCam);
            renderer.resetState();
          } else {
            renderer.resetState();
            renderer.clearDepth();
            renderer.render(scene, camera);
            renderer.resetState();
          }
        },
      };
      map.addLayer(customLayer);

      const cableCache = new Map();
      const modelCache = new Map();
      const volumeCache = new Map();
      const countryBlockCache = new Map();

      function pointInLocalRing(px, py, ring) {
        let inside = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          const xi = ring[i].x, yi = ring[i].y;
          const xj = ring[j].x, yj = ring[j].y;
          const intersect = ((yi > py) !== (yj > py)) && (px < ((xj - xi) * (py - yi)) / (yj - yi + 1e-12) + xi);
          if (intersect) inside = !inside;
        }
        return inside;
      }

      function smoothLocalRingCorners(pts, iters = 1) {
        let cur = pts;
        for (let it = 0; it < iters; it++) {
          if (cur.length < 3 || cur.length > 900) break;
          const next = [];
          const n = cur.length;
          for (let i = 0; i < n; i++) {
            const a = cur[i];
            const b = cur[(i + 1) % n];
            next.push(
              new THREE.Vector2(a.x * 0.78 + b.x * 0.22, a.y * 0.78 + b.y * 0.22),
              new THREE.Vector2(a.x * 0.22 + b.x * 0.78, a.y * 0.22 + b.y * 0.78)
            );
          }
          cur = next;
        }
        return cur;
      }

      function buildCountryBlock3DEntry(layer, idx) {
        const geom = resolveGeom(layer.geom_ref);
        const { outer, inner } = polygonRings(geom);
        const grp = new THREE.Group();
        if (!outer.length) {
          scene.add(grp);
          return { key: layer.id || ("cblock_" + idx), grp, empty: true };
        }

        const toLocal2D = (ringLL) => {
          const pts = [];
          for (const c of ringLL || []) {
            if (!c || c.length < 2) continue;
            const v = lngLatAltToLocal(c[0], c[1], 0);
            if (!pts.length || Math.hypot(v.x - pts[pts.length - 1].x, v.y - pts[pts.length - 1].y) > 1e-3) {
              pts.push(new THREE.Vector2(v.x, v.y));
            }
          }
          if (pts.length > 1 && pts[0].distanceTo(pts[pts.length - 1]) < 1e-3) pts.pop();
          return pts;
        };

        const smoothIters = layer.round_corners === false ? 0 : Math.max(0, Math.min(2, Number(layer.corner_smooth_iters ?? 1)));
        const outerRings2D = [];
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const r of outer) {
          let pts = toLocal2D(r);
          if (pts.length < 3) continue;
          if (smoothIters > 0) pts = smoothLocalRingCorners(pts, smoothIters);
          for (const p of pts) {
            if (p.x < minX) minX = p.x;
            if (p.y < minY) minY = p.y;
            if (p.x > maxX) maxX = p.x;
            if (p.y > maxY) maxY = p.y;
          }
          outerRings2D.push(pts);
        }
        if (!outerRings2D.length) {
          scene.add(grp);
          return { key: layer.id || ("cblock_" + idx), grp, empty: true };
        }

        const holeRings2D = inner.map(toLocal2D).filter((h) => h.length >= 3);
        const shapes = outerRings2D.map((pts) => {
          const sh = new THREE.Shape(pts);
          for (const hole of holeRings2D) {
            if (pointInLocalRing(hole[0].x, hole[0].y, pts)) {
              sh.holes.push(new THREE.Path(hole));
            }
          }
          return sh;
        });

        const spanX = Math.max(100, maxX - minX);
        const spanY = Math.max(100, maxY - minY);
        const spanDiag = Math.hypot(spanX, spanY);
        const extrudeHeightM = Math.max(100, Number(layer.extrude_height_m || Math.max(15000, spanDiag * 0.055)));
        const bevelFrac = layer.bevel_px != null ? clamp(Number(layer.bevel_px) / 48, 0, 0.25) : 0.085;
        const bevelThickness = bevelFrac > 0.001 ? clamp(extrudeHeightM * bevelFrac, 80, extrudeHeightM * 0.18) : 0;
        const bevelSize = bevelFrac > 0.001 ? clamp(spanDiag * 0.0032 * (bevelFrac / 0.085), 50, spanDiag * 0.012) : 0;

        const extrudeGeo = new THREE.ExtrudeGeometry(shapes, {
          depth: extrudeHeightM,
          bevelEnabled: bevelThickness > 0 && bevelSize > 0,
          bevelThickness,
          bevelSize,
          bevelSegments: 3,
          curveSegments: 6,
        });

        // Normalize planar UVs across polygon footprint so flag textures and shaders map cleanly
        const posAttr = extrudeGeo.attributes.position;
        const uvAttr = extrudeGeo.attributes.uv;
        if (posAttr && uvAttr) {
          for (let i = 0; i < posAttr.count; i++) {
            const x = posAttr.getX(i);
            const y = posAttr.getY(i);
            uvAttr.setXY(i, (x - minX) / spanX, (y - minY) / spanY);
          }
          uvAttr.needsUpdate = true;
        }
        extrudeGeo.computeVertexNormals();

        // Optional flag texture mapped onto 3D top face
        let flagTex = null;
        if (layer.flag_fill) {
          const fImg = window.__imgCache[BASE_URL + "/flags/" + String(layer.flag_fill).toLowerCase() + ".svg"];
          if (fImg) {
            flagTex = new THREE.CanvasTexture(fImg);
            flagTex.colorSpace = THREE.SRGBColorSpace;
            flagTex.anisotropy = 4;
          }
        }

        const fillCol = new THREE.Color(layer.fill_hex || "#1F9D55");
        const sideCol = layer.side_hex
          ? new THREE.Color(layer.side_hex)
          : fillCol.clone().multiplyScalar(0.56);
        const fresnelCol = new THREE.Color(layer.fresnel_hex || layer.rim_hex || "#BAE6FD");
        const hatchCol = new THREE.Color(layer.hatch_color || "#FFFFFF");
        const hasFlag = Boolean(flagTex);
        const flagWaveAmp = layer.flag_wave === false
          ? 0.0
          : (layer.flag_wave === true
            ? 0.24
            : (layer.flag_wave != null ? clamp(Number(layer.flag_wave) || 0, 0, 0.6) : (hasFlag ? 0.24 : 0.0)));
        const flagWaveSpeed = Number(layer.flag_wave_speed ?? 0.72);
        const flagWaveCycles = Number(layer.flag_wave_cycles ?? 2.6);
        const flagWaveAngleRad = ((Number(layer.flag_wave_angle_deg ?? 22)) * Math.PI) / 180;
        const flagGloss = layer.flag_gloss === false
          ? 0.0
          : (layer.flag_gloss === true
            ? 0.65
            : (layer.flag_gloss != null ? clamp(Number(layer.flag_gloss) || 0, 0, 1) : (hasFlag ? 0.65 : 0.0)));
        const flagGlowEnabled = layer.flag_glow === false ? false : (Boolean(layer.flag_glow) || hasFlag);
        const flagGlowCol = new THREE.Color(layer.flag_glow_hex || layer.rim_hex || "#F8FAFC");
        const flagGlowIntensity = flagGlowEnabled ? Number(layer.flag_glow_intensity ?? 0.82) : 0.0;

        const topUniforms = {
          uCamPos: { value: camLocalPos },
          uTime: { value: 0.0 },
          uScaleZ: { value: 1.0 },
          uHasFlag: { value: hasFlag ? 1.0 : 0.0 },
          uFlagWaveAmp: { value: flagWaveAmp },
          uFlagWaveSpeed: { value: flagWaveSpeed },
          uFlagWaveCycles: { value: flagWaveCycles },
          uFlagWaveAngleRad: { value: flagWaveAngleRad },
          uFlagGloss: { value: flagGloss },
          uFlagGlowEnabled: { value: flagGlowEnabled ? 1.0 : 0.0 },
          uFlagGlowColor: { value: flagGlowCol },
          uFlagGlowIntensity: { value: flagGlowIntensity },
          uFresnelColor: { value: fresnelCol },
          uFresnelIntensity: { value: Number(layer.fresnel_intensity ?? (flagGlowEnabled ? 0.55 : 0.28)) },
          uHatchEnabled: { value: layer.hatch ? 1.0 : 0.0 },
          uHatchSpacingM: { value: Math.max(500, spanDiag / Math.max(8, Number(layer.hatch_density ?? 36))) },
          uHatchAngleRad: { value: ((Number(layer.hatch_angle_deg ?? 45)) * Math.PI) / 180 },
          uHatchProgress: { value: 1.0 },
          uHatchColor: { value: hatchCol },
          uHatchAlpha: { value: Number(layer.hatch_alpha ?? 0.36) },
          uBoundsMin: { value: new THREE.Vector2(minX, minY) },
          uBoundsSpan: { value: new THREE.Vector2(spanX, spanY) },
          uSweepProgress: { value: -1.0 },
          uSweepIntensity: { value: 0.0 },
          uSweepColor: { value: new THREE.Color("#FFFFFF") },
        };

        const topMat = new THREE.MeshStandardMaterial({
          color: flagTex ? 0xffffff : fillCol,
          map: flagTex,
          roughness: layer.roughness ?? (hasFlag ? 0.44 : 0.62),
          metalness: layer.metalness ?? (hasFlag ? 0.08 : 0.06),
          transparent: true,
          opacity: layer.fill_alpha ?? 0.96,
        });
        topMat.onBeforeCompile = (shader) => {
          Object.assign(shader.uniforms, topUniforms);
          shader.vertexShader = shader.vertexShader
            .replace(
              "#include <common>",
              "#include <common>\\nuniform vec3 uCamPos;\\nvarying vec3 vBlockLocalPos;\\nvarying vec3 vBlockLocalNorm;"
            )
            .replace(
              "#include <begin_vertex>",
              "#include <begin_vertex>\\nvBlockLocalPos = position;\\nvBlockLocalNorm = normal;"
            )
            .replace(
              "vViewPosition = - mvPosition.xyz;",
              "vViewPosition = uCamPos - (modelMatrix * vec4(transformed, 1.0)).xyz;"
            );
          shader.fragmentShader = shader.fragmentShader
            .replace(
              "#include <common>",
              [
                "#include <common>",
                "uniform vec3 uCamPos;",
                "uniform float uTime;",
                "uniform float uScaleZ;",
                "uniform float uHasFlag;",
                "uniform float uFlagWaveAmp;",
                "uniform float uFlagWaveSpeed;",
                "uniform float uFlagWaveCycles;",
                "uniform float uFlagWaveAngleRad;",
                "uniform float uFlagGloss;",
                "uniform float uFlagGlowEnabled;",
                "uniform vec3 uFlagGlowColor;",
                "uniform float uFlagGlowIntensity;",
                "uniform vec3 uFresnelColor;",
                "uniform float uFresnelIntensity;",
                "uniform float uHatchEnabled;",
                "uniform float uHatchSpacingM;",
                "uniform float uHatchAngleRad;",
                "uniform float uHatchProgress;",
                "uniform vec3 uHatchColor;",
                "uniform float uHatchAlpha;",
                "uniform vec2 uBoundsMin;",
                "uniform vec2 uBoundsSpan;",
                "uniform float uSweepProgress;",
                "uniform float uSweepIntensity;",
                "uniform vec3 uSweepColor;",
                "varying vec3 vBlockLocalPos;",
                "varying vec3 vBlockLocalNorm;",
              ].join("\\n")
            )
            .replace(
              "#include <map_fragment>",
              [
                "float flagWaveDh = 0.0;",
                "#ifdef USE_MAP",
                "  vec2 flagUv = vMapUv;",
                "  if (uHasFlag > 0.5 && uFlagWaveAmp > 0.001) {",
                "    float caW = cos(uFlagWaveAngleRad);",
                "    float saW = sin(uFlagWaveAngleRad);",
                "    float wCoord = flagUv.x * caW + flagUv.y * saW;",
                "    float pCoord = -flagUv.x * saW + flagUv.y * caW;",
                "    float ph1 = 6.2831853 * (uFlagWaveCycles * wCoord - uFlagWaveSpeed * uTime);",
                "    float ph2 = 6.2831853 * (uFlagWaveCycles * 1.85 * wCoord - uFlagWaveSpeed * 1.48 * uTime + 0.36 * pCoord);",
                "    float waveH = 0.68 * sin(ph1) + 0.32 * sin(ph2);",
                "    flagWaveDh = 0.68 * cos(ph1) + 0.32 * 1.85 * cos(ph2);",
                "    vec2 warpDir = vec2(-saW, caW);",
                "    flagUv = clamp(flagUv + warpDir * waveH * (0.044 * (uFlagWaveAmp / 0.24)), vec2(0.002), vec2(0.998));",
                "  }",
                "  vec4 sampledDiffuseColor = texture2D( map, flagUv );",
                "  diffuseColor *= sampledDiffuseColor;",
                "  if (uHasFlag > 0.5 && uFlagWaveAmp > 0.001) {",
                "    diffuseColor.rgb *= clamp(1.0 + flagWaveDh * uFlagWaveAmp * 0.96, 0.54, 1.46);",
                "  }",
                "#endif",
              ].join("\\n")
            )
            .replace(
              "#include <emissivemap_fragment>",
              [
                "#include <emissivemap_fragment>",
                "vec3 wPos = vec3(vBlockLocalPos.xy, vBlockLocalPos.z * max(uScaleZ, 0.005));",
                "vec3 wNorm = normalize(vec3(vBlockLocalNorm.xy, vBlockLocalNorm.z / max(uScaleZ, 0.01)));",
                "vec3 viewDirW = normalize(uCamPos - wPos);",
                "float ndv = clamp(dot(wNorm, viewDirW), 0.0, 1.0);",
                "float bevelMask = 1.0 - smoothstep(0.65, 0.96, wNorm.z);",
                "float fresnel = pow(1.0 - ndv, 3.0) * mix(0.28, 1.0, bevelMask);",
                "totalEmissiveRadiance += uFresnelColor * fresnel * uFresnelIntensity;",
                "if (uHasFlag > 0.5 && uFlagWaveAmp > 0.001) {",
                "  float crest = pow(max(0.0, flagWaveDh), 2.1);",
                "  totalEmissiveRadiance += vec3(1.0, 0.99, 0.95) * crest * uFlagWaveAmp * 0.65 * uFlagGloss;",
                "}",
                "if (uFlagGlowEnabled > 0.5 && uFlagGlowIntensity > 0.001) {",
                "  float glowPulse = 0.86 + 0.14 * sin(uTime * 2.8);",
                "  totalEmissiveRadiance += diffuseColor.rgb * (0.24 * uFlagGlowIntensity * glowPulse);",
                "  float edgeGlow = pow(1.0 - ndv, 2.0) * mix(0.30, 1.35, bevelMask);",
                "  totalEmissiveRadiance += uFlagGlowColor * edgeGlow * (0.85 * uFlagGlowIntensity * glowPulse);",
                "}",
                "if (uHatchEnabled > 0.5 && uHatchProgress > 0.001 && wNorm.z > 0.72) {",
                "  float ca = cos(uHatchAngleRad);",
                "  float sa = sin(uHatchAngleRad);",
                "  float nCoord = vBlockLocalPos.x * sa + vBlockLocalPos.y * ca;",
                "  float cell = nCoord / max(uHatchSpacingM, 1.0);",
                "  float fw = max(fwidth(cell), 1e-4);",
                "  float distLine = abs(fract(cell + 0.5) - 0.5);",
                "  float lineMask = 1.0 - smoothstep(0.045 - fw, 0.045 + fw, distLine);",
                "  vec2 uvNorm = (vBlockLocalPos.xy - uBoundsMin) / max(uBoundsSpan, vec2(1.0));",
                "  float rank = clamp(uvNorm.x * 0.65 + (1.0 - uvNorm.y) * 0.35, 0.0, 1.0);",
                "  float localP = clamp((uHatchProgress - rank * 0.55) / 0.45, 0.0, 1.0);",
                "  float uFrac = clamp((uvNorm.x * ca + (1.0 - uvNorm.y) * sa), 0.0, 1.0);",
                "  float sweepReveal = 1.0 - smoothstep(localP - 0.04, localP + 0.04, uFrac * 0.85);",
                "  float hMask = lineMask * sweepReveal * uHatchAlpha * step(0.002, localP);",
                "  diffuseColor.rgb = mix(diffuseColor.rgb, uHatchColor, clamp(hMask, 0.0, 0.75));",
                "  totalEmissiveRadiance += uHatchColor * hMask * 0.08;",
                "}",
                "if (uSweepIntensity > 0.005 && uSweepProgress >= 0.0 && uSweepProgress <= 1.0) {",
                "  vec2 uvNormS = (vBlockLocalPos.xy - uBoundsMin) / max(uBoundsSpan, vec2(1.0));",
                "  float diagS = (uvNormS.x * 0.72 + uvNormS.y * 0.28);",
                "  float band = exp(-pow((diagS - mix(-0.25, 1.25, uSweepProgress)) / 0.11, 2.0));",
                "  totalEmissiveRadiance += uSweepColor * band * uSweepIntensity * 0.65;",
                "}",
              ].join("\\n")
            );
        };

        const sideUniforms = {
          uExtrudeH: { value: Math.max(1, extrudeHeightM) },
          uFresnelColor: { value: fresnelCol },
          uCamPos: { value: camLocalPos },
          uScaleZ: { value: 1.0 },
        };
        const sideMat = new THREE.MeshStandardMaterial({
          color: sideCol,
          roughness: layer.side_roughness ?? 0.68,
          metalness: layer.side_metalness ?? 0.10,
          transparent: true,
          opacity: layer.fill_alpha ?? 0.96,
        });
        sideMat.onBeforeCompile = (shader) => {
          Object.assign(shader.uniforms, sideUniforms);
          shader.vertexShader = shader.vertexShader
            .replace(
              "#include <common>",
              "#include <common>\\nuniform vec3 uCamPos;\\nvarying vec3 vSideLocalPos;"
            )
            .replace(
              "#include <begin_vertex>",
              "#include <begin_vertex>\\nvSideLocalPos = position;"
            )
            .replace(
              "vViewPosition = - mvPosition.xyz;",
              "vViewPosition = uCamPos - (modelMatrix * vec4(transformed, 1.0)).xyz;"
            );
          shader.fragmentShader = shader.fragmentShader
            .replace(
              "#include <common>",
              "#include <common>\\nuniform float uExtrudeH;\\nvarying vec3 vSideLocalPos;"
            )
            .replace(
              "#include <dithering_fragment>",
              [
                "float baseAO = mix(0.38, 1.0, smoothstep(0.0, 0.55, vSideLocalPos.z / max(uExtrudeH, 1.0)));",
                "gl_FragColor.rgb *= baseAO;",
                "#include <dithering_fragment>",
              ].join("\\n")
            );
        };

        const blockMesh = new THREE.Mesh(extrudeGeo, [topMat, sideMat]);
        blockMesh.castShadow = true;
        blockMesh.receiveShadow = true;
        blockMesh.frustumCulled = false;
        grp.add(blockMesh);

        // Crisp HDR emissive top perimeter rim + luminous outer glow ribbon when flag_glow is active
        const rimLines = [];
        const rimCol = new THREE.Color(layer.rim_hex || "#F8FAFC");
        const rimIntensity = Number(layer.rim_emissive ?? (flagGlowEnabled ? 2.15 : 1.35));
        const rimMat = new THREE.LineBasicMaterial({
          color: rimCol.clone().multiplyScalar(rimIntensity),
          transparent: true,
          opacity: 0.96,
        });
        const rimZ = extrudeHeightM + bevelThickness + Math.max(40, extrudeHeightM * 0.008);
        for (const pts of outerRings2D) {
          const verts = pts.map((p) => new THREE.Vector3(p.x, p.y, rimZ));
          const lGeo = new THREE.BufferGeometry().setFromPoints(verts);
          const loop = new THREE.LineLoop(lGeo, rimMat);
          loop.frustumCulled = false;
          grp.add(loop);
          rimLines.push(loop);
          if (flagGlowEnabled && pts.length >= 3) {
            const haloVerts = pts.map((p) => new THREE.Vector3(p.x, p.y, rimZ));
            haloVerts.push(haloVerts[0].clone());
            const haloCurve = new THREE.CatmullRomCurve3(haloVerts, true, "catmullrom", 0.12);
            const haloRad = clamp(spanDiag * 0.0055, 80, spanDiag * 0.012);
            const haloSegs = clamp(pts.length * 2, 48, 260);
            const haloGeo = new THREE.TubeGeometry(haloCurve, haloSegs, haloRad, 6, true);
            const haloMat = new THREE.MeshBasicMaterial({
              color: flagGlowCol.clone().multiplyScalar(1.95),
              transparent: true,
              opacity: 0.58,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
            });
            const haloMesh = new THREE.Mesh(haloGeo, haloMat);
            haloMesh.frustumCulled = false;
            grp.add(haloMesh);
            rimLines.push(haloMesh);
          }
        }

        scene.add(grp);
        return {
          key: layer.id || ("cblock_" + idx),
          grp,
          blockMesh,
          topMat,
          sideMat,
          rimMat,
          rimBaseCol: rimCol,
          rimBaseIntensity: rimIntensity,
          flagGlowEnabled,
          topUniforms,
          sideUniforms,
          baseFillAlpha: layer.fill_alpha ?? 0.96,
          boundsBox: new THREE.Box3(
            new THREE.Vector3(minX, minY, 0),
            new THREE.Vector3(maxX, maxY, extrudeHeightM + bevelThickness)
          ),
          empty: false,
        };
      }

      function buildCableEntry(layer, idx) {
        const rawCoords = resolveGeom(layer.coords_ref) || layer.coords || [];
        const coords = layer.reverse ? [...rawCoords].reverse() : rawCoords;
        const rawPts = coords.map((c) => {
          const v = lngLatAltToLocal(c[0], c[1], c[2] || 0);
          return v;
        });
        const curve = rawPts.length >= 2 ? new THREE.CatmullRomCurve3(rawPts, false, "catmullrom", 0.35) : null;
        const baseSegs = clamp(Math.round(Math.max(90, coords.length * 14)), 90, 320);
        const radialSegs = 14;
        const catenary = Boolean(layer.catenary);
        const spanAnchors = layer.span_fractions || null; // optional array of sub-spans for catenary sag
        const centerPts = [];
        const unitVert = [];
        let totalLenM = 1;
        if (curve) {
          let prev = null;
          totalLenM = 0;
          for (let i = 0; i <= baseSegs; i++) {
            const u = i / baseSegs;
            const p = curve.getPointAt(u);
            centerPts.push(p);
            if (prev) totalLenM += p.distanceTo(prev);
            prev = p;
          }
        }
        const frames = centerPts.length >= 2 ? computeParallelFrames(centerPts) : null;
        const texSet = getArmorTexSet(layer.armor_hex || "#E5B449", layer.jacket_hex || "#1E293B");
        const colorTex = texSet.makeWrapped(texSet.colCanvas);
        const bumpTex = texSet.makeWrapped(texSet.bumpCanvas);

        const offCount = Array.isArray(layer.parallel_offsets_px) && layer.parallel_offsets_px.length > 0
          ? layer.parallel_offsets_px
          : [0];
        const strands = offCount.map((offPx) => {
          const tubeGeo = new THREE.BufferGeometry();
          const vertCount = (baseSegs + 1) * (radialSegs + 1);
          const posArr = new Float32Array(vertCount * 3);
          const normArr = new Float32Array(vertCount * 3);
          const uvArr = new Float32Array(vertCount * 2);
          const idxArr = [];
          for (let i = 0; i <= baseSegs; i++) {
            const u = i / baseSegs;
            for (let j = 0; j <= radialSegs; j++) {
              const v = j / radialSegs;
              const k = i * (radialSegs + 1) + j;
              uvArr[k * 2] = u;
              uvArr[k * 2 + 1] = v;
              if (i < baseSegs && j < radialSegs) {
                const a = i * (radialSegs + 1) + j;
                const b = (i + 1) * (radialSegs + 1) + j;
                const c = (i + 1) * (radialSegs + 1) + (j + 1);
                const d = i * (radialSegs + 1) + (j + 1);
                idxArr.push(a, b, d, b, c, d);
              }
            }
          }
          tubeGeo.setAttribute("position", new THREE.BufferAttribute(posArr, 3));
          tubeGeo.setAttribute("normal", new THREE.BufferAttribute(normArr, 3));
          tubeGeo.setAttribute("uv", new THREE.BufferAttribute(uvArr, 2));
          tubeGeo.setIndex(idxArr);
          const mat = new THREE.MeshStandardMaterial({
            map: colorTex,
            bumpMap: bumpTex,
            bumpScale: 0.35,
            metalness: layer.metalness ?? 0.78,
            roughness: layer.roughness ?? 0.28,
            emissive: new THREE.Color(layer.emissive_hex || "#F59E0B"),
            emissiveIntensity: layer.emissive_intensity ?? 0.16,
            transparent: true,
            opacity: 1,
          });
          const mesh = new THREE.Mesh(tubeGeo, mat);
          mesh.frustumCulled = false;

          // Seabed / ground shadow ribbon under the cable
          const shGeo = new THREE.BufferGeometry();
          const shPos = new Float32Array((baseSegs + 1) * 2 * 3);
          const shIdx = [];
          for (let i = 0; i < baseSegs; i++) {
            const a = i * 2, b = i * 2 + 1, c = (i + 1) * 2, d = (i + 1) * 2 + 1;
            shIdx.push(a, c, b, c, d, b);
          }
          shGeo.setAttribute("position", new THREE.BufferAttribute(shPos, 3));
          shGeo.setIndex(shIdx);
          const shMat = new THREE.MeshBasicMaterial({
            color: 0x02080d,
            transparent: true,
            opacity: 0.42,
            side: THREE.DoubleSide,
            depthWrite: false,
          });
          const shMesh = new THREE.Mesh(shGeo, shMat);
          shMesh.frustumCulled = false;

          return { offPx, tubeGeo, posArr, normArr, mat, mesh, shGeo, shPos, shMat, shMesh };
        });

        const group = new THREE.Group();
        for (const s of strands) {
          group.add(s.shMesh);
          group.add(s.mesh);
        }

        // Energized induction rings travelling smoothly along sheath
        const pulseCount = Math.max(0, Math.round(layer.pulse_count ?? 3));
        const pulseRings = [];
        const ringMat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(layer.pulse_hex || "#FDE047"),
          emissive: new THREE.Color(layer.pulse_hex || "#F59E0B"),
          emissiveIntensity: 0.95,
          roughness: 0.22,
          metalness: 0.65,
          transparent: true,
        });
        for (let p = 0; p < pulseCount; p++) {
          const rm = new THREE.Mesh(new THREE.TorusGeometry(1, 0.17, 8, 18), ringMat);
          rm.frustumCulled = false;
          group.add(rm);
          pulseRings.push(rm);
        }
        const tipSpark = new THREE.Mesh(new THREE.SphereGeometry(1, 10, 8), ringMat);
        tipSpark.frustumCulled = false;
        group.add(tipSpark);

        let startCollar = null;
        let endCollar = null;
        if (layer.landing_collar) {
          const collarMat = new THREE.MeshStandardMaterial({
            color: 0x94a3b8,
            metalness: 0.85,
            roughness: 0.25,
          });
          startCollar = new THREE.Mesh(new THREE.CylinderGeometry(1.55, 1.85, 1.4, 14), collarMat);
          startCollar.rotation.x = Math.PI / 2;
          startCollar.frustumCulled = false;
          endCollar = startCollar.clone();
          endCollar.frustumCulled = false;
          group.add(startCollar, endCollar);
        }

        scene.add(group);
        return {
          key: layer.id || ("cable_" + idx),
          coords,
          baseSegs,
          radialSegs,
          centerPts,
          frames,
          totalLenM,
          colorTex,
          bumpTex,
          strands,
          pulseRings,
          ringMat,
          tipSpark,
          startCollar,
          endCollar,
          catenary,
          spanAnchors,
          group,
        };
      }

      function update3DScene(layers, t) {
        const curZoom = map.getZoom();
        const activeCables = new Set();
        const activeModels = new Set();
        const activeVolumes = new Set();
        const activeBlocks = new Set();
        const activeShadowBox = new THREE.Box3();
        let anyVisible3D = false;
        let anyShadowCaster = false;

        for (let idx = 0; idx < (layers || []).length; idx++) {
          const layer = layers[idx];
          const tStart = layer.start_s ?? 0;
          const tEnd = layer.end_s ?? 1e9;
          const visible = t >= tStart - 0.001 && t <= tEnd + 0.001;
          const fadeIn = layer.fade_in_s ? easeOutCubic(seg(t, tStart, tStart + layer.fade_in_s)) : 1;
          const fadeOut = layer.fade_out_s ? 1 - easeInCubic(seg(t, tEnd - layer.fade_out_s, tEnd)) : 1;
          const alpha = clamp(fadeIn * fadeOut * (layer.opacity ?? 1), 0, 1);

          if (layer.type === "cable_3d") {
            const key = layer.id || ("cable_" + idx);
            let entry = cableCache.get(key);
            if (!entry) {
              entry = buildCableEntry(layer, idx);
              cableCache.set(key, entry);
            }
            activeCables.add(key);
            entry.group.visible = visible && alpha > 0.01 && entry.centerPts.length >= 2;
            if (!entry.group.visible) continue;
            anyVisible3D = true;

            const midLat = entry.coords.length ? entry.coords[Math.floor(entry.coords.length / 2)][1] : originLat;
            const rawRMeters = metersForScreenPx(
              layer.radius_px ?? 5.5,
              midLat,
              curZoom,
              layer.radius_ref_zoom ?? curZoom,
              layer.radius_coupling ?? 0.42,
              layer.min_scale ?? 0.45,
              layer.max_scale ?? 2.8
            );
            const minScreenPx = Number(layer.min_screen_radius_px || 0);
            const minRMeters = minScreenPx > 0 ? metersForScreenPx(minScreenPx, midLat, curZoom, curZoom, 0, 1, 1) : 0;
            const rMeters = Math.max(rawRMeters, minRMeters);
            const endTaperM = Math.max(0, Number(layer.end_taper_m || 0));
            const altMeters = layer.altitude_px != null
              ? metersForScreenPx(layer.altitude_px, midLat, curZoom, layer.radius_ref_zoom ?? curZoom, layer.radius_coupling ?? 0.42, layer.min_scale ?? 0.45, layer.max_scale ?? 2.8)
              : rMeters * 1.15;
            const sagMeters = metersForScreenPx(layer.catenary_sag_px ?? 16, midLat, curZoom, layer.radius_ref_zoom ?? curZoom, layer.radius_coupling ?? 0.42, 0.45, 2.8);

            const drawS = layer.instant === true ? 0 : (layer.draw_duration_s ?? 1.2);
            const drawFrom = tStart + (layer.draw_delay_s ?? 0);
            const drawEase = layer.draw_ease || "editorial_out";
            const prog = drawS > 0 ? evalEase(drawEase, seg(t, drawFrom, drawFrom + drawS)) : (t >= drawFrom - 0.001 ? 1 : 0);
            const exactSegPos = clamp(entry.baseSegs * prog, 0, entry.baseSegs);
            const fullSegs = Math.floor(exactSegPos);
            const segFrac = exactSegPos - fullSegs;
            const hasTipFrac = segFrac > 1e-4 && fullSegs < entry.baseSegs;
            const drawSegs = hasTipFrac ? fullSegs + 1 : fullSegs;

            const repU = clamp(entry.totalLenM / Math.max(1, rMeters * 4.5), 6, 420);
            entry.colorTex.repeat.set(repU, 1);
            entry.bumpTex.repeat.set(repU, 1);

            const N = entry.frames.normals;
            const B = entry.frames.binormals;
            const T = entry.frames.tangents;
            const rSeg = entry.radialSegs;
            const sampleCenterAt = (fIdx) => {
              const i0 = clamp(Math.floor(fIdx), 0, entry.baseSegs);
              const i1 = Math.min(entry.baseSegs, i0 + 1);
              const f = clamp(fIdx - i0, 0, 1);
              const cp = entry.centerPts[i0].clone().lerp(entry.centerPts[i1], f);
              const tan = T[i0].clone().lerp(T[i1], f).normalize();
              const nVec = N[i0].clone().lerp(N[i1], f).normalize();
              const bVec = B[i0].clone().lerp(B[i1], f).normalize();
              return { cp, tan, nVec, bVec, u: fIdx / entry.baseSegs };
            };

            const sagAt = (uVal) => {
              if (!entry.catenary) return 0;
              const nSpans = Math.max(1, (entry.coords.length || 2) - 1);
              const spanPhase = (uVal * nSpans) % 1;
              return -Math.sin(spanPhase * Math.PI) * sagMeters;
            };
            const geomSig = [
              drawSegs,
              segFrac.toFixed(4),
              rMeters.toFixed(3),
              altMeters.toFixed(3),
              sagMeters.toFixed(3),
              endTaperM.toFixed(2),
            ].join("|");
            const needsRebuild = entry._lastGeomSig !== geomSig;
            entry._lastGeomSig = geomSig;

            for (const st of entry.strands) {
              st.mat.opacity = alpha;
              st.shMat.opacity = alpha * (entry.catenary ? 0.30 : 0.48);
              if (!needsRebuild) continue;
              const latShiftM = st.offPx
                ? metersForScreenPx(st.offPx, midLat, curZoom, layer.radius_ref_zoom ?? curZoom, layer.radius_coupling ?? 0.42, 0.45, 2.8)
                : 0;

              for (let i = 0; i <= drawSegs; i++) {
                const isFracTip = hasTipFrac && i === drawSegs;
                const sData = isFracTip ? sampleCenterAt(exactSegPos) : {
                  cp: entry.centerPts[i],
                  tan: T[i],
                  nVec: N[i],
                  bVec: B[i],
                  u: i / entry.baseSegs,
                };
                const u = sData.u;
                const sagOff = sagAt(u);
                const cp = sData.cp;
                const tan = sData.tan;
                const sideDir = new THREE.Vector3(-tan.y, tan.x, 0).normalize();
                if (sideDir.lengthSq() < 0.01) sideDir.set(1, 0, 0);
                const cx = cp.x + sideDir.x * latShiftM;
                const cy = cp.y + sideDir.y * latShiftM;
                const cz = cp.z + altMeters + sagOff;

                const nVec = sData.nVec;
                const bVec = sData.bVec;
                let localRad = rMeters;
                if (endTaperM > 0) {
                  const distFromStart = u * entry.totalLenM;
                  const distFromEnd = (1 - u) * entry.totalLenM;
                  const taperFactor = Math.min(1, distFromStart / endTaperM, distFromEnd / endTaperM);
                  localRad = rMeters * clamp(taperFactor, 0.15, 1.0);
                }
                for (let j = 0; j <= rSeg; j++) {
                  const theta = (j / rSeg) * Math.PI * 2;
                  const cosT = Math.cos(theta), sinT = Math.sin(theta);
                  const nx = nVec.x * cosT + bVec.x * sinT;
                  const ny = nVec.y * cosT + bVec.y * sinT;
                  const nz = nVec.z * cosT + bVec.z * sinT;
                  const k = (i * (rSeg + 1) + j) * 3;
                  st.posArr[k] = cx + nx * localRad;
                  st.posArr[k + 1] = cy + ny * localRad;
                  st.posArr[k + 2] = cz + nz * localRad;
                  st.normArr[k] = nx;
                  st.normArr[k + 1] = ny;
                  st.normArr[k + 2] = nz;
                }
                const sk = i * 6;
                const sw = rMeters * 1.65;
                st.shPos[sk] = cx - sideDir.x * sw;
                st.shPos[sk + 1] = cy - sideDir.y * sw;
                st.shPos[sk + 2] = cp.z + rMeters * 0.08;
                st.shPos[sk + 3] = cx + sideDir.x * sw;
                st.shPos[sk + 4] = cy + sideDir.y * sw;
                st.shPos[sk + 5] = cp.z + rMeters * 0.08;
              }
              st.tubeGeo.attributes.position.needsUpdate = true;
              st.tubeGeo.attributes.normal.needsUpdate = true;
              st.tubeGeo.setDrawRange(0, drawSegs * rSeg * 6);
              st.shGeo.attributes.position.needsUpdate = true;
              st.shGeo.setDrawRange(0, drawSegs * 6);
            }

            // Animate pulse rings continuously along sheath
            const pSpeed = Number(layer.pulse_speed || 0);
            entry.ringMat.opacity = alpha;
            if (pSpeed > 0 && exactSegPos >= 2) {
              const pLen = entry.pulseRings.length;
              for (let p = 0; p < pLen; p++) {
                const rm = entry.pulseRings[p];
                const ph = (((t - tStart) * pSpeed + p / Math.max(1, pLen)) % 1 + 1) % 1;
                const sData = sampleCenterAt(ph * exactSegPos);
                const rSag = sagAt(sData.u);
                rm.visible = true;
                rm.position.set(sData.cp.x, sData.cp.y, sData.cp.z + altMeters + rSag);
                rm.scale.setScalar(rMeters * 1.18);
                rm.lookAt(sData.cp.x + sData.tan.x, sData.cp.y + sData.tan.y, sData.cp.z + altMeters + rSag + sData.tan.z);
              }
            } else {
              for (const rm of entry.pulseRings) rm.visible = false;
            }
            if (entry.startCollar && entry.endCollar) {
              const sp0 = entry.centerPts[0];
              entry.startCollar.visible = exactSegPos >= 0.5;
              entry.startCollar.position.set(sp0.x, sp0.y, sp0.z + altMeters * 0.55);
              entry.startCollar.scale.set(rMeters, rMeters, Math.max(rMeters, altMeters));
              const spEnd = entry.centerPts[entry.baseSegs];
              entry.endCollar.visible = prog >= 0.99;
              entry.endCollar.position.set(spEnd.x, spEnd.y, spEnd.z + altMeters * 0.55);
              entry.endCollar.scale.set(rMeters, rMeters, Math.max(rMeters, altMeters));
            }
            if (prog > 0.01 && prog < 0.995 && exactSegPos > 0.1) {
              const tipData = sampleCenterAt(exactSegPos);
              const tipSag = sagAt(tipData.u);
              entry.tipSpark.visible = true;
              entry.tipSpark.position.set(tipData.cp.x, tipData.cp.y, tipData.cp.z + altMeters + tipSag);
              entry.tipSpark.scale.setScalar(rMeters * 1.8);
            } else {
              entry.tipSpark.visible = false;
            }
          } else if (layer.type === "country_block_3d") {
            const key = layer.id || ("cblock_" + idx);
            let entry = countryBlockCache.get(key);
            if (!entry) {
              entry = buildCountryBlock3DEntry(layer, idx);
              countryBlockCache.set(key, entry);
            }
            activeBlocks.add(key);
            entry.grp.visible = visible && alpha > 0.01 && !entry.empty;
            if (!entry.grp.visible) continue;
            anyVisible3D = true;
            anyShadowCaster = true;

            const riseDelay = Number(layer.rise_delay_s ?? 0);
            const riseDur = layer.rise_duration_s != null ? Math.max(0, Number(layer.rise_duration_s)) : 0.72;
            const riseEase = layer.rise_ease || "spring_tactile";
            const riseRaw = riseDur > 0 ? evalEase(riseEase, seg(t, tStart + riseDelay, tStart + riseDelay + riseDur)) : 1.0;
            const scaleZ = Math.max(0.005, riseRaw);
            entry.grp.scale.set(1, 1, scaleZ);
            entry.topUniforms.uTime.value = t;
            entry.topUniforms.uScaleZ.value = scaleZ;
            entry.sideUniforms.uScaleZ.value = scaleZ;
            entry.topMat.opacity = entry.baseFillAlpha * alpha;
            entry.sideMat.opacity = entry.baseFillAlpha * alpha;
            entry.rimMat.opacity = 0.96 * alpha;
            if (entry.flagGlowEnabled && entry.rimBaseCol) {
              const pulse = 0.88 + 0.16 * Math.sin(t * 2.8);
              entry.rimMat.color.copy(entry.rimBaseCol).multiplyScalar(entry.rimBaseIntensity * pulse);
            }

            if (layer.hatch) {
              const hDelay = Number(layer.hatch_delay_s ?? (riseDelay + riseDur * 0.45));
              const hDur = layer.hatch_draw_s != null ? Math.max(0, Number(layer.hatch_draw_s)) : 0.85;
              entry.topUniforms.uHatchEnabled.value = 1.0;
              entry.topUniforms.uHatchProgress.value = hDur > 0 ? evalEase("editorial_out", seg(t, tStart + hDelay, tStart + hDelay + hDur)) : 1.0;
            } else {
              entry.topUniforms.uHatchEnabled.value = 0.0;
            }

            if (layer.light_sweep) {
              const lsObj = typeof layer.light_sweep === "object" ? layer.light_sweep : {};
              const lsAt = lsObj.at_s != null ? Number(lsObj.at_s) : (tStart + riseDelay + riseDur + Number(lsObj.delay_s ?? 0.1));
              const lsDur = Math.max(0.08, Number(lsObj.duration_s ?? 0.75));
              if (t >= lsAt && t <= lsAt + lsDur) {
                const u = easeInOutCubic(seg(t, lsAt, lsAt + lsDur));
                entry.topUniforms.uSweepProgress.value = u;
                entry.topUniforms.uSweepIntensity.value = Math.sin(u * Math.PI) * Number(lsObj.intensity ?? 0.65);
                if (lsObj.color) entry.topUniforms.uSweepColor.value.set(lsObj.color);
              } else {
                entry.topUniforms.uSweepIntensity.value = 0.0;
              }
            } else {
              entry.topUniforms.uSweepIntensity.value = 0.0;
            }

            activeShadowBox.union(entry.boundsBox);
          } else if (layer.type === "model_3d") {
            const key = layer.id || ("model_" + idx);
            let entry = modelCache.get(key);
            if (!entry) {
              let grp = null;
              const gltfUrl = layer.gltf_url
                ? (String(layer.gltf_url).startsWith("http")
                  ? String(layer.gltf_url)
                  : BASE_URL + "/" + String(layer.gltf_url).replace(/^\\/+/, ""))
                : null;
              if (gltfUrl && window.__gltfCache[gltfUrl]) {
                grp = new THREE.Group();
                const rawClone = window.__gltfCache[gltfUrl].clone(true);
                if (layer.up_axis !== "z") rawClone.rotation.x = Math.PI / 2;
                rawClone.updateMatrixWorld(true);
                const box = new THREE.Box3().setFromObject(rawClone);
                const size = new THREE.Vector3();
                const center = new THREE.Vector3();
                box.getSize(size);
                box.getCenter(center);
                const normH = Math.max(1e-4, size.z || size.y || 1);
                rawClone.position.set(-center.x, -center.y, -box.min.z);
                const holder = new THREE.Group();
                holder.add(rawClone);
                holder.scale.setScalar(1 / normH);
                if (layer.powered === false) {
                  rawClone.traverse((ch) => {
                    if (ch.isMesh && ch.material) {
                      const m = ch.material.clone();
                      if (m.color) m.color.multiplyScalar(0.45);
                      if ("emissiveIntensity" in m) m.emissiveIntensity = 0.05;
                      ch.material = m;
                    }
                  });
                }
                if (layer.altitude_arc_m > 0) {
                  // Elevated aircraft casts detached ground shadow directly on terrain below
                } else {
                  addGroundShadow(grp, 0.72);
                }
                grp.add(holder);
              } else if (layer.model === "aircraft") grp = buildAircraftModel(layer);
              else if (layer.model === "transmission_tower") grp = buildTransmissionTowerModel(layer);
              else if (layer.model === "substation") grp = buildSubstationModel(layer);
              else if (layer.model === "solar_farm") grp = buildSolarFarmModel(layer);
              else if (layer.model === "survey_vessel") grp = buildSurveyVesselModel(layer);
              else grp = buildTransmissionTowerModel(layer);
              const mats = [];
              const seenMats = new Set();
              grp.traverse((ch) => {
                if (ch.isMesh) {
                  ch.castShadow = true;
                  ch.receiveShadow = true;
                  const matList = Array.isArray(ch.material) ? ch.material : (ch.material ? [ch.material] : []);
                  for (const m of matList) {
                    if (m && !seenMats.has(m)) {
                      seenMats.add(m);
                      mats.push({
                        mat: m,
                        baseOpacity: typeof m.opacity === "number" ? m.opacity : 1.0,
                        baseTransparent: Boolean(m.transparent),
                      });
                    }
                  }
                }
              });
              scene.add(grp);

              // Detached ground shadow disk & glowing 3D parabolic contrail for airborne paths
              let flightShadow = null;
              if (Number(layer.altitude_arc_m || 0) > 0) {
                const sGeo = new THREE.CircleGeometry(0.85, 24);
                const sMat = new THREE.MeshBasicMaterial({
                  color: 0x020617,
                  transparent: true,
                  opacity: 0.36,
                  depthWrite: false,
                });
                flightShadow = new THREE.Mesh(sGeo, sMat);
                flightShadow.frustumCulled = false;
                flightShadow.visible = false;
                scene.add(flightShadow);
              }
              let contrailObj = null;
              if (layer.contrail === true && Array.isArray(layer.path) && layer.path.length >= 2) {
                const cSamples = 64;
                const arcM = Number(layer.altitude_arc_m || 0);
                const cPts = [];
                for (let ci = 0; ci <= cSamples; ci++) {
                  const cu = ci / cSamples;
                  const cp = sampleParabolicArcPose(layer.path, cu, { altitudeArcM: arcM, bankMaxDeg: 0 });
                  cPts.push(lngLatAltToLocal(cp.lng, cp.lat, groundElevM(cp.lng, cp.lat) + cp.altM));
                }
                const cCurve = new THREE.CatmullRomCurve3(cPts, false, "catmullrom", 0.25);
                const cLen = cCurve.getLength();
                const coreR = clamp(cLen * 0.0042, 450, 26000);
                const glowR = coreR * 2.6;
                const coreGeo = new THREE.TubeGeometry(cCurve, 96, coreR, 8, false);
                const glowGeo = new THREE.TubeGeometry(cCurve, 96, glowR, 8, false);
                const cHex = new THREE.Color(layer.contrail_hex || "#7CE0F9");
                const coreMat = new THREE.MeshBasicMaterial({
                  color: new THREE.Color("#FFFFFF").lerp(cHex, 0.35).multiplyScalar(1.65),
                  transparent: true,
                  opacity: 0.92,
                  depthWrite: false,
                });
                const glowMat = new THREE.MeshBasicMaterial({
                  color: cHex.clone().multiplyScalar(1.55),
                  transparent: true,
                  opacity: 0.36,
                  blending: THREE.AdditiveBlending,
                  depthWrite: false,
                });
                const coreMesh = new THREE.Mesh(coreGeo, coreMat);
                const glowMesh = new THREE.Mesh(glowGeo, glowMat);
                coreMesh.frustumCulled = false;
                glowMesh.frustumCulled = false;
                const cGrp = new THREE.Group();
                cGrp.add(glowMesh, coreMesh);
                cGrp.visible = false;
                scene.add(cGrp);
                contrailObj = {
                  group: cGrp,
                  coreGeo,
                  glowGeo,
                  coreMat,
                  glowMat,
                  totalCoreIdx: coreGeo.index ? coreGeo.index.count : 0,
                  totalGlowIdx: glowGeo.index ? glowGeo.index.count : 0,
                };
              }

              entry = { key, grp, mats, flightShadow, contrailObj };
              modelCache.set(key, entry);
            }
            activeModels.add(key);
            entry.grp.visible = visible && alpha > 0.01;
            if (!entry.grp.visible) {
              if (entry.flightShadow) entry.flightShadow.visible = false;
              if (entry.contrailObj) entry.contrailObj.group.visible = false;
              continue;
            }
            for (const item of entry.mats || []) {
              item.mat.opacity = item.baseOpacity * alpha;
              item.mat.transparent = item.baseTransparent || alpha < 0.999;
            }
            anyVisible3D = true;
            anyShadowCaster = true;

            let curCoord = layer.coord || [originLng, originLat];
            let headingDeg = layer.heading_deg || 0;
            let pitchDeg = 0;
            let rollDeg = 0;
            let extraAltM = Number(layer.altitude_m || 0);
            let pathU = 0;
            if (Array.isArray(layer.path) && layer.path.length >= 2) {
              const moveDur = layer.move_duration_s ?? Math.max(0.1, tEnd - tStart);
              pathU = clamp(seg(t, tStart, tStart + moveDur), 0, 1);
              if (Number(layer.altitude_arc_m || 0) > 0) {
                const pose = sampleParabolicArcPose(layer.path, pathU, {
                  altitudeArcM: Number(layer.altitude_arc_m),
                  bankMaxDeg: Number(layer.bank_deg ?? 20),
                });
                curCoord = [pose.lng, pose.lat];
                extraAltM += pose.altM;
                if (layer.auto_heading !== false) {
                  headingDeg = pose.headingDeg + Number(layer.heading_offset_deg || 0);
                  pitchDeg = pose.pitchDeg;
                  rollDeg = pose.rollDeg;
                }
              } else {
                curCoord = samplePolylineCoord(layer.path, pathU);
                if (layer.auto_heading !== false) {
                  const cA = samplePolylineCoord(layer.path, Math.max(0, pathU - 0.02));
                  const cB = samplePolylineCoord(layer.path, Math.min(1, pathU + 0.02));
                  const pA = lngLatAltToLocal(cA[0], cA[1], 0);
                  const pB = lngLatAltToLocal(cB[0], cB[1], 0);
                  const dx = pB.x - pA.x, dy = pB.y - pA.y;
                  if (Math.hypot(dx, dy) > 1e-3) {
                    headingDeg = (Math.atan2(-dx, dy) * 180) / Math.PI + Number(layer.heading_offset_deg || 0);
                  }
                }
              }
            }
            if (Number(layer.spin_rps || 0) !== 0) {
              headingDeg += Math.max(0, t - tStart) * Number(layer.spin_rps) * 360;
            }
            const groundElev = layer.model === "survey_vessel" ? 0 : groundElevM(curCoord[0], curCoord[1]);
            const pos = lngLatAltToLocal(curCoord[0], curCoord[1], groundElev + extraAltM);
            const hMeters = metersForScreenPx(
              layer.height_px ?? 95,
              curCoord[1],
              curZoom,
              layer.ref_zoom ?? curZoom,
              layer.scale_coupling ?? 0.46,
              layer.min_scale ?? 0.45,
              layer.max_scale ?? 2.8
            );
            const riseP = layer.rise_duration_s
              ? easeOutBack(seg(t, tStart, tStart + layer.rise_duration_s))
              : 1.0;
            const exitSc = (layer.exit_scale_down_s && t > tEnd - layer.exit_scale_down_s)
              ? 1 - easeInCubic(seg(t, tEnd - layer.exit_scale_down_s, tEnd))
              : 1.0;
            const scXY = hMeters * clamp(exitSc, 0.01, 1.5);
            const scZ = hMeters * clamp(riseP, 0.02, 1.15) * clamp(exitSc, 0.01, 1.5);
            entry.grp.position.copy(pos);
            entry.grp.rotation.order = "ZXY";
            entry.grp.rotation.set(
              (pitchDeg * Math.PI) / 180,
              (rollDeg * Math.PI) / 180,
              (headingDeg * Math.PI) / 180
            );
            entry.grp.scale.set(scXY, scXY, scZ);
            if (entry.flightShadow) {
              const gPos = lngLatAltToLocal(curCoord[0], curCoord[1], groundElev + 25);
              entry.flightShadow.position.copy(gPos);
              entry.flightShadow.scale.setScalar(scXY * 0.78);
              entry.flightShadow.material.opacity = 0.34 * alpha;
              entry.flightShadow.visible = true;
            }
            if (entry.contrailObj) {
              const cObj = entry.contrailObj;
              const drawFrac = clamp(pathU, 0, 1);
              cObj.coreGeo.setDrawRange(0, Math.floor((cObj.totalCoreIdx * drawFrac) / 3) * 3);
              cObj.glowGeo.setDrawRange(0, Math.floor((cObj.totalGlowIdx * drawFrac) / 3) * 3);
              cObj.coreMat.opacity = 0.90 * alpha;
              cObj.glowMat.opacity = 0.36 * alpha;
              cObj.group.visible = drawFrac > 0.005;
            }
            activeShadowBox.expandByPoint(new THREE.Vector3(pos.x - scXY, pos.y - scXY, Math.min(pos.z, groundElev)));
            activeShadowBox.expandByPoint(new THREE.Vector3(pos.x + scXY, pos.y + scXY, pos.z + scZ));
          } else if (layer.type === "volume_3d") {
            const key = layer.id || ("vol_" + idx);
            let entry = volumeCache.get(key);
            if (!entry) {
              const grp = new THREE.Group();
              const wM = Number(layer.width_m || 10000);
              const lM = Number(layer.length_m || 10000);
              const hM = Number(layer.height_m || 1200);
              const boxGeo = new THREE.BoxGeometry(wM, lM, hM);
              const wallMat = new THREE.MeshStandardMaterial({
                color: new THREE.Color(layer.fill_hex || "#F59E0B"),
                emissive: new THREE.Color(layer.fill_hex || "#F59E0B"),
                emissiveIntensity: 0.35,
                transparent: true,
                opacity: layer.fill_alpha ?? 0.32,
                depthWrite: false,
                side: THREE.DoubleSide,
              });
              const boxMesh = new THREE.Mesh(boxGeo, wallMat);
              boxMesh.position.set(0, 0, hM * 0.5);
              grp.add(boxMesh);

              const edgeMat = new THREE.LineBasicMaterial({
                color: new THREE.Color(layer.edge_hex || "#FEF08A"),
                transparent: true,
                opacity: 0.95,
              });
              const edges = new THREE.LineSegments(new THREE.EdgesGeometry(boxGeo), edgeMat);
              edges.position.set(0, 0, hM * 0.5);
              grp.add(edges);

              if (layer.grid_top !== false) {
                const topTex = makeVolumeTopTex(layer.edge_hex || "#FEF08A");
                const topMat = new THREE.MeshBasicMaterial({
                  map: topTex,
                  transparent: true,
                  opacity: 0.85,
                  side: THREE.DoubleSide,
                  depthWrite: false,
                });
                const topPlane = new THREE.Mesh(new THREE.PlaneGeometry(wM, lM), topMat);
                topPlane.position.set(0, 0, hM + 2);
                grp.add(topPlane);
              }
              scene.add(grp);
              entry = { key, grp, wallMat, edgeMat, baseFillAlpha: layer.fill_alpha ?? 0.32 };
              volumeCache.set(key, entry);
            }
            activeVolumes.add(key);
            entry.grp.visible = visible && alpha > 0.01;
            if (!entry.grp.visible) continue;
            anyVisible3D = true;
            const c = layer.coord || [originLng, originLat];
            const pos = lngLatAltToLocal(c[0], c[1], groundElevM(c[0], c[1]));
            const riseP = layer.rise_duration_s ? easeOutCubic(seg(t, tStart, tStart + layer.rise_duration_s)) : 1.0;
            entry.grp.position.copy(pos);
            entry.grp.rotation.set(0, 0, ((layer.heading_deg || 0) * Math.PI) / 180);
            entry.grp.scale.set(1, 1, clamp(riseP, 0.02, 1.0));
            entry.wallMat.opacity = entry.baseFillAlpha * alpha;
            entry.edgeMat.opacity = 0.95 * alpha;
          }
        }

        for (const [k, v] of cableCache.entries()) if (!activeCables.has(k)) v.group.visible = false;
        for (const [k, v] of modelCache.entries()) {
          if (!activeModels.has(k)) {
            v.grp.visible = false;
            if (v.flightShadow) v.flightShadow.visible = false;
            if (v.contrailObj) v.contrailObj.group.visible = false;
          }
        }
        for (const [k, v] of volumeCache.entries()) if (!activeVolumes.has(k)) v.grp.visible = false;
        for (const [k, v] of countryBlockCache.entries()) if (!activeBlocks.has(k)) v.grp.visible = false;

        hasActive3D = anyVisible3D;
        if (anyShadowCaster && !activeShadowBox.isEmpty()) {
          const boxCenter = new THREE.Vector3();
          const boxSize = new THREE.Vector3();
          activeShadowBox.getCenter(boxCenter);
          activeShadowBox.getSize(boxSize);
          const rad = Math.max(100, boxSize.length() * 0.68);
          keySun.target.position.set(boxCenter.x, boxCenter.y, 0);
          keySun.position.set(
            boxCenter.x + SUN_VEC.x * rad * 2.2,
            boxCenter.y + SUN_VEC.y * rad * 2.2,
            Math.max(rad * 0.6, SUN_VEC.z * rad * 2.2)
          );
          keySun.shadow.camera.left = -rad;
          keySun.shadow.camera.right = rad;
          keySun.shadow.camera.top = rad;
          keySun.shadow.camera.bottom = -rad;
          keySun.shadow.camera.near = rad * 0.1;
          keySun.shadow.camera.far = rad * 6.0;
          keySun.shadow.camera.updateProjectionMatrix();
          keySun.shadow.normalBias = Math.max(0.02, rad * 0.0005);
          shadowGround.position.set(boxCenter.x, boxCenter.y, 0.02);
          shadowGround.scale.set(rad * 4.5, rad * 4.5, 1);
          shadowGround.visible = true;
        } else {
          shadowGround.visible = false;
        }
      }

      return update3DScene;
    }

    window.__drawSceneLayers = function(layers, t) {
      if (__update3DScene) {
        __update3DScene(layers, t);
      }
      drawLayers(layers, t);
      if (__update3DScene) {
        map.triggerRepaint();
        return new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res)));
      }
    };

    // Scratch compositing canvas shared between sub-frame shutter accumulation and radial cut blur.
    const cutBlurSrc = document.createElement("canvas");
    cutBlurSrc.width = W; cutBlurSrc.height = H;
    const cutBlurSrcCtx = cutBlurSrc.getContext("2d");

    // Optical sub-frame shutter accumulator with arbitrary per-sample weights (cosine/trapezoid window).
    // Composite map + overlay at full alpha into cutBlurSrc first so overlays do not double-blend over the basemap.
    window.__beginShutterAccum = function() {
      compCanvas.style.display = "block";
      compCtx.clearRect(0, 0, W, H);
    };
    window.__accumSubframe = function(weightOrIdx, cumWeight) {
      cutBlurSrcCtx.save();
      cutBlurSrcCtx.clearRect(0, 0, W, H);
      if (Math.abs(window.__currentRoll) > 0.01) {
        const sc = computeRollOverscan(window.__currentRoll);
        cutBlurSrcCtx.translate(W * 0.5, H * 0.5);
        cutBlurSrcCtx.rotate((window.__currentRoll * Math.PI) / 180);
        cutBlurSrcCtx.scale(sc, sc);
        cutBlurSrcCtx.translate(-W * 0.5, -H * 0.5);
      }
      cutBlurSrcCtx.drawImage(map.getCanvas(), 0, 0, W, H);
      cutBlurSrcCtx.drawImage(ovCanvas, 0, 0, W, H);
      cutBlurSrcCtx.restore();

      compCtx.save();
      const blendAlpha = (cumWeight != null && cumWeight > 0)
        ? clamp(Number(weightOrIdx) / Number(cumWeight), 0, 1)
        : (1 / (Number(weightOrIdx) + 1));
      compCtx.globalAlpha = blendAlpha;
      compCtx.drawImage(cutBlurSrc, 0, 0, W, H);
      compCtx.restore();
    };
    window.__endShutterAccum = function() {
      compCanvas.style.display = "none";
    };

    // Radial zoom blur around the frame centre for act cuts. Reads the shutter
    // composite when one is showing, otherwise the map and overlay canvases with the
    // current roll, then averages scaled copies from 1 to 1 + amount into the
    // composite canvas. The caller hides the composite after capture.
    window.__cutBlurComposite = function(amount, copies) {
      cutBlurSrcCtx.save();
      cutBlurSrcCtx.clearRect(0, 0, W, H);
      if (compCanvas.style.display === "block") {
        cutBlurSrcCtx.drawImage(compCanvas, 0, 0, W, H);
      } else {
        if (Math.abs(window.__currentRoll || 0) > 0.01) {
          const sc = computeRollOverscan(window.__currentRoll);
          cutBlurSrcCtx.translate(W * 0.5, H * 0.5);
          cutBlurSrcCtx.rotate((window.__currentRoll * Math.PI) / 180);
          cutBlurSrcCtx.scale(sc, sc);
          cutBlurSrcCtx.translate(-W * 0.5, -H * 0.5);
        }
        cutBlurSrcCtx.drawImage(map.getCanvas(), 0, 0, W, H);
        cutBlurSrcCtx.drawImage(ovCanvas, 0, 0, W, H);
      }
      cutBlurSrcCtx.restore();
      const n = Math.max(2, Math.min(24, Math.round(copies) || 12));
      compCanvas.style.display = "block";
      compCtx.save();
      compCtx.clearRect(0, 0, W, H);
      for (let k = 0; k < n; k++) {
        const sc = 1 + amount * (k / (n - 1));
        compCtx.globalAlpha = 1 / (k + 1);
        compCtx.setTransform(sc, 0, 0, sc, W * 0.5 * (1 - sc), H * 0.5 * (1 - sc));
        compCtx.drawImage(cutBlurSrc, 0, 0, W, H);
      }
      compCtx.restore();
    };`;
}
