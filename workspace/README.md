# Workspace — ruang project lokal

Folder ini untuk **job edit aktif**: probe, plan, compile, render, master.  
Isi diabaikan git (kecuali README ini). Sumber brand tetap di `profiles/`, studi komponen di `studies/`.

## Layout yang disarankan

```text
workspace/
  <job_id>/
    brief.md                 # opsional: brief manusia
    probes/                  # MediaProbeResult JSON
    transcripts/             # NormalizedTranscript JSON
    plans/                   # EditPlan JSON
    hf_project/              # output vedit compile
    renders/                 # HyperFrames / FFmpeg intermediates
    masters/                 # deliverable final
    audit/                   # vedit audit reports
```

## Contoh alur singkat

```bash
JOB=workspace/geoverum_sulawesi_$(date +%Y%m%d)
mkdir -p "$JOB"/{probes,transcripts,plans,hf_project,renders,masters,audit}

packages/director-py/.venv/bin/vedit probe analyze \
  --input /path/to/source.mp4 \
  --output "$JOB/probes/source.json"

packages/director-py/.venv/bin/vedit director plan \
  --probe-file "$JOB/probes/source.json" \
  --policy-file profiles/brands/geoverum/brand_style_policy.json \
  --brand-dir profiles/brands/geoverum \
  --platform shorts_9x16_1080p \
  --output "$JOB/plans/edit_plan.json"

packages/director-py/.venv/bin/vedit compile \
  --plan-file "$JOB/plans/edit_plan.json" \
  --out-dir "$JOB/hf_project"
```

Jangan simpan master final jangka panjang di sini bila sudah di-ship; pindahkan ke penyimpanan deliverable di luar repo bila perlu.
