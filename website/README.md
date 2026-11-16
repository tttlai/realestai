# Realest AI website

Source for [realestai.in](https://realestai.in): a Vite + React + Tailwind single page, plus
static legal pages.

| Path | What it is |
|---|---|
| `src/` | The React homepage |
| `public/` | Copied as-is into the build: `CNAME`, `app-icon.png`, `privacy/`, `data-deletion/`, `legal.css` |
| `../docs/` | The built site. GitHub Pages serves this folder from `main`, so it is committed |

## Working on it

Requires Node 18 or later.

```sh
cd website
npm install
npm run dev        # local preview with hot reload
npm run build      # rebuilds ../docs (it is emptied first, then rebuilt)
```

After `npm run build`, commit the changes in both `website/` and `docs/`. The site updates once
they reach `main`.

GitHub Pages can only publish from the repo root or a top-level `docs/` folder, which is why the
build output lives outside `website/`.
