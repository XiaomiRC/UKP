# UKP Investigator — browser-only application

Users select files, a folder or a ZIP, choose SACs and a period, and download Excel reports plus the CSV dataset. Processing uses Python/WebAssembly in a Web Worker. No Python, EXE, pip or Node installation is needed on the user's computer.

## Build (developer or GitHub Actions only)

From the repository root:

```sh
npm ci --prefix browser
python -m pip install openpyxl==3.1.5 et-xmlfile==2.0.0 pyxlsb==1.0.10
python browser/scripts/prepare.py
npm --prefix browser test
npm --prefix browser run build
```

`prepare.py` downloads six version-matched Pyodide packages and verifies their SHA256 hashes against the installed runtime lock. It bundles only the explicitly named Python packages and application source. Its dependencies must be installed on the build machine; nothing is installed on user machines.

Serve `browser/dist/` with any static HTTPS host. For local development, prepare assets then run `npm --prefix browser run dev`. Opening index.html directly as a file is unsupported because browsers restrict worker/module and WASM file requests.

## GitHub Pages

The manual `.github/workflows/pages.yml` builds and deploys **only browser/dist**. Set repository Settings → Pages → Source to GitHub Actions, then run the Build browser application workflow. The relative base path supports both account and project Pages URLs.

Do not publish the repository's input files or reports. The root `.gitignore` excludes data and generated assets; check already-tracked files independently before making any repository public. The deployed site is https://xiaomirc.github.io/UKP/.

## Privacy

Inputs and outputs exist in Web Worker memory only. Clear session / Cancel terminates that worker, clears file selections/previews and revokes download links. Reloading loses investigation state. There is no application login, backend, analytics, localStorage, IndexedDB or service worker. The application downloads its runtime from its own origin. GitHub can log page/runtime requests; it does not receive selected file contents. Original files and explicit downloads remain on the user's disk. Browser/OS memory management is outside the application's control.

## Supported workflow

- `.xlsx` SAC reports, VP-number `.csv` bills, `.xlsb` period workbooks; individual, folder and ZIP inputs.
- Inventory, file removal, selected SACs, selected period, fixed reporting date, three analysis modes.
- Up to 500 entries, 500 MB per file, 1 GB expanded total. Streaming ZIP expansion checks actual expanded bytes. Password-protected, nested, split and ZIP64 archives are unsupported.
- Reconciliation, deep-dive, tracker reports and full CSV dataset in a downloadable ZIP; searchable control/finding/account previews.
- This engine currently supports FY2026 (P03 and P06 supplied datasets). Other years are explicitly blocked rather than producing misleading year labels. Missing required or duplicate inputs block processing.
- Power BI publishing is manual from the downloaded dataset. It necessarily sends data to Microsoft and is outside this local-only application.
- Large `.xlsb` parsing can take several minutes and require substantial RAM. Select one period and fewer SACs on constrained devices. Parsing is cached only for the current worker session.

## Verification

`npm --prefix browser test` exercises classification, ZIP equivalence, invalid archives, duplicate paths and limits. `npm --prefix browser run build` includes TypeScript checks.

`node browser/scripts/smoke.mjs --recon` runs the same WebAssembly Python engine against the repository's real inputs under Node, with a read-only-by-convention mount. Without `--recon`, it runs both analyses. Results are written to `/tmp/ukp-wasm-results.json`; source files are not modified. This verifies WASM engine compatibility, not browser/device performance.

### Additional checks

- `node browser/scripts/test-worker.mjs` exercises the actual worker message/download pipeline against TEST01, adapting only the runtime path for Node and forbidding network requests. It writes test downloads under `/tmp/ukp-worker-downloads`.
- `npm --prefix browser run test:browser` runs Playwright against the production preview after a build. Install the Playwright browser on the developer/test machine first, or set `UKP_CHROMIUM` to an installed Chromium executable.
- Chromium browser tests now pass against both the local production preview and https://xiaomirc.github.io/UKP/. See VERIFICATION.md. The desktop browser-extension integration remains separate from the isolated test browser.
