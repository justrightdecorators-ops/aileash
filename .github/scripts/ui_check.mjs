// ui_check.mjs - drive the new pages in real Chrome and fail on any script error.
// Run by .github/workflows/ui.yml inside the no-network sandbox, against a
// throwaway local copy of the site. Never touches the live site.
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import puppeteer from "puppeteer-core";

const ROOT = new URL("../..", import.meta.url).pathname;
const BASE = "http://127.0.0.1:8855";
const work = mkdtempSync(join(tmpdir(), "ui-"));
const env = { ...process.env, PORT: "8855", DB_PATH: join(work, "a.db"), ANCHOR_DIR: join(work, "anc"), OTS_AUTO_UPGRADE: "0" };
const server = spawn("python3", ["server.py"], { cwd: ROOT, env, stdio: "ignore" });
const pass = [], fail = [];
const chk = (n, c, d = "") => { (c ? pass : fail).push(n); console.log((c ? "  ok   " : "  FAIL ") + n + (c ? "" : "  -> " + String(d).slice(0, 300))); console.log(c ? `::notice title=ok::${n}` : `::error title=UI check failed::${n} ${String(d).slice(0, 300).replace(/\n/g, " ")}`); };
const tap = (page, sel) => page.$eval(sel, el => { el.scrollIntoView({ block: "center" }); el.click(); });
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function up() { for (let i = 0; i < 60; i++) { try { const r = await fetch(BASE + "/api/health"); if (r.ok) return; } catch (e) {} await sleep(500); } throw new Error("server did not start"); }

let browser;
try {
  await up();
  await fetch(BASE + "/x/arm/status");
  browser = await puppeteer.launch({ executablePath: process.env.CHROME || "/usr/bin/google-chrome", args: ["--no-sandbox", "--disable-gpu"] });

  async function open(path) {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    page.on("console", m => { if (m.type() === "error" && !/fonts\.googleapis|ERR_|Failed to load resource/.test(m.text())) errors.push(m.text()); });
    await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
    await sleep(600);
    return { page, errors };
  }

  // /build
  {
    const { page, errors } = await open("/build");
    const s1 = await page.$eval("#sentence", e => e.textContent);
    chk("build: sentence written for the first rule", s1.startsWith("If ") && s1.length > 30, s1);
    await page.type("#pa", "UI check");
    await sleep(1500);
    const v1 = await page.$eval("#vtext", e => e.textContent);
    chk("build: engine says the pack is ready", /Ready to publish/.test(v1), v1);
    await tap(page, '.tpl button[data-t="budget"]');
    await sleep(300);
    const s2 = await page.$eval("#sentence", e => e.textContent);
    chk("build: template changes the sentence", s2 !== s1 && /budget/.test(s2), s2);
    await tap(page, "#addrule");
    await sleep(300);
    const n = await page.$$eval(".rule", e => e.length);
    chk("build: add a rule", n === 3, n);
    const out = await page.$eval("#outcome", e => e.textContent);
    chk("build: test bench gives an answer", out.length > 5, out);
    await sleep(1200);
    const v2 = await page.$eval("#vtext", e => e.textContent);
    chk("build: new rule without a why is caught", /why/.test(v2), v2);
    await page.type(".rule.sel input[data-k=why]", "Big spend needs a person.");
    await sleep(1500);
    const v3 = await page.$eval("#vtext", e => e.textContent);
    chk("build: fixed pack is ready again", /Ready to publish/.test(v3), v3);
    await tap(page, "#pub");
    await sleep(1500);
    const pm = await page.$eval("#pmsg", e => e.textContent);
    chk("build: publishes", /Published/.test(pm), pm);
    chk("build: no script errors", errors.length === 0, errors.join(" | "));
  }

  // /connect
  {
    const r = await fetch(BASE + "/signup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "UI", email: "ui@example.org", org: "UI Ltd", product: "aileash", devices: 1 }) });
    const key = (await r.json()).api_key;
    const { page, errors } = await open("/connect");
    await tap(page, '.tab[data-t="have"]');
    await page.type("#pk", key);
    await tap(page, "#usekey");
    const code = await page.$eval("#code", e => e.textContent);
    chk("connect: key written into the snippet", code.includes(key), code.slice(0, 120));
    await tap(page, '.stack button[data-s="zapier"]');
    const z = await page.$eval("#code", e => e.textContent);
    chk("connect: Zapier settings shown", /Webhooks|POST/.test(z) && z.includes(key), z.slice(0, 120));
    await tap(page, '.stack button[data-s="lovable"]');
    const l = await page.$eval("#code", e => e.textContent);
    chk("connect: Lovable prompt shown", /SEBBI_API_KEY/.test(l), l.slice(0, 120));
    await tap(page, "#fire");
    await sleep(2500);
    const m = await page.$eval("#fmsg", e => e.textContent);
    const b = await page.$eval("#n3t", e => e.textContent);
    chk("connect: test decision sealed on the wire", /Sealed/.test(m) && /Block \d+/.test(b), m + " / " + b);
    chk("connect: no script errors", errors.length === 0, errors.join(" | "));
  }

  // Human Keys pages load clean
  for (const path of ["/keys", "/k/"]) {
    const { page, errors } = await open(path);
    chk("keys: " + path + " loads without script errors", errors.length === 0, errors.join(" | "));
  }
  // homepage strip visible
  {
    const { page, errors } = await open("/");
    const has = await page.$(".sbx");
    chk("homepage: feature strip present", !!has);
  }
} catch (e) {
  chk("ui check ran", false, e.stack || e.message);
} finally {
  if (browser) await browser.close();
  server.kill();
}
console.log(`\npassed ${pass.length}, failed ${fail.length}`);
process.exit(fail.length ? 1 : 0);
