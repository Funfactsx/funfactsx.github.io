# Fun Facts — public static mirror

Repository for **https://funfactsx.github.io/**, hosted by GitHub Pages.

The site is generated from the **publicly rendered** pages at https://uwarboretum.org/. It does not contain the ASP.NET CMS, SQL Server credentials, Hangfire jobs, or AI publishing components.

## Deployment

1. In **Settings → Pages**, select **GitHub Actions** as the publishing source.
2. The workflow **Export Fun Facts and publish static GitHub Pages** is in **Actions**.
3. On the first push, a **preview** job automatically exports the public pages. Use the Actions run to check progress.
4. The exporter discovers every category's pagination and all article links, downloads HTML and same-origin static assets, and leaves article images on their existing CDN.
5. The workflow refuses to deploy if fewer than 3,000 unique articles are found or any discovered article request fails.
6. A successful preview sets `noindex,nofollow` in generated HTML and `Disallow: /` in robots.txt to avoid accidentally indexing duplicate content.
7. **Only after inspecting the deployed pages and deciding whether to index the mirror**, manually run the workflow from Actions with mode `production`. This removes the preview crawler restrictions.

## Important differences

- Existing clean fact slugs become files like `/<fact-slug>.html`. Verify clean URL resolution on GitHub Pages.
- Listing pagination changes from `/animals?page=2` to `/animals/page/2/` because GitHub Pages cannot generate different HTML from query strings.
- Search and random facts work in the browser using a generated `facts.json` index. Content is a snapshot of the origin at export time.
- Source CDN images are still loaded from `funfacts-cdn.whitescreen.dev`; its availability must be maintained.
- No administration or content publishing takes place on this repository.
- GitHub Actions will only repeat the export on source-code changes or manual dispatch. There is no scheduled publication.
- **The exporter is not a guarantee of SEO-equivalent migration**, particularly for query-based pagination, old redirects, or canonical history.

## Build output

The generated Pages artifact contains `index.html`, the full fact HTML collection, categories, `facts.json`, `sitemap.xml`, `robots.txt` and `build-report.json`.

For local Python dependency setup: `python -m pip install -r requirements.txt`.

Do not point the original domain DNS here; this is a separate site under `funfactsx.github.io`.
