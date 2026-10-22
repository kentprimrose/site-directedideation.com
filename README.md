# site-directedideation.com

A static, single-page field guide to directed ideation. The deployable site is in `public/` and consists of plain HTML and CSS; it has no framework or backend runtime.

## Local development

Requirements: Node.js and npm.

```bash
npm install
npm run dev
```

This starts a local static server with live reload at the URL printed in the terminal. Edit files in `public/`; the browser reloads when they change.

## Deploy to NameHero

Upload the **contents** of `public/` to the document root for the domain in NameHero cPanel. For the primary domain this is usually `public_html`; addon domains and subdomains use their configured document root. Ensure `index.html` is directly in that directory, with the `site/` asset directory alongside it. No build, Node installation, or server-side application is required on the hosting account.
