# Realest AI website

Source for [realestai.in](https://realestai.in): a Vite + React + Tailwind single page, plus
static legal pages.

| Path | What it is |
|---|---|
| `src/` | The React homepage |
| `public/` | Copied as-is into the build: `CNAME`, `app-icon.png`, `brokers/` (the page for property brokers), `privacy/`, `data-deletion/`, `legal.css` |
| `dist/` | Local build output (not committed) |

## Publishing

Pushing changes under `website/` to `main` runs
[`.github/workflows/deploy-website.yml`](../.github/workflows/deploy-website.yml), which builds
the site and publishes it to GitHub Pages. There is nothing to build or commit by hand. You can
also run it from the repo's **Actions** tab → **Deploy website** → **Run workflow**.

This needs the repo's **Settings → Pages → Build and deployment → Source** set to
**GitHub Actions**, with `realestai.in` as the custom domain.

## Working on it locally

Requires Node 18 or later.

```sh
cd website
npm install
npm run dev        # local preview with hot reload
npm run build      # optional: check the production build in dist/
```
