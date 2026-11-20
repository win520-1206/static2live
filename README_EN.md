# Static2Live

[简体中文](README.md) | [English](README_EN.md)

**Bring Still Images to Life.**

Turn still images into interactive live wallpapers with local image analysis and real-time rendering.

![Portrait wallpaper preview with subtle hair, clothing, and warm particles](assets/demo/portrait-motion.webp)

Web runtime capture · Hair tips sway, fabric moves gently, and warm particles drift while the face stays stable.

`Python 3.10+` · `WebGL` · `Depth Estimation` · [MIT code license](LICENSE)

[Quick Start](#quick-start) · [Demos](#demos) · [Feature status](#status-and-limitations) · [Documentation](#documentation)

## What is Static2Live?

Static2Live plans motion using depth, semantic regions, or hand-drawn masks. WebGL and Canvas render effects in real time in response to pointer input and time. Outputs run offline in a browser, with native Wallpaper Engine export available when local prerequisites are installed. Configure effects through the CLI, YAML, or the included skill.

## Features

- **Depth parallax**. Different parts of the image respond to the pointer according to their depth.
- **Local motion effects**. Use region masks to animate hair tips, fabric, foliage, water, and mist, and add ambient particles.
- **Local AI analysis**. Smart mode uses local models to identify people, sky, and water. Lite supports manual regions or rule-based suggestions.
- **Native Wallpaper Engine export**. Build scenes using a local Wallpaper Engine installation, scene templates, and compiler.

## Quick Start

With Python 3.10+, open the repository root and activate your Python environment. Replace `photo.jpg` with your image path. This Lite example disables parallax and needs no model.

```bash
pip install .
static2live photo.jpg --mode lite --no-parallax --effect dust
```

After the first run, open `output/photo/v001/index.html` to view the warm particles. The same directory contains the check results in `validation.json`.

### Run the public sample from a fresh checkout

Windows PowerShell, Python 3.10+.

```powershell
git clone https://github.com/win520-1206/static2live.git
cd static2live
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m static2live --help
.\.venv\Scripts\python.exe -m static2live assets/demo/landscape-source.png --mode lite --no-parallax --effect dust
```

The first output is `output/landscape-source/v001/`. Double-click its `index.html` to view it. Checks are stored in `validation.json`. Subsequent generation creates `v002/` and further independent versions.

For slow PyPI connections, append `--index-url https://pypi.tuna.tsinghua.edu.cn/simple` to this installation command to use the Tsinghua mirror.

On Linux/macOS, substitute `.venv/bin/python`. Actual host acceptance currently comes from Windows. The native Adapter targets a local Wallpaper Engine installation.

## Demos

### Lakeside · Foliage, ripples, and mist

![Foreground foliage swaying, water rippling, and mist drifting in the distance](assets/demo/depth-parallax.webp)

Foliage, water, and mist animate in separate regions, with protected rocks and a boathouse. The capture holds the pointer at the center. The interactive project supports subtle mouse parallax. Reproduce it with Lite, a model-estimated depth map, and explicit region masks. [Static source](assets/demo/landscape-source.png)

### Winter street · Ambient particles

![Animated snowfall on a winter street](assets/demo/particle-effects.webp)

The photorealistic street is an AI-generated still. Lite and Web Canvas render the airborne snowflakes in real time. [Static source](assets/demo/particle-source.png)

The featured portrait uses a photograph authorized for public project display. Human-parsing regions were corrected by hand before importing them into Lite. The soft-edged Web dust was tuned using the previously accepted native effect as a reference. [Portrait display source](assets/demo/portrait-source.png)

All three clips were captured from the Web runtime at 960×540 and about 12 FPS. The lake runs for 8 seconds, and the portrait and snow clips run for 5 seconds each. The demo directory includes GIF copies, asset provenance, and reproduction steps. [Demo assets and reproduction](assets/demo/README.md)

## Models and advanced usage

### Prepare a local depth model

Reuse the environment above, install the optional PyTorch/Transformers dependencies, and explicitly prepare the depth model.

```powershell
.\.venv\Scripts\python.exe -m pip install ".[depth]"
.\.venv\Scripts\python.exe -m static2live models prepare --kind depth --model-cache models
.\.venv\Scripts\python.exe -m static2live assets/demo/landscape-source.png --mode lite --model-cache models --output output/depth
```

The model cache is `models/`. Output is `output/depth/landscape-source/v001/`. CPU is the default, with explicit `--device cuda` support. Generation reads the prepared local cache.

A supplied map can be passed through `--depth-map depth.png`. It must match the EXIF-oriented input dimensions, use an 8-bit single channel, and encode nearer regions as white. Slow downloads can explicitly use a domestic mirror while retaining official revision/hash checks. See [model preparation](references/workflow.md#下载慢时换国内镜像).

For failures, inspect the CLI error and `validation.json`, then consult the [workflow](references/workflow.md) or [native troubleshooting](references/native-qa.md).

### Smart, manual regions, and native export

Install the `.[smart]` dependencies and explicitly prepare the segmentation model after reviewing and accepting its license. The Smart example below uses parallax and also needs the depth model prepared. Prepare the separate human-parsing model if you use `--human-parsing`.

```powershell
pip install ".[smart]"
static2live models prepare --kind segmentation --model-cache models --accept-model-license
static2live models prepare --kind human-parsing --model-cache models --accept-model-license
```

The examples below use `static2live` from an activated environment. You can substitute `.\.venv\Scripts\python.exe -m static2live`.

```powershell
# Analyze and recommend only; disable parallax to skip the depth model
static2live analyze --input photo.jpg --no-parallax

# Create an offline editor, save regions.json, then regenerate
static2live annotate --input photo.jpg --output annotations
static2live photo.jpg --mode lite --no-parallax --regions regions.json --effect dust

# Predict people, sky, and water after preparing local models
static2live photo.jpg --mode smart --preset warm_portrait --model-cache models

# Local human parsing and optional native scene export
static2live photo.jpg --mode smart --human-parsing --target wallpaper-engine --model-cache models

# Landscape framing with a top-priority crop
static2live photo.jpg --crop-aspect 16:9 --crop-anchor top
```

See the [full workflow](references/workflow.md) and [human parsing guide](docs/V0.4_IMPLEMENTATION.md).

Precedence is CLI > user YAML > selected Preset > automatic suggestions > defaults. `--strength` is a fraction of the canvas short edge, capped at `0.01`. Hair and clothing amplitudes use canvas pixels. The workflow documents detailed units. Explicitly disabled effects and zero strengths are preserved.

## Architecture

```mermaid
flowchart TD
    A[Static image] --> B[Orientation, size and crop alignment]
    B --> C[Optional local depth estimation]
    B --> D[Smart segmentation and human parsing]
    B --> E[Lite manual or rule-based regions]
    C --> F[Analysis and Motion Planner]
    D --> F
    E --> F
    F --> G[Motion Manifest and assets]
    G --> H[WebGL / Canvas]
    G --> I[Optional Wallpaper Engine Adapter]
    H --> J[Layered Validator and acceptance report]
    I --> J
```

`analyzer.py` aligns pixels and region provenance, `planning.py` recommends motion, and `motion.py` defines canvas and parameters. Renderers consume generated assets, the Adapter handles host dependencies, and the Validator checks configuration, hashes, and runtime evidence. See [automatic planning](docs/V1.0_IMPLEMENTATION.md).

## Output

```text
output/landscape-source/v001/
├── index.html
├── style.css
├── runtime.js
├── effects.js
├── assets/
├── config.yaml
├── analysis.json
├── motion.json
├── manifest.json
└── validation.json
```

`index.html` is the offline Web entry point. `assets/` stores the image and applicable depth/maps. `analysis.json` records provenance and recommendations, `motion.json` describes animation, `manifest.json` records versions and hashes, and `validation.json` stores check results.

Native exports add `native-plan.json` and `wallpaper-engine/project.json`. Missing engine/template/compiler prerequisites retain Web output with `actual:web` and a warning. Actual compilation failures raise errors. Consult `native-plan.json` for mapped native particles/properties and unsupported features.

## Validation

| Layer | Checks | Evidence |
| --- | --- | --- |
| Structural | Assets, dimensions, parameters, references, and hashes | Automated structural checks |
| Browser Runtime | WebGL startup, pixel behavior, edges, zero strength, and fallback | Actual Chromium execution |
| Visual Acceptance | Continuity, natural motion, and local artifacts | Human observation of a specific version |
| Native Runtime | Host loading, interaction, properties, and capabilities | Actual Wallpaper Engine observation |

States are `passed / warning / failed / not_tested`. Generation, browser behavior, and human observation are tracked separately. Every new Manifest retains its own acceptance state. Screenshot evidence is independently versioned.

The installed 1.0.1 regression on 2026-11-17 passed **225 tests**, including real synthetic browser tests and foliage/water composition and soft-dust cases. The historical 1.0 source package also passed 28 core/skill workflow tests. Current fixes are described in the [1.0.1 notes](docs/V1.0.1.md). Real-photo, independent native audio, and physical dual-display evidence is scoped in the [1.0 notes](docs/V1.0_RELEASE.md) and [requirements audit](docs/V1_REQUIREMENT_AUDIT.md). Private source photos and raw local records remain on the maintainer's machine.

## Status and limitations

| Feature | What it provides | 1.0.1 status |
| --- | --- | --- |
| Depth parallax | Pointer response through local UV displacement and bounded sampling | Implemented, real-photo and browser validation |
| Lite | Manual regions, rule-based candidates, optional supplied depth | Implemented, fully model-free with parallax disabled |
| Smart | Local person/sky/water prediction and optional human parsing | Implemented, predictions require inspection and possible correction |
| Hair and clothing | Anchored roots, local weights, and protected regions | Implemented, corresponding photo feedback recorded |
| Particles and regional effects | Rain/snow/dust/fog, Glow, Cloud Drift, independent foliage sway | Implemented on Web, native scope documented below |
| Offline region editor | Paint, erase, protection, motion sources, undo, and zoom | Implemented, regenerate after editing |
| Automatic planning | Evidence-based Preset and restrained motion recommendations | Implemented, explicit user configuration takes precedence |
| Advanced runtime | Optional audio response, performance profiles, virtual viewport, local shaders | Implemented, acceptance and host support tracked separately |
| Native Adapter | Complete scene dependencies using local licensed templates and compiler | Implemented, requires a Wallpaper Engine environment |

- Relative depth drives bounded sampling of the input. Hidden background remains occluded. Human parsing predicts coarse classes, and loose hair or edges may need manual correction.
- Automatic recommendations are conservative. The accepted Smart sample was reported natural, continuous, and face-stable. Independent visibility of default clothing motion still needs per-image confirmation.
- Native mapping covers parallax, human local motion, full-canvas rain/snow/dust/fog, properties, and optional audio/shaders. Web features such as local particles, Glow, and Cloud Drift are handled according to native unsupported records. Appearance can differ between targets.
- Web supports performance profiles and normalized virtual viewports. Native performance and cropping are host-managed. Precise native hardware FPS, VRAM, and multi-instance clock synchronization still need measurement or acceptance.
- Future scope includes automatic tree recognition, independent light rays, fine hair Alpha Matting, background completion, facial expressions, and video export.
- Skill evidence includes actual primary-Agent usage and runnable CLI recipes. Independent Agent behavioral evaluation remains pending.

## Development and tests

Install development dependencies in the environment above.

```powershell
.\.venv\Scripts\python.exe -m pip install ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q

# Full browser tests require explicit Chromium installation and opt-in
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD/.browsers"
.\.venv\Scripts\python.exe -m playwright install chromium
$env:STATIC2LIVE_BROWSER_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

Browser cases are skipped without opt-in. Editable installation is available through `pip install -e ".[dev]"`. A regular install can avoid editable-install encoding issues on Windows paths containing Chinese characters.

Report reproduction steps, version, configuration, and target in [Issues](https://github.com/win520-1206/static2live/issues), and submit changes through [Pull requests](https://github.com/win520-1206/static2live/pulls). Preserve original inputs, old output, and model-license provenance. Use synthetic fixtures and check for private files and credentials before committing.

## Roadmap

- [x] 1.0 analysis, planning, dual-target output, and validation pipeline.
- [x] Manual region editing, real Smart models, and accepted portrait micro-motion.
- [ ] Expand the variety of real photos and human-edge cases.
- [ ] Measure native hardware performance and test continuous multi-display composition.
- [ ] Independently evaluate skill behavior with another Agent.
- [ ] Improve the native support matrix, CI, and release workflow.

## Privacy, licenses, and credits

Generation and playback are local. Initial dependency installation and explicit model preparation need network access. Original images are preserved and new outputs use independent version directories. Users are responsible for securing public-display rights to their images.

| Resource | License and source |
| --- | --- |
| Static2Live code | [MIT](LICENSE) |
| README portrait and derived animations | Authorized by the user for project display; further reuse requires confirmation from the rights holder, see [asset notes](assets/demo/README.md) |
| README landscape/street images and derived animations | AI-generated sources with actual runtime animation; image rights are separate from the code license, see [sources and prompts](assets/demo/prompts.md) |
| Depth Anything V2 Small HF | Apache-2.0, follow the [official model card](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf) and actual cache record |
| SegFormer B0 ADE | NVIDIA SegFormer license, non-commercial research/evaluation, see the [official model card](https://huggingface.co/nvidia/segformer-b0-finetuned-ade-512-512) |
| FASHN Human Parser | NVIDIA SegFormer license, non-commercial research/evaluation, see the [official model card](https://huggingface.co/fashn-ai/fashn-human-parser) |
| Wallpaper Engine templates/assets | Local use under their source license; excluded from software distribution |

Thanks to Depth Anything, SegFormer, FASHN, Pillow, NumPy, PyTorch, Transformers, and Wallpaper Engine for their models or tools. See [model and asset licenses](docs/MODEL_LICENSE.md) for usage and redistribution details.

## Documentation

| Document | Contents |
| --- | --- |
| [1.0 delivery notes](docs/V1.0_RELEASE.md) | Current capabilities, acceptance basis, and limitations |
| [1.0.1 fixes](docs/V1.0.1.md) | Independent foliage sway, soft warm dust, and compatibility |
| [Requirements audit](docs/V1_REQUIREMENT_AUDIT.md) | Original specification mapping and historical scope |
| [Skill entry point](SKILL.md) | Natural-language request to CLI orchestration |
| [Full workflow](references/workflow.md) | Modes, models, configuration, framing, and units |
| [Native troubleshooting and QA](references/native-qa.md) | Loading, black screens, particles, and properties |
| [Development capabilities](references/development.md) | Parsing, protection, and capability-level evidence |
| [Motion primitives](docs/MOTION_PRIMITIVES.md) | Regional shaders and constraints |
| [Human parsing](docs/V0.4_IMPLEMENTATION.md) | Hair, clothing, and protection implementation history |
| [Mask editor](docs/V0.5_IMPLEMENTATION.md) | Painting, saving, and regeneration |
| [Advanced runtime](docs/V0.6_IMPLEMENTATION.md) | Audio, performance, displays, and shaders |
| [Automatic analysis and planning](docs/V1.0_IMPLEMENTATION.md) | Analyzer and Motion Planner |
