# Local models (image generation)

Everything the editor's image features use runs locally on the host; nothing is sent to a hosted API. The editor
container talks to one model server, `stable-diffusion.cpp`. When its URL is unset, image generation is disabled and
the editor **hides it from the interface**. Art upload and MIDI→PT3 conversion are not AI and always stay available.

## Configuration

The model server is expected to run on the host, outside Compose. Point the editor at it with
`STABLE_DIFFUSION_URL`; `host.docker.internal` resolves to the Docker host gateway via the `extra_hosts` entry in
`compose.yml`. The simplest setup is a local `.env` (gitignored):

    STABLE_DIFFUSION_URL=http://host.docker.internal:7860

The editor's environment variables and the URL each expects:

| Variable | URL / value | When unset |
|---|---|---|
| `STABLE_DIFFUSION_URL` | SD.cpp A1111 API, e.g. `http://host.docker.internal:7860` | Art generation controls hidden |
| `RVN_SETTINGS` | JSON file for editor-wide settings (desktop sets its userData path) | a per-user config file |
| `EDITOR_HOST` / `EDITOR_PORT` | bind address and port (default `127.0.0.1:8765`) | `127.0.0.1:8765` |

The old `ZXAD_SETTINGS` name is still accepted as a fallback.

The endpoint can also be set in the app: the top-bar **Settings** modal's **Image server** card saves the
stable-diffusion URL to `RVN_SETTINGS` and applies it immediately (no restart). A saved value wins over the
environment variable, so clearing the field disables image generation even when the variable set one.

## Image generation (Art / Regenerate)

The **Art** tab and **Regenerate images** are backed by
[`stable-diffusion.cpp`](https://github.com/leejet/stable-diffusion.cpp) running **Qwen-Image 2.1** with the Qwen3VL 8B
text/vision encoder:

    sd-server --diffusion-model models/qwen_image_2.1-Q8_0.gguf \
              --llm models/Qwen3VL-8B-Instruct-Q4_K_M.gguf --listen-port 7860 ...

Download those GGUFs/safetensors with `models/download-qwen-image-2.1.sh`. It serves the A1111-style `/sdapi/v1` API
(and a native `/sdcpp/v1`) on port 7860; point the editor at it with `STABLE_DIFFUSION_URL` (e.g.
`http://host.docker.internal:7860`). When `STABLE_DIFFUSION_URL` is unset, image generation is disabled and its controls
are hidden.

The image model receives `"<game prompt>, <art prompt>"`. Generate or regenerate art with the stable-diffusion server
running at http://localhost:7860 (`--game` defaults to the first game under `games/`; the standalone CLI still uses
`localhost`):

    python3 tools/gen_images.py --game <slug>          # every art
    python3 tools/gen_images.py --game <slug> dock     # one art
    python3 tools/gen_images.py --game <slug> --refs   # every reference
    python3 tools/gen_images.py --game <slug> --ref boat --ref van
    python3 tools/gen_images.py --game <slug> --refine # refine every art at 2x
    python3 tools/gen_images.py --game <slug> --refine-refs

or use the editor (`python3 tools/editor/server.py`, default port 8765), which also edits scenes/options/inventory and
previews each art. The top bar's **Regenerate images** button re-renders every reference image and then every art of the
selected game in one job (progress in the Build log); every declared reference is regenerated first (once per run) so
each art conditions on the fresh images. **Generate missing** does the same reference pass, then only fills in arts with
no image yet.

Each `## <art-id>` under `# Art` is rendered from `"<game prompt>, <art prompt>"` and written as a *new*
`assets/art/<id>/gen-<epoch>.png`; every generation or upload adds another candidate, and the art's `image:`
line (edited with the Art tab's thumbnail picker) selects which one the build converts for the target. The picker's ×
button deletes a candidate after confirmation; deleting the selected file repoints `image:` to the newest remaining
candidate (or clears it when none remain). Absent `image:` uses the newest file in the folder, and a legacy flat
`assets/gen/art_<id>.png` is still read. The render size comes from `# Game` `width`/`height` (defaults **512x256**);
the legacy square `size` is still accepted as a fallback for either axis.

Reusable references are `## <ref-id>` blocks under `# References` with their own `prompt:` (and optional
`image:`/size overrides); they render separately into `assets/refs/<id>/` and are selected per art with `refs: boat
van`. Those images are sent to the model as SD.cpp reference images (`extra_images`) so a boat, van or character keeps
one design across scenes; they are never packed into the game. The Art tab toggles them per art, and the sidebar's
**References** list edits/generates/uploads them; its image picker has the same confirmed × delete control.

The `# Game` `negative_prompt:` is sent with every render, and `hires: 2x` adds a second diffusion pass
(`hires_steps:`/`hires_denoise:`) so the saved PNG is 1024x512 from a 512x256 base. The Art tab's **Refine 2x** button
instead runs img2img from the current image (strength `refine_denoise:`), which keeps the composition and adds detail.
Each art's source is cropped to its `crop:` rectangle (`x y w h`, percent of the source) and fitted to the selected
target's art band; absent `crop:` uses the target's centred band-aspect window. The Art tab overlays a resizable box on
the Original image to set it, and the previews and saved value update when the drag is released.
