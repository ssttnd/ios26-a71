# Lessons from the iOS 16 A71 port and other iOS 26 ports

What earlier work found that applies (or may apply) to this iOS 26 port. Each item says where it came from and
whether it is done here. Update the status column as items are ported or ruled out.

## From the iOS 16 A71 port (`../ios-a71`, its NOTES.md and xnu/patches)

| Topic | iOS 16 finding | Status here |
|---|---|---|
| Sampler LOD range | `effefe8`: A6XX_TEX_SAMP_1_MIN/MAX_LOD are unsigned 4.8 fixed point; 16.0 wrapped to 0 and every LOD clamped to level 0 (pixelated blur). | Same bug (Metal default lodMaxClamp 65504 -> 0). Clamp to [0,15] in `6fe189c` (Metal patch generator). |
| Blur pyramid | `b622d82`: render level N from a one-level view of level N-1 of the same texture. | Covered differently: draws that read and write one texture sample a copy (hazard path), mip views exist. |
| Progressive blur | bundle 929ce9e: rendering into mip level 1 (level views as attachments). | Done (`ios26-mip-views.patch`, `ios26-blur-attachments.patch`). |
| Frame pacing | 0226 swap wait until GPU done; 0229 (`2535fbc`) `sweetswapwait=3`: only one swap in flight. Cause: CoreAnimation SwapWait serialised encode, GPU and copy. 36-41 fps with `sweetfb_hz=60`. | Not ported (our `sweet_fb` differs). Boot images used `sweetfb_hz=30` (leftover diagnostic, ~10 swaps/s seen). First step: `--fb-hz 60`. |
| 0217 present at swap, 0218 BO free without full drain | Lower present latency, BO free 0.85 ms (was 12-21). | 0218 ported (2102 set). 0217 not checked. |
| GPU for apps | 0221/0225 Metal for every client but SpringBoard, 0224 Maps, 0227 short list. | We allow backboardd, AegirPoster, Mercury (2119), PosterBoard (2124) only. Apps draw Liquid Glass on the CPU path. |
| Maps | pipelineLibrary selector `7a094ce`, buffer address space + pack 2x16 `c82725f`, heap proxy `2966d07`, single-sample storage for multisample descriptors `761b43d`. | Not checked against the iOS 26 driver. |
| Mail logos | 0228 keep 4-byte client rows. | Not checked. |
| Settings pages | CoreImage `internalContextWithEAGLContext:options:` swizzled to nil (SweetNativeDrawLog.inc). | iOS 16 GL path; probably not needed on iOS 26 (no GLES). |
| Notes black screen | accountsd `tetheredSyncSourceTypeForDataclass:` -> lockdownd tethered_sync value. | Not checked on iOS 26. |
| GMEM vs sysmem | GMEM was slower (7.1 vs 6.5 ms per pass); UBWC shadows of linear targets gave nothing. | Same driver family: keep sysmem. |
| Measuring fps | `tools/a71-smooth.py` (kernel FB windows), `MESA_GPU_TRACES=print` in `/var/local/sweet-native-env` for per-pass GPU time; own pass timestamps were wrong. | Tools not copied yet. |

## From other iOS 26 ports (checked 2026-11-22)

- **Bergamota** (ry-diffusion, A630): MSAA textures need `nr_storage_samples` or freedreno drops resolves
  (done here `9252b8c`); AIR image stores must be typed from the stored value (done `2cba538`); a PosterBoard older
  than SpringBoard never shows the wallpaper again (done in A71Island); CoreAnimation set glass blur radius and gate
  to 0 every frame (cause not found there); mixed-size colour attachments in CA's blur passes.
- **IOS-26-Hot / IOS-26-Hot-raphael** (A640, Turnip): `docs/prior-art.md` lists UniXNU kernel 0242 GPU cache
  invalidate before every submit, 0244 drawables released 3 vsyncs after the flip, 0245 IOSurface zombie views,
  AdrenoMetal `51b7003` supportsTileShaders NO (QuartzCore non-tile path).
- **Viva** (nik300/viva-gpu, Redmi Note 11 Pro): SpringBoard display hooks for the Dynamic Island (basis of
  `userspace/island26/A71Island.m`).
- **marnov999/ios26-sweet**: same SoC/GPU (SM7150, A618), README only.
- **ios-pipa** (A650, GL-based bridge): blur works there; different stack.
- **hakios-arm64e-dada** (Xiaomi 15): Metal via metal2vulkan + Turnip.
