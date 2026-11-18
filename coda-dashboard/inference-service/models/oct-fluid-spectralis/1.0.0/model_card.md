# Model card — oct-fluid-spectralis 1.0.0

**Task:** per-B-scan segmentation of retinal fluid in OCT volumes: IRF (intraretinal fluid), SRF (subretinal fluid),
PED (pigment epithelial detachment). Volumes are derived by summing segmented area × B-scan spacing.

**Intended use:** research. **Not for clinical diagnosis.**

## Architecture and training
- Reference attention U-Net (2D, 9.44 M parameters, fully convolutional), softmax over {bg, IRF, SRF, PED}.
- Source notebook: `training/OCT_Fluid_Spectralis_RefAttUNet.ipynb` (TensorFlow 2.21.0, Keras 3.13.2, Colab GPU).
- Data: RETOUCH Training set, Heidelberg Spectralis only (24 volumes × 49 B-scans, 496 × 512, uint16 `.mhd`).
- Validation: 10 % of B-scans of every training volume (stratified fluid / no fluid), **not patient-held-out**.
- Loss: fluid Dice + focal (γ = 2). Augmentation: crop, flip, rotation/scale/shift, gamma 0.7–1.5, contrast,
  speckle, blur, black wedges. 35 epochs, best epoch 29.

## Preprocessing (must match training)
Resample each B-scan to 0.011174 mm (lateral) × 0.003872 mm (axial) → detect padding → percentile stretch
(0.5–99.5 %) to uint8 1..255 (padding = 0) → place on a 512 × 576 canvas (grown, never cropped, for wider scans)
→ per-B-scan z-score over non-padding pixels.

## Performance
| Data | IRF Dice | SRF Dice | PED Dice | Notes |
|---|---|---|---|---|
| Validation B-scans (RETOUCH) | 0.747 | 0.933 | 0.856 | best-epoch score 0.833 (Dice − false-alarm share, averaged) |
| RETOUCH Spectralis Test | — | — | — | no public reference; predicted volumes in `training/test_predicted_volumes.csv` |

## Limitations
- Trained and validated on RETOUCH Spectralis only. Other vendors are rejected by the service.
- Validation shares patients with training, so the Dice above is optimistic.
- DICOM exports differ in intensity encoding from RETOUCH `.mhd`; see "Input domain" below.
- Volumes use the scan centre as the default ETDRS centre (no fovea detection).

## Input domain (Phase 0 findings, 2026-11-17)
Reproduce with `inference-service/experiments/phase0_domain.py`.

**The domain gap.** The sample Spectralis DICOM exports (`ImageType DERIVED\SECONDARY`) store intensities as
0..100 integers (~38 % zeros, black vitreous). RETOUCH `.mhd` volumes are 16-bit with a grey, speckled background.

**How it was measured.** There is no ground truth on the DICOMs, so the DICOM domain was simulated on RETOUCH. A monotone
transfer curve (RETOUCH raw → DICOM raw, from pooled quantiles) was applied, then values were rounded to 0..100. The
simulated volumes match the real DICOMs: 38.4 % vs 37.7 % zeros, the same median (3) and the same 99th percentile (100).
Each option was then scored on the 121 held-out validation B-scans with the notebook's metric (Dice − false-alarm
share, averaged over classes):

| Input / preprocessing | score | Dice IRF | Dice SRF | Dice PED | FA IRF | FA SRF | FA PED |
|---|---|---|---|---|---|---|---|
| RETOUCH original, as trained (upper bound) | 0.833 | 0.747 | 0.933 | 0.856 | 0.004 | 0.003 | 0.031 |
| Simulated DICOM, as trained (edge padding, no harmonization) | 0.791 | 0.706 | 0.927 | 0.836 | 0.015 | 0.008 | 0.074 |
| Simulated DICOM, zero-border padding | 0.802 | 0.720 | 0.931 | 0.837 | 0.008 | 0.005 | 0.068 |
| Simulated DICOM, gamma 0.5 | 0.788 | 0.733 | 0.935 | 0.797 | 0.002 | 0.010 | 0.088 |
| Simulated DICOM, histogram match | 0.824 | 0.719 | 0.927 | 0.857 | 0.010 | 0.002 | 0.020 |
| Simulated DICOM, histogram match + dither | 0.822 | 0.721 | 0.927 | 0.856 | 0.010 | 0.002 | 0.027 |
| **Simulated DICOM, zero-border padding + histogram match + dither (chosen)** | **0.829** | **0.739** | **0.930** | **0.854** | **0.007** | **0.003** | **0.028** |

**Decision** (in `model.yaml`): for `dicom-opt` input, use `zero_border` padding and histogram matching (with dither) to
`intensity_reference.npy`. That is the uint8 histogram of the stretched RETOUCH training-split B-scans. `.mhd` input
keeps the as-trained preprocessing, which reproduces the notebook exactly (golden test on TEST015).

**On the real sample DICOMs:**
- Without harmonization, volumes are 7–25 % higher for IRF and larger still for SRF and PED.
- The overlays show IRF bleeding across the septa between cysts, plus spurious SRF/PED at the image edges.
- The harmonized options agree with each other within a few percent.
- HARI08S (large dome-shaped elevation) needs clinician review. The model labels scattered IRF at the base of the
  dome rather than segmenting it as PED, which may be a lesion type that RETOUCH does not represent well.

**Remaining risk.** The simulation captures intensity encoding, not differences in scanner, protocol or population. A
small annotated DICOM set (~10–20 B-scans) is still the only way to measure DICOM accuracy directly.
