# OCT Fluid Segmentation in CODA: Implementation Plan

**Goal:** a user uploads a Heidelberg Spectralis OCT volume (DICOM) in the dashboard. They get back per-B-scan IRF / SRF / PED segmentation and total fluid volumes (whole scan, ETDRS 1 mm, ETDRS 6 mm) in a report modelled on the RetInSight Fluid Monitor. The model runs on the GPU when one is present and falls back to CPU otherwise. The design should also make it easy to add or replace models later.

**Out of scope for now:** longitudinal progression and per-patient history, auto fovea detection, PDF export, DICOM-SEG export, other OCT vendors.

---

## 1. Inputs and what they tell us

### 1.1 Model: `inference-service/models/oct-fluid-spectralis/1.0.0/`

The reference folder supplied for this work was temporary. Everything the service needs from it now lives in `inference-service/`: the weights, plus the notebook, `inference_config.json`, training history, `val_split.json` and `test_predicted_volumes.csv` under the package's `training/` folder. The RetInSight screenshot is in `docs/reference/` and the sample DICOMs are in `tests/data/`.

| Item | Value |
|---|---|
| Architecture | Reference attention U-Net, 2D, 9.44 M params, input `(None, None, 1)` (fully convolutional) |
| Output | softmax over 4 classes: 0 bg, 1 IRF, 2 SRF, 3 PED |
| Framework | TensorFlow 2.21.0 / Keras 3.13.2, saved as `best_model.keras` (114 MB) |
| Training precision | `mixed_float16` (global policy at save time) |
| Training data | RETOUCH Spectralis Training set (24 vols × 49 B-scans, 496×512, uint16 `.mhd`) |
| Validation | 10 % of B-scans per volume (not patient-held-out); best val score 0.833 (epoch 29) |
| Preprocessing | see `training/inference_config.json` and §5.2 |
| Reference outputs | `training/test_predicted_volumes.csv` (e.g. TEST015: IRF 0.7169, SRF 0.00435, PED 1.6877 mm³) |

### 1.2 Sample DICOMs: `inference-service/tests/data/sample_spectralis/*.dcm` (local only, gitignored: patient data)

All 4 files have the same structure:

| Tag | Value | Consequence |
|---|---|---|
| SOP Class | `1.2.840.10008.5.1.4.1.1.77.1.5.4` (Ophthalmic Tomography, multi-frame) | Validate this on upload |
| Manufacturer / Model | `Heidelberg Engineering` / `Spectralis` | Validate this; reject other vendors |
| Frames × Rows × Cols | 31 × 496 × 768, uint16, MONOCHROME2, uncompressed LE | |
| Top-level `PixelSpacing` / `SliceThickness` | **absent** | Must read from functional groups |
| `SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing` | `[0.0038717, 0.011484]` = **[row = axial, col = lateral]** mm | Map to the notebook's `spacing_xy = (lateral, axial)`; **do not** pass it through in DICOM order |
| `…PixelMeasuresSequence[0].SliceThickness` | `0.244673` mm | B-scan spacing |
| `PerFrameFunctionalGroupsSequence[i].PlanePositionSequence.ImagePositionPatient` | `[0, 0, i × 0.244673]` | Authoritative inter-B-scan spacing; also gives frame order |
| `FrameContentSequence.InStackPositionNumber` | 1…31 | Frame order |
| `ImageLaterality` | `L` | Shown in the report (OD/OS); used for en-face orientation |
| `ImageType` | `DERIVED\SECONDARY` | These look like converted exports, not native HEYEX exports |
| Pixel values | **0–100 only** (101 levels), 30–45 % zeros, ~4 % saturated at 100 | **Intensity domain differs from training** (see §1.4) |
| Linked SLO fundus image | **none** | En-face maps are drawn on the OCT grid with no fundus background |

Scan geometry: 768 × 0.011484 = **8.82 mm wide**, 31 × 0.2447 = **7.34 mm tall** (a 30°×25° raster). That covers the full ETDRS 6 mm circle.

### 1.3 RETOUCH golden case: `~/Desktop/OCT_Others/RETOUCH/RETOUCH-TestSet-Spectralis/TEST015`

`oct.mhd` / `oct.raw` are uint16, 49 × 496 × 512, spacing `(0.010244, 0.003872, 0.110993)` mm, values 0–65535 (median ~6900, only 9 % zeros, speckled grey background).

### 1.4 Risks found while inspecting the data (must be resolved in Phase 0)

1. **Intensity domain shift.**
   - RETOUCH volumes are 16-bit with a grey, speckled vitreous and choroid.
   - The sample DICOMs are quantised to 0–100 with a black (0) vitreous and an apparently different contrast transfer curve.
   - The notebook's percentile stretch plus z-score fixes scale and offset but not curve shape or quantisation.
   - Gamma augmentation in training (0.7–1.5) gives some robustness, but the model may still over- or under-segment.
   - **Mitigation:** an `input_harmonization` step selected per input source in the model manifest (histogram matching to a RETOUCH reference CDF vs. gamma vs. none), chosen experimentally in Phase 0.
2. **Black vitreous counted as padding.** `edge_padding()` marks every zero run connected to an image edge as padding. In the DICOMs the black vitreous above the retina touches the top edge, so it would be excluded from normalisation statistics and forced to background. Background there is harmless, but excluding it shifts the z-score statistics compared with training.
   - **Mitigation:** compare (a) the notebook's `edge_padding` against (b) treating only fully-zero columns and rows as padding (the true padding strips, e.g. the black strip at cols ~740–768). Pick one in Phase 0.
3. **Lateral crop.** After resampling to 0.011174 mm/px, a 768-px B-scan becomes ~789 px. The notebook's fixed 576-px canvas would **center-crop away ~2.4 mm** of the 8.8 mm scan.
   - **Mitigation:** the network is fully convolutional, so use a dynamic canvas width `W_canvas = max(576, ceil16(W_res))`.
   - For RETOUCH-size inputs (W_res ≤ 576) this is identical to the notebook, so the golden test still applies.
   - Verify that predictions near the image edges look sane.
4. ~~**Mixed precision on CPU.**~~ *Resolved in Phase 0:* the saved layers use float32 policies, so the file loads and runs unchanged on CPU and GPU.
5. **No ground truth on the DICOMs.** We can only check them visually. The golden test protects the pipeline code, not the domain shift. See §11, question 1.

---

## 2. Architecture decision

### 2.1 Separate service, same VM, same compose

We add a new **`inference-service`**: one Docker image run as **two containers**.

```
Browser
  └─► ui (nginx :80)                         ── /inference/* proxied like other API paths
        └─► api-gateway (:8000)              ── verify_token, streams uploads, forwards Authorization
              └─► inference-api (:8002)      ── FastAPI: validate upload, create job, serve results (no TensorFlow import)
                    │   writes upload → /data/jobs/{id}/input.dcm
                    │   INSERT job (status=queued)
                    ▼
              inference-db (Postgres 16)     ── jobs table = the queue (SELECT … FOR UPDATE SKIP LOCKED)
                    ▲
              inference-worker               ── loads model(s) once, claims jobs, runs pipeline, writes results
                    │   GPU (T4) via nvidia runtime, else CPU
                    ▼
              /data volume (inference_data)  ── masks, PNG renders, result.json
              /models (read-only bind mount of inference-service/models) ── versioned model packages
```

**Why a separate service (not inside dataset-service or the gateway):**

| Concern | Reason |
|---|---|
| Dependencies | TF with CUDA is ~5 GB; the other services are `python:3.11-slim` |
| GPU | Only this service needs the NVIDIA runtime |
| Fault isolation | An OOM or CUDA crash in inference must not take down auth, query or datasets |
| Release cadence | Models change independently of the dashboard |
| Portability | It is reachable only via `INFERENCE_SERVICE_URL`, so it can later move to a dedicated GPU VM, GKE or Cloud Run GPU with only a config change |

**Why split API and worker:**
- The API stays responsive while the GPU is busy.
- Uvicorn workers don't each load a copy of the model.
- A worker crash doesn't drop HTTP traffic.
- Throughput scales by adding workers (one per GPU).

**Why a Postgres queue instead of Celery or Redis:**
- Jobs are rare and heavy, a pattern that `SKIP LOCKED` handles well.
- It follows the existing one-Postgres-per-service pattern.
- It needs no new infrastructure.
- If load grows, Redis or RQ can replace it behind the same `jobs` table and API.

**What we are *not* doing yet:** Triton or TF Serving. Our pre- and post-processing is custom NumPy/OpenCV that those servers wouldn't run for us. The adapter layer (§4) is where a Triton client would plug in later.

### 2.2 Model packaging (the swap-ability contract)

Model packages live **inside `inference-service/models/`**, so the service is self-contained. Tracked in git: the manifest, model card, intensity reference, and from `training/` the notebook, `inference_config.json` and `history.csv`. Gitignored: the weights (114 MB), the rest of `training/` and the `docs/reference/` images. Packages are kept out of the Docker image (`.dockerignore`) and bind-mounted read-only at `/models`, so swapping a model never requires rebuilding the ~5 GB TensorFlow image:

```
coda-dashboard/inference-service/models/       # *.keras gitignored; weights from scripts/fetch_models.sh (GCS) or copied manually
  oct-fluid-spectralis/
    1.0.0/
      model.yaml
      best_model.keras
      intensity_reference.npy                 # (if Phase 0 chooses histogram matching) RETOUCH Spectralis CDF
      model_card.md                           # training data, metrics, intended use, limitations
      training/                               # notebook, inference_config.json, history.csv tracked; val_split, trained.json, reference volumes gitignored
```

`model.yaml` (example; the schema is validated with Pydantic at worker start):

```yaml
id: oct-fluid-spectralis
version: 1.0.0
display_name: "OCT Fluid (IRF/SRF/PED) — Spectralis"
task: segmentation-2d-per-bscan
modality: OPT
adapter: refattn_unet_v1          # Python adapter class registered in the service
framework: keras
weights: best_model.keras
sha256: "<filled at packaging time>"
input:
  supported_manufacturers: ["Heidelberg Engineering"]
  supported_models: ["Spectralis"]
  target_spacing_mm: {lateral: 0.011174, axial: 0.003872}
  canvas: {height: 512, min_width: 576, multiple_of: 16}
  clip_percentiles: [0.5, 99.5]
  padding: edge_connected_zero_runs            # as trained (.mhd)
  padding_overrides: {dicom-opt: zero_border}  # Phase 0 decision
  harmonization:
    default: {method: none}
    dicom-opt: {method: histogram_match, reference: intensity_reference.npy, dither: true}
classes:
  1: {name: IRF, label: "Intraretinal fluid", color: "#E53935"}
  2: {name: SRF, label: "Subretinal fluid",   color: "#FBC02D"}
  3: {name: PED, label: "Pigment epithelial detachment", color: "#1E88E5"}
quantification: {units: nL, etdrs_diameters_mm: [1, 3, 6]}
report:                                        # added in Phase 1: report text ships with the model
  disclaimer: "Research use only. Not for clinical diagnosis."
  warnings:
    default: ["Model trained and validated on RETOUCH Spectralis data only …"]
    dicom-opt: ["DICOM input is intensity-harmonized to the training data …"]
```

To add a model:
1. Drop in a new package directory.
2. Add an adapter class, but only if its pre- or post-processing differs from an existing one.
3. Add it to `ENABLED_MODELS`.

No changes are needed to the API, the UI contract or the quantification code. Every job records `model_id@version` and the sha256, so results stay reproducible after upgrades.

---

## 3. Repository layout (new and changed files)

```
coda-dashboard/
  docker-compose.yml                 # + inference-api, inference-worker, inference-db, volumes
  docker-compose.gpu.yml             # NEW: GPU reservation override for inference-worker
  inference-service/                 # NEW
    Dockerfile
    .dockerignore                    # models/, tests/data/, .venv/, experiments/out/
    models/                          # model packages (weights gitignored), bind-mounted at /models
    scripts/fetch_models.sh          # NEW: gsutil rsync gs://<bucket>/models → ./models (optional)
    docs/reference/retinsight.jpeg   # gitignored: report layout reference
    requirements.txt                 # tensorflow[and-cuda]==2.21.0, keras==3.13.2, pydicom, opencv-python-headless, numpy,
                                     # scipy, fastapi, uvicorn, sqlalchemy, psycopg2-binary, python-jose, python-multipart, pydantic, pyyaml, pillow
    requirements-dev.txt             # pytest, httpx
    config.py                        # env: DATABASE_URL, DATA_DIR, MODELS_DIR, ENABLED_MODELS, JWT_*, MAX_UPLOAD_MB, RESULT_TTL_DAYS
    db.py                            # SQLAlchemy models: InferenceJob, InferenceWorker
    auth.py                          # JWT validation (CurrentUser; rejects oauth_access tokens)
    storage.py                       # per-job files under DATA_DIR/jobs/{id}/
    main.py                          # FastAPI app (inference-api)
    worker.py                        # job loop (inference-worker)
    .env.example                     # tracked (gitignore exception); copy to .env
    routes/
      jobs.py                        # /inference/models, /inference/jobs…
    core/
      volume.py                      # OctVolume dataclass (vendor-neutral)
      ingest/
        dicom_opt.py                 # DICOM OPT → OctVolume (+ validation)
        mhd.py                       # .mhd/.raw → OctVolume (golden test + CLI only)
      manifest.py                    # model.yaml schema (Pydantic)
      registry.py                    # load_manifests (API, no TF) / load_adapters (worker: weights, sha256, device, warm-up)
      adapters/
        base.py                      # ModelAdapter ABC: preprocess / predict / postprocess
        refattn_unet_v1.py           # port of the notebook (prepare_bscan, normalise, predict_labels, canvas_to_original)
      quantify.py                    # volumes (total / ETDRS), en-face thickness maps, per-B-scan stats
      render.py                      # B-scan PNGs, RGBA overlays, en-face height maps (ETDRS grid is drawn in the UI)
      pipeline.py                    # ingest → adapter → quantify → render → result.json
    cli.py                           # `python cli.py run <file> [--package DIR] [--out DIR]` (debug; --out runs the full pipeline)
    tests/
      test_dicom_ingest.py
      test_preprocessing.py          # canvas math, padding, dynamic width, round-trip canvas_to_original
      test_quantify.py               # synthetic masks → exact nL / ETDRS numbers
      test_golden_retouch.py         # TEST015 regression (skipped if data/model absent)
      test_jobs_api.py               # auth, validation errors, ownership, API does not import TensorFlow
      test_worker.py                 # job lifecycle with a fake adapter: ETDRS, failure, cancel, requeue, TTL, take-over
      test_render.py                 # overlay colours, en-face opacity, display window
      data/                          # gitignored: sample patient DICOMs for local runs
  api-gateway/main.py                # + /inference/* proxy routes
  ui/nginx.conf                      # + inference in proxied paths, client_max_body_size, timeouts
  ui/src/router.jsx                  # + /oct-analysis, /oct-analysis/:jobId
  ui/src/components/layout/Sidebar.jsx   # + "OCT Fluid Analysis" nav item
  ui/src/pages/OctAnalysisPage.jsx       # NEW: upload + job list
  ui/src/pages/OctReportPage.jsx         # NEW: RetInSight-style report
  ui/src/components/oct/…                # NEW: UploadDropzone, JobStatus, VolumeTable, EnfaceMap, BscanViewer
.gitignore                           # + inference-service weights, part of training/, docs/reference/, tests/data, .venv, experiments/out
```

---

## 4. Service internals

### 4.1 `OctVolume` (the vendor-neutral contract between ingest and models)

```python
@dataclass
class OctVolume:
    voxels: np.ndarray            # (Z, H, W) float32, B-scan order = superior→inferior as acquired
    spacing_lateral_mm: float     # x, along a B-scan
    spacing_axial_mm: float       # y, depth
    bscan_positions_mm: np.ndarray  # (Z,) slow-axis position of each B-scan
    laterality: str | None        # "OD" | "OS"
    manufacturer: str
    device_model: str
    study_date: str | None
    source_format: str            # "dicom-opt" | "mhd"
    meta: dict                    # non-PHI only
```

Inter-B-scan spacing per slice is `np.gradient(bscan_positions_mm)`. Falls back to `SliceThickness` if positions are missing.

### 4.2 DICOM ingest (`core/ingest/dicom_opt.py`)

- `pydicom.dcmread(..., force=False)`. Reject anything that is not the OPT SOP class (`422 unsupported_sop_class`).
- Pixel spacing lookup order:
  1. `SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing`
  2. Per-frame `PixelMeasuresSequence`
  3. Top-level `PixelSpacing`

  Interpret it as `[row(axial), col(lateral)]`.
- B-scan positions come from per-frame `PlanePositionSequence.ImagePositionPatient`. The coordinate that varies is the slow axis. Frames are sorted by `InStackPositionNumber`.
  - Fallback: `SliceThickness` × index, then `SpacingBetweenSlices`.
  - If no spacing can be found: `422 missing_spacing`. Volumes must never be computed with guessed spacing.
- Apply `RescaleSlope` / `RescaleIntercept` if present, and invert if the image is `MONOCHROME1`.
- Validate `Manufacturer` and `ManufacturerModelName` against the model manifest:
  - Other vendors get `422 unsupported_device`, naming the supported devices.
  - Every model the service ships declares vendors; a model that declares none would accept anything with a warning.
- **PHI:**
  - Read only the needed tags. Patient name, ID and birth date are **never** written to the DB, logs or `result.json`.
  - The uploaded file is deleted after processing (`KEEP_INPUT=false` default).
  - Derived outputs (masks, PNGs) are kept for `RESULT_TTL_DAYS` (default 30) and then purged by the worker.

### 4.3 Adapter (`core/adapters/refattn_unet_v1.py`)

This is a faithful port of notebook §1 and §6, with the Phase 0 decisions applied:

1. **Harmonize** (if configured): histogram-match the non-padding pixels to `intensity_reference.npy`, or apply gamma.
2. **`prepare_bscan`:**
   - Resize to the target spacing: INTER_AREA when shrinking, INTER_LINEAR when enlarging, applied separately per axis as in the notebook.
   - Detect padding (configured strategy), percentile-stretch to uint8 1..255 with padding = 0, then place on the canvas.
   - Canvas width is dynamic: `max(576, ceil16(W_res))`. Height is 512 (crop or pad rows as in the notebook).
3. **`normalise`:** per-B-scan z-score over non-padding pixels.
4. **`predict`:**
   - Batch of 8 with fixed batch shape to avoid retracing; on CPU batch 4.
   - Use `model(x, training=False)` inside a `tf.function` instead of `predict_on_batch`.
   - Take `argmax`, then set padding to 0.
5. **`postprocess`:** `canvas_to_original` puts the labels back on the native B-scan grid (Z, H, W) using nearest-neighbour resampling.

Quantification uses the **native-grid** masks with native spacing, so results don't depend on the canvas. Phase 0 checks that this matches the notebook's canvas-based mm³ on TEST015 within tolerance. The notebook computes on the canvas with effective spacing, so small resampling differences are expected. If the gap is larger than the tolerance, compute on the canvas exactly as the notebook does.

### 4.4 Device selection (`core/registry.py`)

```python
gpus = tf.config.list_physical_devices("GPU")
for g in gpus: tf.config.experimental.set_memory_growth(g, True)
model = keras.models.load_model(path, compile=False)   # float32 layers: same file on CPU and GPU (Phase 0)
```

- Also set `TF_FORCE_GPU_ALLOW_GROWTH=true` and `TF_CPP_MIN_LOG_LEVEL=2`.
- Log the device at startup, expose it on `/inference/health` (`{"device": "GPU:Tesla T4" | "CPU"}`) and record it on every job.
- Warm up with one dummy batch at startup so the first user job doesn't pay for compilation.
- **Expected latency:**
  - T4: ~2–4 s for 31–97 B-scans, plus ingest and rendering.
  - CPU (16 cores): ~30–90 s.

### 4.5 Quantification (`core/quantify.py`)

For a label volume `L (Z,H,W)` on the native grid, with lateral spacing `dx`, axial spacing `dy` and per-B-scan spacing `dz[z]`:

- **Fluid height map (en-face), per class c:** `h_c[z, x] = count_y(L[z,:,x] == c) · dy` in µm. Shape (Z, W).
- **Volume of class c:** `V_c = Σ_z Σ_x h_c[z,x] · dx · dz[z]`, in mm³ × 1000 = **nL**. This is Cavalieri summation, the same as the notebook and how the model was validated.
- **ETDRS subfields:**
  - Center (x0, z0) defaults to the scan center.
  - The API accepts an override `center_mm={x, z}`, which recomputes volumes only, with no re-inference.
  - An A-scan at (x·dx, pos[z]) is in the circle of diameter D if its distance to the center is ≤ D/2.
  - Report D = 1 mm and 6 mm (RetInSight style) plus 3 mm.
- **"Interpolation":**
  - The **volume numbers** use Cavalieri summation. It is unbiased, matches validation, and for evenly spaced B-scans equals the integral of linear interpolation between B-scans.
  - Interpolation is used for the **en-face maps**: `h_c` is resampled from (Z × W) onto an isotropic grid (0.02 mm/px) with linear interpolation along the slow axis (`scipy.ndimage.zoom` / `cv2.resize`), which fills the 245 µm gaps between B-scans for display.
  - The ETDRS circle masks are also evaluated on this isotropic grid for display only. Numbers always come from the native-grid sums.
- **Per-B-scan stats:** pixel counts and area (mm²) per class, used for the B-scan list ("B-scans with fluid") and the viewer.

Unit tests use synthetic masks with known geometry, e.g. a cylinder of height 100 µm and radius 0.5 mm should give ≈ 78.5 nL.

### 4.6 Rendering (`core/render.py`)

All outputs are PNG, served via authenticated endpoints:
- `bscan/{z}.png`: the 8-bit display image on the native grid (same percentile stretch as preprocessing).
- `overlay/{z}.png`: a transparent RGBA label overlay in the manifest's class colors, alpha 0.55. Stacking it in the UI lets the overlay toggle without another request.
- `enface/{class}.png`: the isotropic height map with a colour ramp from 0 to 250 µm. The ETDRS grid is drawn **in the UI as SVG** so it moves when the center is adjusted.
- `enface/{class}.json` (optional): the raw height grid, if we later want hover readouts.

The masks are also saved as `labels.npz`. A downloadable `labels.nii.gz` (via `nibabel`) is optional and can come later.

### 4.7 Worker loop (`worker.py`)

```
startup: load registry (validate manifests + sha256), select device, warm up each ENABLED_MODELS entry
loop:
  BEGIN; SELECT * FROM inference_jobs WHERE status='queued' ORDER BY created_at
         FOR UPDATE SKIP LOCKED LIMIT 1; UPDATE status='running', started_at, worker_id; COMMIT
  run pipeline with progress callbacks → UPDATE progress (0–100), stage ("ingest"|"inference"|"quantify"|"render")
  success → status='succeeded', result_json, finished_at, duration_ms, device
  failure → status='failed', error_code, error_message (user-safe), full traceback to logs only
  delete input file unless KEEP_INPUT
periodically: requeue 'running' jobs whose heartbeat is older than 10 min (worker crash); purge results older than RESULT_TTL_DAYS
```

Concurrency is one job at a time per worker; on one T4, run one worker. Shutdown is graceful on SIGTERM: the current job finishes, then the worker exits.

### 4.8 Database (`inference-db`, table `inference_jobs`)

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID, indexed | From JWT `sub`; jobs are visible only to their owner (admins see all) |
| model_id, model_version, model_sha256 | text | Reproducibility |
| status | enum queued / running / succeeded / failed / cancelled | |
| stage, progress | text, int | For the UI progress bar |
| original_filename | text | Shown in the job list. Users should avoid patient names in file names; we also strip the filename to a basename and cap its length |
| input_meta | JSONB | Manufacturer, model, laterality, study_date, dims, spacing (no PHI) |
| result_json | JSONB | See §5.3 |
| error_code, error_message | text | |
| device, duration_ms, worker_id, heartbeat_at | | |
| attempts | int | Incremented on each claim; after `MAX_ATTEMPTS` lost runs the job fails with `worker_lost` |
| created_at, started_at, finished_at | timestamp (naive UTC) | Naive UTC, as in dataset-service, so the same code runs on Postgres and SQLite (tests) |

A second table, `inference_workers` (worker_id, device, models, started_at, heartbeat_at), is refreshed by each worker every `HEARTBEAT_SECONDS`. `/inference/health` reports a worker as online if it reported within `WORKER_ONLINE_SECONDS`.

Schema creation uses SQLAlchemy `create_all` at startup, matching dataset-service. Alembic can come later.

---

## 5. API contract

### 5.1 inference-api (internal, :8002). The gateway exposes the same paths

The JWT is validated in the service (shared `JWT_SECRET`), the same defence-in-depth pattern dataset-service uses. Everyone who is logged in may use it.

| Method & path | Purpose |
|---|---|
| `GET /inference/health` | No auth. `{status: ok\|degraded, device, models_enabled, models_loaded, workers_online, queue}` (worker heartbeat via DB) |
| `GET /inference/models` | Enabled models: id, version, display name, classes and colours, supported devices |
| `POST /inference/jobs` | multipart `file` (.dcm) + `model_id` → `202 {job_id}`. Synchronous validation errors (bad DICOM, wrong vendor, too large) → `4xx` before enqueueing |
| `GET /inference/jobs?skip&limit&status&all` | The user's jobs (id, filename, model, status, progress, eye, B-scans, created_at, headline volumes). `all=true` lists every user's jobs, for admins only |
| `GET /inference/jobs/{id}` | Status, progress and stage; when succeeded, includes `result` |
| `POST /inference/jobs/{id}/etdrs` | `{center_mm: {x, z}}` → recomputed ETDRS volumes (fast, no inference). The centre is saved in `result`; `{center_mm: null}` resets to the scan centre; a centre outside the scan gives `422 invalid_center` |
| `GET /inference/jobs/{id}/bscan/{z}.png` | B-scan image |
| `GET /inference/jobs/{id}/overlay/{z}.png` | Label overlay |
| `GET /inference/jobs/{id}/enface/{class}.png` | En-face height map |
| `GET /inference/jobs/{id}/labels.npz` | Raw masks download (labels + geometry) |
| `GET /inference/jobs/{id}/result.json` | Report download (added in Phase 1) |
| `DELETE /inference/jobs/{id}` | Delete the job and its files. A running job is marked `cancelled`; the worker stops at its next progress update and removes it |

**Errors:** every 4xx/5xx body is `{"detail": "<user-safe message>", "code": "<stable code>"}`, e.g. `invalid_dicom`, `unsupported_sop_class`, `unsupported_device`, `missing_spacing`, `empty_file`, `file_too_large` (413), `unknown_model`, `not_ready` (409), `not_found`. Failed jobs carry the same `{code, message}` in `error`; internal errors show a generic message, and the traceback goes to the logs only.

**Access:** no or invalid token → 401; connected-app (`oauth_access`) tokens → 403; another user's job → 404; admins can read any job. Result files are served only for `succeeded` jobs.

Images are fetched with `fetch` plus the Authorization header and turned into blob URLs, because a plain `<img src>` can't send the bearer token.

### 5.2 Preprocessing parameters (from `inference_config.json`, now in `model.yaml`)

| Setting | Value |
|---|---|
| `TARGET_XY_MM` | (0.011174 lateral, 0.003872 axial) |
| Canvas | 512 high × 576 wide, the minimum (dynamic width, see §1.4.3) |
| `CLIP_PCT` | (0.5, 99.5) |
| Normalisation | z-score over non-padding pixels |
| Padding | 0 |

### 5.3 `result` shape

```json
{
  "model": {"id": "oct-fluid-spectralis", "version": "1.0.0", "device": "GPU:Tesla T4"},
  "scan": {"manufacturer": "Heidelberg Engineering", "device_model": "Spectralis", "laterality": "OS",
           "study_date": "2025-01-01", "n_bscans": 31, "bscan_shape": [496, 768],
           "spacing_mm": {"lateral": 0.011484, "axial": 0.003872, "bscan": 0.244673},
           "field_mm": {"width": 8.82, "height": 7.34}},
  "classes": [{"id": 1, "name": "IRF", "label": "Intraretinal fluid", "color": "#E53935"}, …],
  "volumes_nl": {
    "total":  {"IRF": 261.5, "SRF": 0.3, "PED": 102.7},
    "etdrs_1mm": {"IRF": 54.4, "SRF": 0.3, "PED": 29.8},
    "etdrs_3mm": {…}, "etdrs_6mm": {…}
  },
  "etdrs_center_mm": {"x": 4.41, "z": 3.67, "source": "scan_center"},
  "bscans": [{"z": 0, "position_mm": 0.0, "area_mm2": {"IRF": 0.0, "SRF": 0.0, "PED": 0.012}}, …],
  "max_height_um": {"IRF": 212, "SRF": 18, "PED": 240},
  "enface": {"grid_mm_per_px": 0.02, "shape": [367, 441], "scale_max_um": 250},
  "warnings": ["Model validated on RETOUCH data only; DICOM input uses histogram harmonization."],
  "disclaimer": "Research use only. Not for clinical diagnosis."
}
```

---

## 6. Gateway, nginx and compose changes

**api-gateway/main.py:**
- Add `INFERENCE_SERVICE_URL`.
- Proxy routes for each path in §5.1, forwarding `Authorization`.
- **Uploads:** accept `UploadFile` and stream it to the service with `requests.post(files={"file": (name, upload.file, "application/dicom")}, data={"model_id": …})`. The gateway must not `await upload.read()` the whole file into memory.
- **Image endpoints:** `StreamingResponse` passthrough with the upstream `Content-Type`.
- **Timeouts:** upload 120 s; others use `DOCKER_API_TIMEOUT`.

**ui/nginx.conf:**
- Add `inference` to the proxied-paths regex: `^/(auth|datasets|users|query|role-changes|oauth|inference)`.
- `client_max_body_size 300m;` (scoped to that location) and `proxy_request_buffering off;` for streaming.
- `proxy_read_timeout 300s;`

**docker-compose.yml (base: works with or without a GPU):**

```yaml
  inference-api:
    build: ./inference-service
    command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
    env_file: [./inference-service/.env]
    depends_on: [inference-db]
    volumes: [inference_data:/data, ./inference-service/models:/models:ro]

  inference-worker:
    build: ./inference-service
    command: ["python", "worker.py"]
    env_file: [./inference-service/.env]
    depends_on: [inference-db]
    volumes: [inference_data:/data, ./inference-service/models:/models:ro]
    mem_limit: 10g
    restart: unless-stopped

  inference-db:
    image: postgres:16
    environment: {POSTGRES_DB: inference-db, POSTGRES_USER: coda, POSTGRES_PASSWORD: coda-pass}
    volumes: [inference_db_data:/var/lib/postgresql/data]
    # no host port: internal only

volumes:
  inference_data:
  inference_db_data:
```

**docker-compose.gpu.yml (GCP VM only):**

```yaml
services:
  inference-worker:
    deploy:
      resources:
        reservations:
          devices: [{driver: nvidia, count: 1, capabilities: [gpu]}]
```

Run on the VM with `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build`. Locally, plain `docker compose up` runs the worker on CPU.

**Dockerfile:**
- Base `python:3.11-slim`, then `pip install tensorflow[and-cuda]==2.21.0 keras==3.13.2 …`. The CUDA and cuDNN wheels come with the pip package, so no CUDA base image is needed and the same image runs on CPU.
- Install `libgl1`/`libglib2.0-0` only if not using `opencv-python-headless`.
- Image size: estimated ~5–6 GB, **measured 10.8 GB** in Phase 1 (CUDA/cuDNN wheels). Inference-api uses the same image (simpler); a slim API image is a possible later optimisation.

**`.env.example` for inference-service:** `DATABASE_URL`, `DATA_DIR=/data`, `MODELS_DIR=/models`, `ENABLED_MODELS=oct-fluid-spectralis@1.0.0`, `JWT_SECRET`, `JWT_ALGORITHM`, `MAX_UPLOAD_MB=300`, `RESULT_TTL_DAYS=30`, `KEEP_INPUT=false`.

### 6.1 GCP VM one-time GPU setup (T4)

1. Install the NVIDIA driver: GCP's `install-gpu-driver` script, or `sudo apt install nvidia-driver-550-server`. Reboot and check that `nvidia-smi` shows the Tesla T4.
2. Install `nvidia-container-toolkit`, then `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`.
3. Check: `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`.
4. Copy the weights into `coda-dashboard/inference-service/models/oct-fluid-spectralis/1.0.0/` (and `training/`, if wanted; `model.yaml`, `model_card.md` and `intensity_reference.npy` come with git) (manually, or from GCS via `scripts/fetch_models.sh`).
5. Bring up the stack with the GPU override. Check that `GET /inference/health` reports `GPU:Tesla T4`.

Memory budget on the 24 GB VM:
- Worker: ~2–3 GB host RAM for TF plus a 97-B-scan volume, so the 10 GB limit leaves headroom.
- T4: 16 GB VRAM; a batch of 8 × 512 × 800 in fp16 uses well under 4 GB.
- Everything else currently uses ~7 GB.

---

## 7. UI

### 7.1 Navigation and routes
- Sidebar item **"OCT Fluid Analysis"** (lucide `ScanEye` icon) → `/oct-analysis`, visible to all users.
- `/oct-analysis/:jobId` is the report page.

### 7.2 `OctAnalysisPage` (upload and jobs)
- **Model picker**, populated from `GET /inference/models`. Hidden when there is only one model, but the request still sends `model_id`.
- **Upload:** a drag-and-drop zone accepting `.dcm`, using `api.postForm` with upload progress. A note says "Heidelberg Spectralis OCT volume (DICOM)".
- **Validation errors:** 4xx responses are shown inline using the existing `ErrorBanner`, e.g. "This file is from Zeiss Cirrus; this model supports Heidelberg Spectralis only."
- **Jobs table:**
  - Columns: filename, eye, B-scans, model, status badge (queued / running with %, succeeded, failed), created, total IRF/SRF/PED nL, and a delete action.
  - Polls `GET /inference/jobs/{id}` every 2 s while any job is queued or running; clicking a row opens the report.

### 7.3 `OctReportPage` (modelled on the RetInSight report; our own design and branding)

Built with existing `StatCard` / `DataTable` styles and the design tokens:
1. **Header:** "Fluid Report (OD/OS)", device, scan pattern ("8.8 mm × 7.3 mm, 31 B-scans, distance 245 µm"), study date, model id and version, and the compute device.
2. **Volume table:**
   - Rows IRF / SRF / PED, each with a colour chip.
   - Columns ETDRS 1 mm, ETDRS 6 mm and Total scan, all in nL, with tooltips that spell out each compartment.
3. **Three en-face panels (IRF, SRF, PED):**
   - Each panel shows the height-map PNG plus a colour-scale legend (0–250 µm).
   - An SVG overlay draws the ETDRS 1/3/6 mm circles and quadrant lines, plus a line marking the B-scan currently selected in the viewer.
   - Clicking a panel moves the ETDRS center: `POST …/etdrs`, after which the table updates.
   - A "reset to scan center" button undoes this.
4. **B-scan viewer:**
   - Slider or arrow keys go through B-scans 1…N; a mini-strip highlights B-scans that contain fluid.
   - Side by side: "without segmentation" and "with segmentation" (the overlay PNG stacked on top), plus a toggle for a single large view.
   - Per-B-scan area readout.
5. **Footer:** warnings from `result.warnings` and the "Research use only" disclaimer, plus downloads (`labels.npz`, `result.json`).

---

## 8. Testing and acceptance

| Test | Pass criterion |
|---|---|
| **Golden regression** (`test_golden_retouch.py`): TEST015 `.mhd` via the CLI and the service pipeline, notebook padding and no harmonization | IRF 0.7169, SRF 0.0043, PED 1.6877 mm³, each within **±2 % or ±0.005 mm³** (CPU fp32 vs Colab GPU fp16). Run on CPU and on the T4 |
| Canvas equivalence | For W_res ≤ 576 the dynamic canvas is byte-identical to the notebook's `to_canvas` |
| DICOM ingest | Sample files → (31, 496, 768); spacing (0.011484, 0.003872); positions 0…7.34 mm; laterality OS |
| Spacing order | Swapping rows and cols in a synthetic DICOM gives the correct `spacing_lateral` (guards against the DICOM [row, col] trap) |
| Quantify | Synthetic cylinder → analytical nL within 1 %; ETDRS circle membership correct at the boundaries |
| Rejection | Non-OPT DICOM, non-Heidelberg, missing spacing and oversize files each give the right 4xx and error code |
| Auth | No token → 401; user B cannot read user A's job → 404 |
| E2E (manual) | All 4 sample DICOMs upload through the UI on the VM; the report renders; GPU time < 10 s per job end-to-end |
| CPU fallback | Same results (±2 %) with `CUDA_VISIBLE_DEVICES=""` |
| Visual QA | A clinician reviews overlays for the 4 sample DICOMs and signs off on the Phase 0 harmonization choice |

---

## 9. Phased work plan

### Phase 0: De-risk the model on real inputs ✅ done 2026-11-17
- [x] `inference-service/` skeleton: `core/volume.py`, `core/ingest/` (DICOM OPT and `.mhd`), `core/manifest.py`, `core/adapters/refattn_unet_v1.py`, `core/quantify.py`, `core/registry.py`, `cli.py`.
- [x] Local venv (Python 3.11, TF 2.21.0 / Keras 3.13.2). The model loads on CPU **unchanged**: its layers were saved with float32 policies, so no dtype handling is needed. CPU runs at ~1.3 s per B-scan (31-B-scan DICOM ≈ 50 s end to end).
- [x] **Golden test on TEST015** passes. On the model canvas, IRF/SRF/PED = 0.71690 / 0.00435 / 1.68770 mm³, identical to the notebook. On the native grid (what we report), the deviation is −0.11 % / −0.5 % / −0.02 %. Locked in as `tests/test_golden_retouch.py`.
- [x] DICOM ingest for the 4 samples, plus synthetic-DICOM tests for spacing order, frame order, fallbacks and the rejection codes (24 tests in total).
- [x] **Experiments** (`experiments/phase0_domain.py`). The RETOUCH Training set has ground truth, so the DICOM intensity domain was simulated on it and each option scored on the 121 validation B-scans, in addition to the contact sheets on the 4 real DICOMs:
  - The as-trained preprocessing on the DICOM domain scores 0.791 (upper bound 0.833).
  - **Chosen:** `zero_border` padding with histogram matching (dithered) to the RETOUCH reference, scoring **0.829**. Gamma 0.5 scored worse (0.788).
  - The dynamic canvas (800 px for the samples) processes the full 8.8 mm width; the fixed 576 px canvas would have cropped 2.4 mm.
  - Full table and decisions: `inference-service/models/oct-fluid-spectralis/1.0.0/model_card.md`.
- [x] Settings recorded in `model.yaml` (per source format: `dicom-opt` vs `mhd`). `intensity_reference.npy` added to the package; `model_card.md` written.
- [ ] **Open:** clinician review of the contact sheets (`inference-service/experiments/out/sheet_*.png`), especially HARI08S. There, the model labels scattered IRF at the base of a large dome-shaped elevation rather than segmenting it as PED.
- [x] The reference folder was retired: the model package, training provenance, report reference image and sample DICOMs now live in `inference-service/` (see §1.1).

#### Phase 0 results in short

**Preprocessing options on simulated DICOM input** (121 RETOUCH validation B-scans; score = Dice − false-alarm share, higher is better):

| Input / preprocessing | Score | Dice IRF / SRF / PED |
|---|---|---|
| RETOUCH original, as trained (upper bound) | 0.833 | 0.747 / 0.933 / 0.856 |
| DICOM-like, as trained | 0.791 | 0.706 / 0.927 / 0.836 |
| DICOM-like, zero-border padding | 0.802 | 0.720 / 0.931 / 0.837 |
| DICOM-like, gamma 0.5 | 0.788 | 0.733 / 0.935 / 0.797 |
| DICOM-like, histogram match | 0.824 | 0.719 / 0.927 / 0.857 |
| **DICOM-like, zero-border + histogram match + dither (chosen)** | **0.829** | **0.739 / 0.930 / 0.854** |

**Real sample DICOMs with the chosen setting** (whole-scan volumes, nL):

| File | IRF | SRF | PED |
|---|---|---|---|
| ARUNK01J_oct_0 | 1075.1 | 9.8 | 32.7 |
| ARUNK02J_oct_0 | 1103.6 | 159.4 | 102.8 |
| ARUNK02J_oct_1 | 938.6 | 63.8 | 98.6 |
| HARI08S_oct_1 ⚠ | 342.7 | 595.2 | 645.2 |

**Takeaways:**
- The pipeline reproduces the notebook exactly on TEST015, and the same weights run on CPU and GPU.
- The chosen DICOM preprocessing recovers ~90 % of the simulated domain gap. Without it, IRF on the real DICOMs comes out 7–25 % higher, with cysts merging and stray SRF/PED at the edges.
- ⚠ HARI08S needs clinician review before its numbers are trusted.
- Accuracy on real DICOMs is still unmeasured; ~10–20 annotated DICOM B-scans would settle it.

**Exit criteria met:** the golden test passes, the DICOM preprocessing configuration is chosen with quantitative evidence, and the model package is finalised (pending clinician sign-off).

### Phase 1: inference-service ✅ done 2026-11-18
- [x] `OctVolume`, registry (manifest validation, sha256, device selection, warm-up) and adapter base class.
  - `core/registry.py`: `load_manifests()` (manifest-only, no TensorFlow, used by the API) and `load_adapters()` (weights + sha256 + device + warm-up, used by the worker) for every `ENABLED_MODELS` entry.
  - `model.yaml` gained a `report:` section (disclaimer, warnings per source format), so report text ships with the model package.
- [x] Quantification (total and ETDRS 1/3/6, en-face interpolation) and rendering (B-scan, overlay, en-face PNGs).
  - `core/render.py`: one display window per volume; RGBA overlays (alpha 0.55); en-face PNGs in the class colour with opacity = height (0 µm transparent, 250 µm opaque), row 0 = first B-scan.
  - `core/pipeline.py`: ingest → adapter → quantify → render → `result.json` + `labels.npz` (labels + geometry). The CLI's `--out` runs the same pipeline.
- [x] DB model, jobs API, worker loop (SKIP LOCKED, heartbeat, requeue, TTL purge) and JWT validation.
  - Uploads are validated from the DICOM header only (`inspect_dicom_opt`, no pixel decode) before queueing; the API never imports TensorFlow (tested).
  - Errors are `{"detail": "<user-safe message>", "code": "<stable code>"}`.
  - Connected-app (`oauth_access`) tokens get 403; other users' jobs get 404; admins can read any job and list with `?all=true`.
  - `DELETE` on a running job marks it `cancelled`; the worker stops at its next progress update and removes the row and files.
  - Worker: `inference_workers` table for liveness (`/inference/health`); jobs it left running are requeued on restart; stale jobs are requeued, then failed (`worker_lost`) after `MAX_ATTEMPTS`; finished jobs are purged after `RESULT_TTL_DAYS`; a job re-claimed by another worker is never touched.
  - `POST …/etdrs` persists the chosen centre in `result_json`, so the report reopens with it; `{"center_mm": null}` resets.
  - Extra endpoint: `GET /inference/jobs/{id}/result.json` (download).
- [x] Dockerfile, `.env.example`, compose entries, `docker-compose.gpu.yml`, `.dockerignore`.
  - For Phase 1 testing `inference-api` publishes port 8002 on the host. Remove that once the gateway proxies `/inference/*` (Phase 2).
- [x] Tests from §8 (except E2E): `test_jobs_api.py` (auth, validation codes, size limit, ownership, no-TF import), `test_worker.py` (full lifecycle with a fake adapter, ETDRS re-centring, failure, cancel, requeue, TTL, take-over), `test_render.py`, plus extra quantify and ingest cases.

**Exit criteria:** with `docker compose up`, a `curl` upload of a sample DICOM produces a succeeded job with a full result on CPU locally.

#### Phase 1 results ✅ done 2026-11-18
- **Exit criteria met.** `docker compose up -d inference-db inference-api inference-worker`, then a `curl` upload of `ARUNK02J_oct_0.dcm`: the job succeeded in 61 s wall time (52 s in the worker, 50.6 s of it inference) on CPU. Volumes IRF / SRF / PED = 1103.6 / 159.4 / 102.8 nL, identical to Phase 0.
- All result endpoints, ETDRS re-centring, input deletion after processing, and `DELETE` were checked against the running stack.
- Tests: 65 passing (`pytest`), including the TEST015 golden regression.
- The image is **10.8 GB** uncompressed (CUDA/cuDNN wheels), above the 5–6 GB estimate in §6. It is still a single image for both containers; a slim API image (no TensorFlow) remains a "Later" item.
- Run locally: `cp inference-service/.env.example inference-service/.env` (set `JWT_SECRET` to auth-service's), then `docker compose up -d --build inference-db inference-api inference-worker`; `GET localhost:8002/inference/health`. Stop with `docker compose stop inference-api inference-worker inference-db`.
- The real model was also run through the full pipeline via `cli.py run … --out`. The renders were checked visually: overlays sit on the cysts, and the en-face maps show the central IRF cluster.

**Things to know going into Phase 2:**
- **Host port 8002 is temporary.** `inference-api` publishes 8002 so it can be tested with `curl`; remove the `ports:` entry once the gateway proxies `/inference/*`.
- **Image size.** A single 10.8 GB image serves both containers; most of that is the CUDA wheels. The API doesn't need TensorFlow, so a slim API image would save space (see "Later").
- **Beyond the original plan:**
  - The ETDRS centre is saved, so the report reopens with it; `null` resets it.
  - Admins can list every job with `?all=true`.
  - Connected-app tokens (e.g. Biomni) get 403.
  - There is an extra `result.json` download endpoint.
  - Errors share one `{detail, code}` shape (§5.1). The UI should show `detail` and can branch on `code`.
- **Local `.env`.** `inference-service/.env` is gitignored and must use the same `JWT_SECRET` as auth-service. `.env.example` is tracked through a `.gitignore` exception.
- **En-face PNG encoding.** Each map is drawn in its class colour, with opacity = height: 0 µm is transparent, and opacity runs from 0.25 just above 0 µm to 1 at ≥ 250 µm. Row 0 is the first B-scan in acquisition order. The UI draws the legend and the ETDRS grid on top.
- **Still open from Phase 0:** clinician review of the contact sheets, especially HARI08S.

### Phase 2: Gateway, nginx and UI ✅ done 2026-11-18
- [x] Gateway proxy routes (streamed upload, streamed images) and nginx changes.
  - `api-gateway/main.py`: explicit routes for every §5.1 path, proxied with `httpx` (async, streaming both ways), so uploads and PNGs are never buffered in gateway memory. `httpx==0.28.1` added to the gateway requirements.
  - Path params are validated before forwarding (job id = UUID, `z` = int, class name `[A-Za-z0-9_-]`). A missing token is 401, not 422. `/inference/health` needs no auth.
  - `INFERENCE_SERVICE_URL` defaults to `http://inference-api:8002`, and `INFERENCE_UPLOAD_TIMEOUT` to 120 s. If the service is down the gateway returns `502 inference_unavailable`; if it times out, `504 inference_timeout`.
  - `ui/nginx.conf`: `location ^~ /inference/` with `client_max_body_size 300m`, `proxy_request_buffering off`, HTTP/1.1 and 300 s timeouts. `vite.config.js` also proxies `/inference` for `npm run dev`.
- [x] Remove the temporary host port 8002 from `inference-api` in `docker-compose.yml` (the gateway now `depends_on` it).
- [x] Sidebar ("OCT Fluid Analysis", `ScanEye`), routes `/oct-analysis` and `/oct-analysis/:jobId`, and `OctAnalysisPage`.
  - Drag-and-drop upload with a progress bar: XHR, since `fetch` has no upload progress.
  - The model picker appears only when there is more than one model. Errors show the service's `detail` inline.
  - The jobs table shows eye, B-scans, status with stage and %, and total nL per class. It polls every 2 s while a job is active; clicking a finished row opens its report; a delete button cancels or deletes. Admins get a "Show all users" toggle.
- [x] `OctReportPage`: header, volume table, three en-face panels, B-scan viewer, downloads, warnings and disclaimer.
  - The header shows eye, file, device, scan pattern, study date, and model with its compute device.
  - The volume table has ETDRS 1/3/6 mm and Total scan columns, marked "partial" when the scan doesn't cover a circle.
  - The en-face panels are SVG in scan millimetres. The PNG is drawn under the ETDRS circles and diagonals, with a line marking the current B-scan and a 0–250 µm legend. Clicking a map moves the ETDRS centre; "Reset to scan centre" undoes it.
  - B-scan viewer:
    - The slider, arrow keys and prev/next buttons step through B-scans; a strip of bars shows fluid area per B-scan.
    - Views are side by side or one large view with an overlay toggle, plus a per-class area (mm²) readout.
    - It opens on the B-scan with the most fluid and prefetches neighbouring B-scans.
  - Images are fetched with the bearer token and shown as blob URLs (`components/oct/useOctHelpers.js`).
  - New files: `ui/src/lib/inference.js`, `ui/src/components/oct/*`, `ui/src/pages/Oct{Analysis,Report}Page.jsx`.

**Exit criteria:** the full flow works in the browser locally on CPU.

#### Phase 2 results ✅ done 2026-11-18
- **Exit criteria met.** With the full stack running locally (`docker compose up -d --build`), a scripted headless Chrome session against `http://localhost:5000` ran the whole flow without console errors.
  - It signed in with a test JWT and opened OCT Fluid Analysis.
  - It uploaded `HARI08S_oct_1.dcm` through the file input and watched the job go from queued to running to succeeded on CPU.
  - It then opened the report, moved the ETDRS centre by clicking an en-face map (the IRF 1 mm value changed from 0.00 to 10.6 nL), reset it, stepped B-scans with the arrow keys and switched to the single view.
- Through nginx → gateway → inference-api:
  - Volumes are identical to Phase 1.
  - No token gives 401, and a bad job id gives 422.
  - A non-DICOM file gives `422 invalid_dicom`; a 310 MB file gives 413 from nginx.
  - Gateway memory stayed flat (~52 MB) during a 200 MB upload, so uploads are streamed.
  - Port 8002 is no longer reachable from the host.
- Lint (`oxlint`) is clean and `npm run build` passes. The existing >500 kB bundle warning is unchanged.
- **Notes for Phase 3:**
  - En-face orientation is shown literally: top = B-scan 1, left = first A-scan. It has not been mapped to superior/inferior or nasal/temporal; that needs the scan's acquisition orientation and is worth confirming with the clinician during the HARI08S review.
  - The gateway has no test suite; its inference routes were checked against the running stack only.

### Phase 3: Deploy to the GCP VM with the T4 (about 0.5–1 day)
- [ ] Driver and nvidia-container-toolkit setup (§6.1), copy the model package, bring up with the GPU override.
- [ ] Run the golden test inside the worker container on the GPU; E2E with the 4 samples; check latency and memory.
- [ ] Update `coda-dashboard/README.md`: new services, GPU override, how to add a model.

### Later (not now)
- Per-patient and longitudinal progression (needs a patient/study identity design and a PHI decision).
- PDF report export, DICOM-SEG and NIfTI export.
- Automatic fovea detection (a retinal layer model, added as a second package through the same registry).
- Additional vendor models (Cirrus/Topcon). Raw `.E2E` ingest if needed.
- Slim API image; Redis queue or Triton if load grows; model packages pulled from GCS at startup.

---

## 10. How to add or replace a model later (the runbook we're designing for)

1. Train, then export `weights` and write `model.yaml` (new `version`) and `model_card.md`.
2. Put the package at `inference-service/models/<id>/<version>/`, or upload it to GCS and run `fetch_models.sh`.
3. If its preprocessing or output differs, add `core/adapters/<new_adapter>.py` implementing `ModelAdapter`. Otherwise reuse the existing adapter by name.
4. Add a golden test case for it.
5. Add it to `ENABLED_MODELS` and restart `inference-worker` and `inference-api`. The UI picks it up from `/inference/models`.
6. Old jobs keep their `model_id@version`; the old package can stay mounted for reproducibility.

---

## 11. Open questions (non-blocking; defaults in brackets)

1. **Ground truth on DICOM-domain data.**
   - Could someone annotate IRF, SRF and PED on ~10–20 B-scans from 2 of the sample DICOMs?
   - Without that, Phase 0 can only be judged visually.
   - If DICOM performance turns out poor, the real fix is fine-tuning on a few annotated DICOM volumes, which is a model change the registry already supports.
   - [Default: visual QA only.]
2. **Origin of the DICOMs.**
   - `ImageType = DERIVED\SECONDARY` with values 0–100 suggests they came from a converter (e.g. from `.E2E`), not native HEYEX DICOM export.
   - Will production data always come through the same path? If some will be native HEYEX DICOMs, the harmonization may need to differ per source.
   - [Default: treat all inputs like these samples.]
3. **Result retention.** [Default: delete the uploaded DICOM immediately; keep derived masks and images for 30 days; users can delete sooner.]
4. **Job visibility.** [Default: users see only their own jobs; admins see all.]
