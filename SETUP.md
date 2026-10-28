## Local setup

Install Node.js, then run:

```bash
npm --prefix site install
npm --prefix site run dev
```

The local server serves `site/public/` and reloads the browser when files change. For hosting, upload the contents of `site/public/` to the NameHero domain's document root (typically `public_html` for the primary domain).


## Setup

```bash
uv sync --all-groups --locked
source .venv/bin/activate
```

If you use direnv:

```bash
direnv allow
```
