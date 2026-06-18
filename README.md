## Indexing and SEO

I added automatic sitemap support and a submission endpoint to help get your site indexed quickly by search engines.

What I added

- /sitemap.xml — dynamically-generated sitemap of primary pages (/, /scan, /contact, /signup, /api/verify-chain).
- /robots.txt — updated to include the Sitemap: line pointing to your sitemap.xml so crawlers discover it automatically.
- /_submit_sitemap — an admin-protected endpoint that attempts to notify Google and Bing by pinging their sitemap endpoints. Protect it by setting ADMIN_TOKEN in your environment and then POST to this endpoint to trigger pings.

How to use

1. Deploy the site to your public host (ensure HOST env is set to the canonical URL, e.g. https://sebbi.pro).
2. Visit https://your-host/sitemap.xml to confirm it is reachable.
3. Visit https://your-host/robots.txt to confirm it references the sitemap.
4. Optionally submit the site to Google Search Console and Bing Webmaster Tools for verification and indexing. Use the same HOST value as the property.
5. To programmatically ping crawlers from the server (after deployment):

   curl -X POST https://your-host/_submit_sitemap -H "X-Admin-Token: <ADMIN_TOKEN>"

Notes

- Submitting the sitemap via these pings is a courtesy; to fully manage indexing, verify your site in Google Search Console and Bing Webmaster Tools and submit the sitemap there as well.
- For Google Search Console you will need to verify site ownership — follow the instructions in Search Console. Once verified you can submit sitemaps and request indexing for individual URLs.

If you want, I can also:

- Add JSON-LD structured data to the landing page (Organization and WebSite schema).
- Expand the sitemap to include dynamically-created pages (e.g., per-customer pages) if you add them later.
- Automate Search Console API submissions (requires OAuth and verification access).
