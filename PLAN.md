# Static site redesign plan

## Context
The current site is a single, content-rich field guide served through Django templates. The request is to make it a static website, eliminate Django and all Django references, and assess React/FastAPI only if they solve a real need. The intended hosting is NameHero.

## Approach
Use plain HTML and CSS in a root `public/` directory, with `public/index.html` and its assets. No React or FastAPI: this content-focused single page has only anchor navigation and no dynamic interactions or API needs. For local development, use a small Node-based static server with live reload (e.g. `live-server`) serving `public/`; this is development-only and does not affect hosting. NameHero shared hosting supports static files: upload the *contents* of `public/` into the domain's document root (`public_html` for the primary domain, or the configured document root for an addon domain/subdomain), ensuring `index.html` is at the root. Preserve relative asset paths so the same files work locally and on NameHero. No build step is required.

## Files to modify
- `public/index.html` (new) — migrate the existing page, remove Django template tag, use relative asset path.
- `public/site/style.css` (new) — retain existing stylesheet.
- `package.json` and optionally `package-lock.json` (new) — development-only live-reload server and scripts.
- `pyproject.toml`, `uv.lock`, `manage.py`, Python package under `src/site_directedideation_com/`, `tests/` — remove obsolete Python/Django app and tests.
- `README.md`, `SETUP.md`, `.gitignore` — document Node-based local preview and NameHero static deployment; remove Python-specific guidance/ignores as appropriate.

## Reuse
- Existing complete page content and semantic section structure in `src/site_directedideation_com/templates/site/home.html`.
- Existing responsive styling in `src/site_directedideation_com/static/site/style.css`.
- Existing page uses only internal anchor links; no JavaScript behavior or backend/API requirement is evident.
- NameHero's upload guidance identifies `public_html` as the usual primary-domain document root; addon domains/subdomains use their configured document root. Sources: [NameHero File Manager upload](https://www.namehero.com/index.php?rp=%2Fknowledgebase%2F9%2FHow-To-Upload-Using-File-Manager.html), [NameHero addon/subdomain guidance](https://help.namehero.com/en/articles/7005199-how-to-create-a-subdomain-in-cpanel).

## Steps
- [x] Create `public/index.html` and `public/site/style.css` from the existing content/design; remove all Django template syntax and use relative stylesheet URLs.
- [x] Remove Django/Python runtime, package configuration, lockfile, and obsolete tests; ensure no Django references remain in maintained project files.
- [x] Add a minimal development-only live-reload server script and update README/setup instructions for local preview and NameHero upload.
- [x] Verify local server/reload, responsive layout and anchor navigation, and that the static files work when served from a document-root-equivalent directory.

## Verification
- Search maintained project files for Django references/dependencies and confirm none remain.
- Run the local live-reload server, verify the page and CSS load, change a file and confirm browser reload.
- Serve `public/` as the document root and inspect stylesheet loading, navigation anchors, and mobile layout. Deployment is a direct upload of `public/` contents to the NameHero domain document root; no server-side runtime or build process is required.
