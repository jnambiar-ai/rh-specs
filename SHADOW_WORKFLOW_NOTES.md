# Weave automated shadow workflow - notes

Working notes for automating cast-shadow generation (Weave) and placing the result back into the WIP PSDs.

## Pipeline

| # | Stage | Tool | Status |
|---|-------|------|--------|
| 1 | Prep WIP PSD as AI input | `RH_PrepWIPForShadow.jsx` (this repo) | Built, not yet run in Photoshop |
| 2 | Generate shadow | Weave `WeaveBatchShadowWorkflow_BlankTemplate` | In use |
| 3 | Extract shadow from AI output | `RH_ShadowExtractorV2.jsx` (not in this repo) | Exists |
| 4 | Place shadow into the WIP | Manual (see below) | To automate |
| 5 | Rename outputs to match inputs | - | Not built |

Superseded: `RH_addBleedremoveShadow_5056x3392` (V1, V2) by the prep script; `RH_ShadowExtractor` (V1) by V2.

## WIP files

- Layered PSDs. Canvas size and framing are **not fixed**: they vary per file, so the prep script measures each product.
- **"Main" group**: the product and its mask. Used to measure how the product sits in the canvas.
- **Shadow group**: the existing shadow. Turned off for prep.

## 1. Prep (`RH_PrepWIPForShadow.jsx`)

Hide Shadow group(s) -> measure product from Main (fallback: non-white bounds) -> 3:2 frame centered on the product with `PADDING` -> expand canvas if the frame runs past it -> flatten, RGB 8-bit -> 4000x2667 JPG.

- `PADDING = 0.37`: space on each side as a fraction of the product's longer side.
- Every crop is logged to `RH_ShadowPrep_log.csv` (`file,status,srcW,srcH,cropLeft,cropTop,cropW,cropH,outW,outH,hiddenGroups,boundsSource`). `cropLeft/Top` can be negative (frame extends past the WIP canvas). Needed to map the shadow back to the WIP.
- Padding check against five catalog images (2000x1334): wide tables fill 57.6% of the width, which is exactly 0.37. Compact pieces (side table, nightstand) are framed smaller in the catalog (36-37% width), so 0.37 frames them 7-29% larger. No single fit rule reproduces all five. Kept 0.37: the shadow goes back into the WIP using the logged crop, so the AI-input framing does not have to match catalog framing.

## 2. Weave template

- Image Iterator -> Depth Anything V2 -> Nano Banana Pro edit (`fal-ai/nano-banana-pro/edit`).
- Nano inputs: image_1 product, image_2 depth map, image_3 shadow-style reference (one fixed image for the whole batch) + prompt. Settings: 4K, aspect 3:2, PNG, random seed. Output: **5056x3392**.
- **Resize node** (aspect lock off). The width correction (Nano's frame is 1.4906:1, the prep frame is 1.4998:1) must live in **one** place only:
  - **Photoshop (recommended):** the 99% width step below. Resize node is then neutral: **5056 x 3371** (the prep frame's ratio, -21px height, width unchanged), or skip the node and keep 5056 x 3392 if the placement forces exact frame dimensions.
  - **Weave (alternative):** bake the 99% in with **5036 x 3392** (-20px width, height unchanged) and do no 99% in Photoshop; place by fitting to frame height.
  - Superseded: 5056 x 3388 (= 3980 x 2667 ratio, 99.5%). It only applied if the correction lived in Weave.
- Outputs carry no original filename (random IDs). Order is preserved: each result's `secondaryOrder` matches the iterator's `insertionOrder`. A rename step must map by order (the workflow JSON lists the ordered originals).
- Prompt: the `--no ...` list is Midjourney syntax and Gemini likely reads it as plain text; consider positive phrasing. The style reference is the same product as batch item 1, so item 1 is not a fair style test.

## 4. Placing the shadow into the WIP - manual steps today

1. Place the AI shadow output as a **Smart Object** at the same canvas size and dimensions as the WIP image.
2. Scale it to **99% on the width** (height unchanged).
3. Nudge the shadow layer **up 1px** (one arrow-key press).
4. Add a **Hue/Saturation layer, Saturation -100** ("desat 100%"), **clipped** to the shadow layer.
5. **Round table:** the canvas had to be expanded by about **200px on each side** to fit the shadow.

Notes for automating:

- The 99% width step corrects the same thing as a Resize-node width change (the model's frame is ~0.6% narrower than 3:2; theory says ~99.4%, the tuned value is 99%). Apply it once only, in Photoshop (see Resize node above). Because the prep frame is always the same 3:2 ratio, the correction is the same for every file, so it can be a constant. Verify on one file.
- These steps were done with the AI output fitted to the full WIP canvas. The prep script crops, pads and resizes, so placement has to use the CSV: the 4000x2667 prep frame covers WIP pixels `cropLeft, cropTop, cropW x cropH`. Stretch the AI image to that rectangle (cropW x cropH), then apply the 99% width about its center.
- Canvas expansion should come from where the shadow lands, not a fixed 200px.
- Unconfirmed: the unit of the 1px nudge (WIP pixels or prep-frame pixels).

## Open questions

1. Blend mode of the placed shadow layer (not mentioned above).
2. Is the placed file the extracted `_shadow.png` or the full AI output?
3. How Weave downloads are named (needed for the rename step).
