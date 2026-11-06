# Verification — 6 November 2026

- Production build and TypeScript checks passed.
- Ten input tests passed: individual/ZIP equivalence, folder paths, ignored outputs/templates, duplicates, count limits, unsafe paths/nested archives, encrypted ZIPs, declared oversized entries, truncation, and cancellation.
- Two Python dataset-update regression tests passed.
- WebAssembly Python engine ran reconciliation and deep dive for all 11 supplied P06 SACs, generating 33 workbooks in its virtual filesystem.
- Compared 308 numeric reconciliation/headline values with the existing dataset: no differences at GBP 0.02 tolerance.
- Full run recorded 138 PASS, 12 WARN, seven INFO and one FAIL. TEST02's empty VP00000000 bill remains a source-data failure.
- Actual production worker logic was tested under a Node harness, adapting only the file-based runtime location and forbidding network requests. TEST01 produced a results ZIP, a readable six-sheet Excel workbook, seven controls, and 29 account records. ZIP integrity passed.
- Checked the static artifact allowlist: 17 files, with no investigation XLSX/XLSB/CSV/parquet files. The engine ZIP contains only application source, rule configuration and the three explicitly bundled pure-Python dependencies.
- Cold parsing of P06 in WebAssembly took about seven minutes for the first SAC in this environment. Later SACs used memory-only cached sheets and took approximately 16–63 seconds each. These are Node/WASM timings, not browser-device measurements.

## Not verified

Browser rendering/device performance and Playwright UI/network-storage tests could not run in this sandbox. Local-server binding was denied (EPERM), and Chromium launch failed on a crashpad socket restriction. The Playwright suite is included for execution in a normal test environment. No live GitHub Pages site was published.

The application currently supports FY2026 inputs; other fiscal years are blocked to prevent misleading year labels. Online Power BI publishing remains manual and requires sending data to Microsoft.
