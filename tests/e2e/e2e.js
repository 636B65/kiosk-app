const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

// Resolve repo paths relative to this file (tests/e2e) -> repo root.
const REPO = path.resolve(__dirname, "..", "..");
const FRONT = path.join(REPO, "frontend");
const BACKEND_CWD = path.join(REPO, "backend");

const PORT = Number(process.env.E2E_PORT || 8082);
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT || 8013);
const BACKEND = `127.0.0.1:${BACKEND_PORT}`;
const DB = process.env.E2E_DB || path.join(REPO, ".e2e-db.sqlite");
const PYTHON = process.env.E2E_PYTHON || "python3";

try { fs.unlinkSync(DB); } catch {}
// "Back up now" writes next to the database; remove what this run created.
const BACKUP_DIR = path.join(path.dirname(DB), "backups");
const backupDirExisted = fs.existsSync(BACKUP_DIR);
// The PIN pepper (backend/pins.py) is created next to the database on first use.
const PIN_PEPPER = path.join(path.dirname(DB), "pin_pepper.key");
const pinPepperExisted = fs.existsSync(PIN_PEPPER);

const backend = spawn(
  PYTHON,
  ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
  {
    cwd: BACKEND_CWD,
    env: {
      ...process.env,
      DATABASE_PATH: DB,
      ADMIN_PASSWORD: process.env.E2E_ADMIN_PASSWORD || "test-admin-password",
    },
    stdio: "ignore",
  }
);

function waitForBackend(retries = 60) {
  return new Promise((resolve, reject) => {
    const tryReq = () => {
      const req = http.get(`http://${BACKEND}/api/health`, (res) => {
        res.resume();
        resolve();
      });
      req.on("error", () => {
        if (--retries <= 0) return reject(new Error("backend not up"));
        setTimeout(tryReq, 300);
      });
    };
    tryReq();
  });
}

const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".png": "image/png", ".svg": "image/svg+xml", ".json": "application/json",
  ".md": "text/markdown; charset=utf-8",
};

function staticHandler(req, res) {
  let urlPath = decodeURIComponent(req.url.split("?")[0]);
  if (urlPath === "/") urlPath = "/index.html";
  // The Docker image copies the repo-root CHANGELOG.md next to index.html.
  const changelog = urlPath === "/CHANGELOG.md";
  const file = changelog ? path.join(REPO, "CHANGELOG.md") : path.join(FRONT, urlPath);
  if (!changelog && !file.startsWith(FRONT)) { res.writeHead(403); return res.end(); }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); return res.end("Not found"); }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    res.end(data);
  });
}

function proxyHandler(req, res) {
  const options = {
    hostname: "127.0.0.1", port: BACKEND_PORT,
    path: req.url, method: req.method, headers: req.headers,
  };
  const proxy = http.request(options, (upstream) => {
    res.writeHead(upstream.statusCode, upstream.headers);
    upstream.pipe(res);
  });
  proxy.on("error", (e) => { res.writeHead(502); res.end("Bad gateway: " + e.message); });
  req.pipe(proxy);
}

const server = http.createServer((req, res) => {
  if (req.url.startsWith("/api/")) return proxyHandler(req, res);
  return staticHandler(req, res);
});

server.listen(PORT, async () => {
  console.log(`frontend+proxy on http://127.0.0.1:${PORT}`);
  try {
    await waitForBackend();
  } catch (e) {
    console.error("Backend failed to start:", e.message);
    backend.kill("SIGTERM");
    server.close();
    process.exit(1);
  }
  console.log("backend ready");

  const executable = process.env.CHROMIUM_PATH || "/usr/bin/chromium";
  const browser = await chromium.launch({
    executablePath: executable,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errors = [];
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const url = m.location()?.url;
    errors.push(url ? `${m.text()} [${url}]` : m.text());
  });
  page.on("pageerror", (e) => errors.push("PAGEERROR: " + e.message));

  const results = [];
  async function step(name, fn) {
    try {
      const extra = await fn();
      results.push(`PASS  ${name}${extra ? " — " + extra : ""}`);
    } catch (e) {
      results.push(`FAIL  ${name} — ${e.message.split("\n")[0]}`);
      if (process.env.E2E_FAIL_SHOTS) {
        await page.screenshot({ path: path.join(process.env.E2E_FAIL_SHOTS, name.replace(/\W+/g, "_") + ".png") }).catch(() => {});
        console.log("FAILED AT", page.url());
      }
    }
  }

  // Set the store-wide payment due date through the admin API. Only an
  // overdue due date blocks checkout, so the block step needs one in the past.
  async function setPaymentDueDate(value) {
    const login = await fetch(`http://${BACKEND}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "admin", password: process.env.E2E_ADMIN_PASSWORD || "test-admin-password" }),
    });
    if (!login.ok) throw new Error("admin login failed: " + login.status);
    const { access_token } = await login.json();
    const res = await fetch(`http://${BACKEND}/api/settings/payment_due_date`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${access_token}` },
      body: JSON.stringify({ key: "payment_due_date", value }),
    });
    if (!res.ok) throw new Error("failed to set payment_due_date: " + res.status);
  }

  async function setSetting(key, value) {
    const login = await fetch(`http://${BACKEND}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "admin", password: process.env.E2E_ADMIN_PASSWORD || "test-admin-password" }),
    });
    if (!login.ok) throw new Error("admin login failed: " + login.status);
    const { access_token } = await login.json();
    const res = await fetch(`http://${BACKEND}/api/settings/${key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${access_token}` },
      body: JSON.stringify({ key, value }),
    });
    if (!res.ok) throw new Error(`failed to set ${key}: ${res.status}`);
  }

  async function setCustomerSelfServicePayment(value) {
    const login = await fetch(`http://${BACKEND}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "admin", password: process.env.E2E_ADMIN_PASSWORD || "test-admin-password" }),
    });
    if (!login.ok) throw new Error("admin login failed: " + login.status);
    const { access_token } = await login.json();
    const res = await fetch(`http://${BACKEND}/api/settings/customer_self_service_payment`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${access_token}` },
      body: JSON.stringify({ key: "customer_self_service_payment", value }),
    });
    if (!res.ok) throw new Error("failed to set customer self-service payment: " + res.status);
  }

  try {
    // ---- CUSTOMER FLOW ----
    await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
    await page.waitForSelector(".product-card");

    await step("customer: sees products in EUR", async () => {
      const price = await page.locator(".product-price").first().textContent();
      if (!price.includes("€")) throw new Error("not EUR: " + price);
      return price.trim();
    });

    await step("customer: footer shows release and opens changelog", async () => {
      const version = (await page.locator("#app-version").textContent()).trim();
      if (!version.startsWith("Kiosk ")) throw new Error("no release in footer: " + version);
      await page.locator('.app-footer [data-action="show-changelog"]').click();
      await page.waitForSelector(".changelog h3");
      const first = (await page.locator(".changelog h3").first().textContent()).trim();
      if (!/^\[\d+\.\d+\.\d+\]/.test(first)) throw new Error("unexpected changelog heading: " + first);
      await page.locator('#modal-overlay [data-action="modal-close"]').click();
      await page.waitForSelector("#modal-overlay", { state: "detached" });
      return `${version}; latest ${first}`;
    });

    await step("customer: add to cart (no tax line)", async () => {
      const card = page.locator(".product-card", { hasText: "USB-C Cable" }).first();
      await card.locator(".add-btn").click();
      await card.locator(".qty-btn[data-delta='1']").click();
      await page.locator(".cart-btn", { hasText: "Cart" }).click();
      await page.waitForSelector("#cart-overlay");
      const text = await page.locator("#cart-overlay").textContent();
      if (text.includes("Tax")) throw new Error("tax line still present");
      const total = await page.locator("#cart-overlay .cart-total-row").last().locator("span").last().textContent();
      const expected = new Intl.NumberFormat("sv-SE", { style: "currency", currency: "EUR", minimumFractionDigits: 2 }).format(19.98);
      if (total.trim() !== expected.trim()) throw new Error(`total ${total} != ${expected}`);
      return `total = ${total.trim()} (2 × 9,99)`;
    });

    await step("customer: buy requires username", async () => {
      await page.locator(".checkout-btn").click();
      await page.waitForSelector("#checkout-form");
      const label = await page.locator("#checkout-form label").first().textContent();
      if (!label.includes("Username")) throw new Error("no username prompt");
      const focused = await page.evaluate(() => document.activeElement?.id);
      if (focused !== "co-username") throw new Error("cursor not in the username field: " + focused);
      return "username prompt shown with the cursor in it";
    });

    await step("customer: checkout creates new user", async () => {
      await page.fill("#co-username", "alice");
      await page.locator("#checkout-form button[type=submit]").click();
      await page.waitForFunction(() => {
        const t = document.querySelector("#modal-overlay")?.textContent || "";
        return t.includes("Order #");
      }, undefined, { timeout: 7000 });
      const text = await page.locator("#modal-overlay").textContent();
      const ord = text.match(/Order #(\d+)/);
      if (!ord) throw new Error("no order number");
      const bal = text.match(/Balance to pay: (.+)/);
      if (!bal) throw new Error("no balance display");
      const confettiCanvas = await page.evaluate(
        () => !!document.querySelector("canvas.confetti-layer")
      );
      if (!confettiCanvas) throw new Error("no confetti on order complete");
      return `order ${ord[1]} — ${bal[1].trim()} (confetti ✓)`;
    });

    await step("customer: lookup after buy opens lookup + typing username", async () => {
      await page.locator("#modal-overlay button", { hasText: "Look up user" }).click();
      await page.waitForSelector("#lookup-form");
      await page.fill("#lk-username", "alice");
      await page.locator("#lookup-form button[type=submit]").click();
      await page.waitForTimeout(800);
      const text = await page.locator("#modal-overlay").textContent();
      if (!text.includes("Order #")) throw new Error("lookup after buy did not show history");
      await page.locator("#modal-overlay button", { hasText: "Close" }).click();
      await page.waitForTimeout(300);
      const badge = await page.locator("#cart-count").textContent();
      if (badge.trim() !== "0") throw new Error("cart not cleared after buy: " + badge);
      return "history shown after buy lookup; cart cleared";
    });

    await step("customer: second buy blocked while unpaid (overdue)", async () => {
      // The unpaid-order block only fires when a payment due date is set AND
      // has passed; make the store overdue for this step, then restore "".
      await setPaymentDueDate("2020-01-01");
      try {
        await page.locator(".product-card", { hasText: "Chocolate Bar" }).first().locator(".add-btn").click();
        await page.locator(".cart-btn", { hasText: "Cart" }).click();
        await page.waitForSelector("#cart-overlay");
        await page.locator(".checkout-btn").click();
        await page.waitForSelector("#checkout-form");
        await page.fill("#co-username", "alice");
        await page.locator("#checkout-form button[type=submit]").click();
        // alice still has an unpaid order and the due date passed -> rejected
        await page.waitForSelector(".toast.error", { timeout: 7000 });
        const toast = await page.locator(".toast.error").last().textContent();
        if (!toast.includes("still unpaid")) throw new Error("unexpected toast: " + toast);
        return `blocked: ${toast.trim()}`;
      } finally {
        await setPaymentDueDate("");
      }
    });

    await step("customer: user lookup shows balance + history + stats", async () => {
      await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
      await page.waitForSelector(".product-card");
      await page.locator("#lookup-btn").click();
      await page.waitForSelector("#lookup-form");
      await page.fill("#lk-username", "alice");
      await page.locator("#lookup-form button[type=submit]").click();
      await page.waitForTimeout(800);
      const modal = page.locator("#modal-overlay");
      const text = await modal.textContent();
      if (!text.includes("Order #")) throw new Error("no history");
      const totalBlocks = await modal.locator(".history-order-total").count();
      if (totalBlocks === 0) throw new Error("no item totals");
      if ((await modal.locator(".customer-stats").count()) === 0) throw new Error("no stats panel");
      const balance = await modal.locator(".balance-big").textContent();
      if (!balance.includes("€")) throw new Error("no EUR balance: " + balance);
      return `balance ${balance.trim()}, ${totalBlocks} order(s), stats present`;
    });

    await step("customer: user lookup autocompletes while typing", async () => {
      await page.locator("#modal-overlay button", { hasText: "Another user" }).click();
      await page.waitForSelector("#lookup-form");
      await page.fill("#lk-username", "ali");
      await page.waitForSelector(".lookup-suggestion", { timeout: 5000 });
      const suggestion = await page.locator(".lookup-suggestion").first().textContent();
      if (!(suggestion || "").includes("alice")) throw new Error("expected 'alice' suggestion, got: " + suggestion);
      await page.locator(".lookup-suggestion", { hasText: "alice" }).click();
      await page.waitForTimeout(800);
      const text = await page.locator("#modal-overlay").textContent();
      if (!text.includes("Order #")) throw new Error("pick did not trigger lookup");
      return `suggestion "${suggestion}" picked`;
    });

    await step("customer: lookup unknown user shows error", async () => {
      await page.locator("#modal-overlay button", { hasText: "Another user" }).click();
      await page.waitForSelector("#lookup-form");
      await page.fill("#lk-username", "ghost_user_x");
      await page.locator("#lookup-form button[type=submit]").click();
      await page.waitForSelector(".toast.error", { timeout: 5000 });
      return "toast shown";
    });

    // ---- ADMIN FLOW ----
    await page.evaluate(() => {
      document.getElementById("modal-overlay")?.remove();
      document.querySelectorAll(".toast-container").forEach((t) => t.remove());
    });
    await page.goto(`http://127.0.0.1:${PORT}/#admin`, { waitUntil: "networkidle" });
    await page.reload();
    await page.waitForSelector(".auth-card", { timeout: 7000 });
    await step("admin: login", async () => {
      await page.fill("#login-username", "admin");
      await page.fill("#login-password", process.env.E2E_ADMIN_PASSWORD || "test-admin-password");
      await page.click("#login-form button[type=submit]");
      await page.waitForSelector(".admin-layout", { timeout: 5000 });
      await page.waitForSelector(".stat-card", { timeout: 5000 });
      return "dashboard visible";
    });

    await step("admin: dashboard shows outstanding balance", async () => {
      const labels = await page.locator(".stat-card .label").allTextContents();
      if (!labels.includes("Outstanding Balance")) throw new Error("no outstanding stat");
      const text = await page.locator(".stat-card", { hasText: "Outstanding Balance" }).textContent();
      if (!text.includes("€")) throw new Error("not EUR");
      return text.replace(/\s+/g, " ").trim();
    });

    await step("admin: orders show username + paid statuses", async () => {
      await page.locator('a[data-view="orders"]').click();
      await page.waitForTimeout(600);
      const text = await page.locator("#admin-main-container").textContent();
      if (!text.includes("alice")) throw new Error("no alice column");
      const headers = await page.locator("thead th").allTextContents();
      if (!headers.some((h) => h.includes("User"))) throw new Error("no User column");
      return headers.join(" | ");
    });

    await step("admin: view order items table renders", async () => {
      await page.locator(".view-order").first().click();
      await page.waitForTimeout(600);
      const modal = page.locator("#modal-overlay");
      const text = await modal.textContent();
      if (!text.includes("Order #")) throw new Error("no order modal");
      if (!text.includes("Unit Price")) throw new Error("no items table");
      const rows = await modal.locator("tbody tr").count();
      if (rows === 0) throw new Error("no item rows");
      await modal.locator("button", { hasText: "Close" }).click();
      await page.waitForTimeout(300);
      return `${rows} item(s) shown`;
    });

    await step("admin: new product form has image upload, EUR price", async () => {
      await page.locator('a[data-view="products"]').click();
      await page.waitForTimeout(600);
      await page.locator("button", { hasText: "+ New Product" }).click();
      await page.waitForSelector("#product-form");
      const labels = await page.locator("#product-form label").allTextContents();
      if (!labels.some((l) => l.includes("Price (EUR)"))) throw new Error("no 'Price (EUR)' label: " + labels.join(" | "));
      if ((await page.locator("#p-image-file").count()) !== 1) throw new Error("no image upload field");
      const body = await page.locator("#modal-overlay").textContent();
      if (body.includes("Price ($)")) throw new Error("currency still shows $");
      await page.locator("#product-form button", { hasText: "Cancel" }).click();
      await page.waitForTimeout(200);
      return labels.filter((l) => l.includes("Price")).join(" | ");
    });

    await step("admin: upload product image shows in admin list", async () => {
      const row = page.locator("tr", { hasText: "USB-C Cable" }).first();
      await row.locator(".edit-product").click();
      await page.waitForSelector("#product-form");
      await page.locator("#p-image-file").setInputFiles({
        name: "cable.png",
        mimeType: "image/png",
        buffer: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
          "base64"
        ),
      });
      await page.locator("#product-form button[type=submit]").click();
      await page.waitForTimeout(800);
      const thumb = await page.locator("tr", { hasText: "USB-C Cable" }).locator(".thumb");
      const src = await thumb.getAttribute("src");
      if (!src || !src.startsWith("/api/images/")) throw new Error("no image src: " + src);
      return "thumb src " + src;
    });

    await step("admin: mark product as weekly special", async () => {
      const row = page.locator("tr", { hasText: "USB-C Cable" }).first();
      await row.locator(".edit-product").click();
      await page.waitForSelector("#product-form");
      await page.locator("#p-weekly").check();
      await page.waitForTimeout(100);
      await page.locator("#p-special-price").fill("5.00");
      await page.locator("#product-form button[type=submit]").click();
      await page.waitForTimeout(800);
      const badge = page.locator("tr", { hasText: "USB-C Cable" }).locator(".weekly-badge");
      if ((await badge.count()) !== 1) throw new Error("no weekly badge in admin list");
      return "weekly badge shown";
    });

    await step("admin: assign multiple barcodes to a product", async () => {
      const row = page.locator("tr", { hasText: "USB-C Cable" }).first();
      await row.locator(".edit-product").click();
      await page.waitForSelector("#product-form");
      await page.locator("#p-barcodes").fill("0123456789012\nUSB-C-ALT");
      await page.locator("#product-form button[type=submit]").click();
      await page.waitForTimeout(700);
      if (await page.locator("#modal-overlay").count()) throw new Error("product edit did not save");
      return "two barcodes saved";
    });

    await step("customer: self-scanning is off by default", async () => {
      await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
      await page.waitForSelector(".product-card");
      if (await page.locator("#barcode-input").count()) throw new Error("scan field shown although scanning is off");
      return "no scan field until an admin enables it";
    });

    await step("customer: scan either barcode to add product to cart", async () => {
      await setSetting("kiosk_barcode_scanning", "true");
      try {
        await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
        await page.waitForSelector("#barcode-input");
        const input = page.locator("#barcode-input");
        await input.fill("0123456789012");
        await input.press("Enter");
        await page.waitForFunction(() => document.querySelector("#cart-count")?.textContent === "1");
        await input.fill("USB-C-ALT");
        await input.press("Enter");
        await page.waitForFunction(() => document.querySelector("#cart-count")?.textContent === "2");
        await page.locator(".cart-btn", { hasText: "Cart" }).click();
        await page.waitForSelector("#cart-overlay");
        const cart = await page.locator("#cart-overlay").textContent();
        if (!cart.includes("USB-C Cable") || !cart.includes("× 2")) {
          throw new Error("barcode scans did not add the same item twice: " + cart);
        }
        await page.locator("#cart-overlay .cart-close").click();
        await page.evaluate(() => localStorage.removeItem("kiosk_cart"));
      } finally {
        await setSetting("kiosk_barcode_scanning", "false");
      }
      return "both codes added USB-C Cable to cart";
    });

    await step("admin: customers page lists balance", async () => {
      await page.goto(`http://127.0.0.1:${PORT}/#admin/customers`, { waitUntil: "networkidle" });
      await page.waitForTimeout(600);
      const row = page.locator("tr", { hasText: "alice" });
      const text = await row.textContent();
      if (!text.includes("€")) throw new Error("no EUR balance");
      if ((await row.locator(".reset-payment").count()) !== 1) throw new Error("reset button missing");
      return (await row.locator("td").nth(6).textContent()).trim();
    });

    await step("admin: view customer history from admin", async () => {
      await page.locator(".view-customer").first().click();
      await page.waitForTimeout(600);
      const modal = page.locator("#modal-overlay");
      const text = await modal.textContent();
      if (!text.includes("Order #")) throw new Error("no history modal");
      const historyCount = (await modal.locator(".history-order").count());
      return `${historyCount} orders shown`;
    });

    await step("admin: reset payment clears balance", async () => {
      await page.locator("#reset-from-modal").click();
      await page.waitForSelector(".toast.success", { timeout: 5000 });
      await page.waitForTimeout(700);
      const row = page.locator("tr", { hasText: "alice" });
      const balText = (await row.locator("td").nth(6).textContent()).replace(/\s+/g, "");
      if (balText !== "0,00€") throw new Error("balance not reset: " + balText);
      return "payment reset → " + balText;
    });

    await step("admin: reports show outstanding cleared", async () => {
      await page.goto(`http://127.0.0.1:${PORT}/#admin/reports`, { waitUntil: "networkidle" });
      await page.waitForTimeout(700);
      const text = await page.locator("#admin-main-container").textContent();
      if (!text.includes("Outstanding")) throw new Error("no outstanding in reports");
      if (!text.includes("Customer insights") || !text.includes("Top customers today")) {
        throw new Error("customer insights missing from reports");
      }
      if (!text.includes("Last customer to pay")) throw new Error("last payer insight missing");
      if (!text.includes("Products bought most today")) throw new Error("product insights missing from reports");
      const stat = await page.locator(".stat-card", { hasText: "Outstanding Balance" }).textContent();
      if (!stat.includes("0,00")) throw new Error("outstanding not cleared: " + stat.replace(/\s+/g, " "));
      return "reports ok";
    });

    await step("admin: export report statistics as CSV", async () => {
      const downloadPromise = page.waitForEvent("download");
      await page.locator('[data-action="admin-export-reports-csv"]').click();
      const download = await downloadPromise;
      if (!download.suggestedFilename().startsWith("kiosk-report-") ||
          !download.suggestedFilename().endsWith(".csv")) {
        throw new Error("unexpected export filename: " + download.suggestedFilename());
      }
      const stream = await download.createReadStream();
      let content = "";
      for await (const chunk of stream) content += chunk.toString("utf8");
      if (!content.includes("customer_balance") || !content.includes("inventory") ||
          !content.includes("top_products")) {
        throw new Error("CSV missing customer balances, stock, or product insights");
      }
      return "downloaded report CSV with balances, inventory, and insights";
    });

    await step("admin: customer lookup matches after reset", async () => {
      await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
      await page.waitForSelector(".product-card");
      await page.locator("#lookup-btn").click();
      await page.waitForSelector("#lookup-form");
      await page.fill("#lk-username", "alice");
      await page.locator("#lookup-form button[type=submit]").click();
      await page.waitForTimeout(700);
      const text = await page.locator("#modal-overlay").textContent();
      if (!text.includes("No outstanding balance")) throw new Error("balance not zero");
      await page.locator("#modal-overlay button", { hasText: "Close" }).click();
      await page.waitForTimeout(300);
      return "customer sees 0 to pay";
    });

    await step("customer: buy again allowed after payment", async () => {
      // The earlier blocked purchase left a Chocolate Bar in the persisted cart
      // (localStorage), which turns that product's add button into qty controls.
      // Clear it and reload to start from an empty cart.
      await page.evaluate(() => localStorage.removeItem("kiosk_cart"));
      await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
      await page.waitForSelector(".product-card");
      await page.locator(".product-card", { hasText: "Chocolate Bar" }).first().locator(".add-btn").click();
      await page.locator(".cart-btn", { hasText: "Cart" }).click();
      await page.waitForSelector("#cart-overlay");
      await page.locator(".checkout-btn").click();
      await page.waitForSelector("#checkout-form");
      await page.fill("#co-username", "alice");
      await page.locator("#checkout-form button[type=submit]").click();
      // payment was reset, so the order is accepted this time
      await page.waitForFunction(() => {
        const t = document.querySelector("#modal-overlay")?.textContent || "";
        return t.includes("Order #");
      }, undefined, { timeout: 7000 });
      const text = await page.locator("#modal-overlay").textContent();
      const bal = text.match(/Balance to pay: (.+)/);
      if (!bal) throw new Error("no balance");
      await page.locator("#modal-overlay button", { hasText: "New Order" }).click();
      await page.waitForTimeout(300);
      return `accepted, balance ${bal[1].trim()}`;
    });

    await step("customer: tab stays open without a due date (buy again while unpaid)", async () => {
      // Regression for the v1.0.13 due-date change: with no payment due date
      // configured, a customer with an unpaid balance must still be able to
      // add another order to their tab instead of getting a 403 block.
      await page.evaluate(() => localStorage.removeItem("kiosk_cart"));
      await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
      await page.waitForSelector(".product-card");
      await page.locator(".product-card", { hasText: "Chocolate Bar" }).first().locator(".add-btn").click();
      await page.locator(".cart-btn", { hasText: "Cart" }).click();
      await page.waitForSelector("#cart-overlay");
      await page.locator(".checkout-btn").click();
      await page.waitForSelector("#checkout-form");
      await page.fill("#co-username", "alice");
      await page.locator("#checkout-form button[type=submit]").click();
      await page.waitForFunction(() => {
        const t = document.querySelector("#modal-overlay")?.textContent || "";
        return t.includes("Order #");
      }, undefined, { timeout: 7000 });
      const text = await page.locator("#modal-overlay").textContent();
      const bal = text.match(/Balance to pay: (.+)/);
      if (!bal) throw new Error("no balance after stacked purchase");
      const amount = parseFloat(bal[1].replace(/[^\d,]/g, "").replace(",", "."));
      if (!(amount > 3.49)) throw new Error("tab did not stack: balance " + bal[1]);
      return `stacked, balance ${bal[1].trim()}`;
    });

    await step("customer: admin-enabled self-payment clears all unpaid orders", async () => {
      try {
        await setCustomerSelfServicePayment("true");
        await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
        await page.waitForSelector(".product-card");
        await page.locator("#lookup-btn").click();
        await page.waitForSelector("#lookup-form");
        await page.fill("#lk-username", "alice");
        await page.locator("#lookup-form button[type=submit]").click();
        await page.waitForSelector('[data-action="kiosk-mark-all-paid"]');
        await page.locator('[data-action="kiosk-mark-all-paid"]').click();
        await page.locator("#confirm-self-payment").click();
        await page.waitForFunction(() =>
          document.querySelector("#modal-overlay")?.textContent.includes("No outstanding balance")
        );
        return "all pending orders marked paid";
      } finally {
        await setCustomerSelfServicePayment("false");
      }
    });

    await step("admin: settings expose self-payment opt-in warning", async () => {
      await page.goto(`http://127.0.0.1:${PORT}/#admin/settings`, { waitUntil: "networkidle" });
      await page.waitForSelector("#s-customer_self_service_payment");
      const checkbox = page.locator("#s-customer_self_service_payment");
      if (await checkbox.isChecked()) throw new Error("self-payment should be disabled after test");
      const text = await page.locator("#admin-main-container").textContent();
      if (!text.includes("does not verify identity or payment")) {
        throw new Error("self-payment warning missing");
      }
      await checkbox.evaluate((el) => {
        el.checked = true;
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });
      await page.locator('[data-action="admin-save-settings"]').evaluate((el) => el.click());
      await page.waitForFunction(async () => {
        const response = await fetch("/api/settings");
        const settings = await response.json();
        return settings.customer_self_service_payment === "true";
      });
      await checkbox.evaluate((el) => {
        el.checked = false;
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });
      await page.locator('[data-action="admin-save-settings"]').evaluate((el) => el.click());
      await page.waitForFunction(async () => {
        const response = await fetch("/api/settings");
        const settings = await response.json();
        return settings.customer_self_service_payment === "false";
      });
      return "setting can be enabled and disabled with risk warning";
    });

    await step("customer: sees updated store name on fresh load", async () => {
      await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
      await page.waitForSelector(".product-card");
      const h = await page.locator(".kiosk-header h1").textContent();
      return h.trim();
    });

    await step("customer: product card shows uploaded image", async () => {
      const img = page.locator(".product-card", { hasText: "USB-C Cable" }).locator(".product-image img");
      const src = await img.getAttribute("src");
      if (!src || !src.startsWith("/api/images/")) throw new Error("no product image on card: " + src);
      return "card img " + src;
    });

    await step("customer: weekly special listed first with special price", async () => {
      const first = page.locator(".product-grid .product-card").first();
      const text = await first.textContent();
      if (!text.includes("USB-C Cable")) throw new Error("special not first: " + text.replace(/\s+/g, " "));
      if ((await first.locator(".weekly-badge").count()) !== 1) throw new Error("no weekly badge on card");
      const oldP = await first.locator(".price-old").textContent();
      const special = await first.locator(".price-special").textContent();
      if (!oldP.includes("9,99")) throw new Error("old price missing: " + oldP);
      if (!special.includes("5,00")) throw new Error("special price missing: " + special);
      return "special first: " + oldP + " → " + special;
    });

    // ---- 1.0.32: buy again, idle reset, restocks, margins, audit, system ----
    const freshKiosk = async () => {
      await page.evaluate(() => localStorage.removeItem("kiosk_cart"));
      await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
      await page.reload({ waitUntil: "networkidle" });
      await page.waitForSelector(".product-card");
    };

    await step("customer: lookup offers buy-again favorites that add to the cart", async () => {
      await freshKiosk();
      await page.evaluate(() => Kiosk.openLookup());
      await page.fill("#lk-username", "alice");
      await page.locator("#lookup-form button[type=submit]").click();
      await page.waitForSelector(".buy-again-btn", { timeout: 5000 });
      const names = await page.locator(".buy-again-name").allTextContents();
      if (!names.includes("USB-C Cable")) throw new Error("alice's purchase not offered: " + names.join(", "));
      await page.locator(".buy-again-btn", { hasText: "USB-C Cable" }).click();
      await page.waitForFunction(() => document.getElementById("buy-again-count")?.textContent === "1");
      const toast = await page.locator(".toast.success").last().textContent();
      if (!toast.includes("USB-C Cable added to cart")) throw new Error("no confirmation: " + toast);
      await page.locator('[data-action="kiosk-open-cart"]').click();
      await page.waitForSelector("#cart-overlay .cart-item");
      const item = await page.locator("#cart-overlay .cart-item-name").first().textContent();
      if (item.trim() !== "USB-C Cable") throw new Error("cart holds " + item);
      return `favorites: ${names.join(", ")}`;
    });

    await step("customer: idle kiosk warns, then clears the cart for the next person", async () => {
      await setSetting("kiosk_idle_seconds", "2");
      try {
        await freshKiosk();
        await page.locator(".product-card", { hasText: "Cola" }).first().locator(".add-btn").click();
        await page.waitForSelector("#idle-warning", { timeout: 6000 });
        await page.locator('#idle-warning [data-action="kiosk-idle-continue"]').click();
        await page.waitForSelector("#idle-warning", { state: "detached" });
        if ((await page.locator("#cart-count").textContent()).trim() !== "1") throw new Error("'I'm still here' lost the cart");
        await page.waitForSelector("#idle-warning", { timeout: 6000 });
        await page.waitForSelector("#idle-warning", { state: "detached", timeout: 15000 });
        const badge = (await page.locator("#cart-count").textContent()).trim();
        const stored = await page.evaluate(() => localStorage.getItem("kiosk_cart"));
        if (badge !== "0" || stored !== "[]") throw new Error(`cart survived reset: badge ${badge}, stored ${stored}`);
        const toast = await page.locator(".toast").last().textContent();
        if (!toast.includes("reset after inactivity")) throw new Error("no reset notice: " + toast);
        return "warned, kept on tap, then reset (cart cleared)";
      } finally {
        await setSetting("kiosk_idle_seconds", "90");
      }
    });

    const adminView = async (view, selector) => {
      await page.evaluate((v) => { location.hash = "#admin/" + v; }, view);
      await page.waitForSelector(selector, { timeout: 7000 });
    };
    // Exact name match: hasText alone would let "Cola" match "Chocolate Bar".
    const productRow = (name) =>
      page.locator("#products-table tbody tr").filter({ has: page.locator("td:nth-child(2)", { hasText: new RegExp(`^\\s*${name}\\b`) }) });
    const editProduct = async (name) => {
      await adminView("products", "#recent-restocks");
      await productRow(name).locator(".edit-product").click();
      await page.waitForSelector("#product-form");
    };

    await step("admin: per-product low-stock threshold puts it on the restock list", async () => {
      await page.evaluate(() => document.getElementById("cart-overlay")?.remove());
      await editProduct("Baseball Cap");
      await page.fill("#p-threshold", "20");
      await page.locator("#product-form button[type=submit]").click();
      await page.waitForSelector("#product-form", { state: "detached" });
      await adminView("dashboard", "#restock-needed");
      const row = page.locator("#restock-needed tr", { hasText: "Baseball Cap" });
      if ((await row.count()) !== 1) throw new Error("Baseball Cap not on the restock list");
      return (await row.textContent()).replace(/\s+/g, " ").trim();
    });

    await step("admin: restock records a delivery with purchase price", async () => {
      await page.locator("#restock-needed tr", { hasText: "Baseball Cap" }).locator('[data-action="admin-restock"]').click();
      await page.waitForSelector("#restock-form");
      await page.fill("#r-quantity", "10");
      await page.fill("#r-cost", "7.5");
      await page.fill("#r-note", "e2e delivery");
      await page.locator("#restock-form button[type=submit]").click();
      await page.waitForSelector(".toast.success >> text=Added 10 × Baseball Cap", { timeout: 5000 });
      await page.waitForFunction(() => !document.querySelector("#restock-needed")?.textContent.includes("Baseball Cap"));
      await adminView("products", "#recent-restocks");
      const row = (await productRow("Baseball Cap").textContent()).replace(/\s+/g, " ");
      if (!row.includes("7,50")) throw new Error("cost not shown: " + row);
      const delivery = await page.locator("#recent-restocks tr", { hasText: "e2e delivery" }).count();
      if (delivery !== 1) throw new Error("delivery missing from recent deliveries");
      return "stock topped up, cost 7,50 € recorded";
    });

    await step("admin: scheduled special stays off until its start date", async () => {
      const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
      await editProduct("Cola");
      await page.check("#p-weekly");
      await page.fill("#p-special-price", "0.99");
      await page.fill("#p-special-start", tomorrow);
      await page.locator("#product-form button[type=submit]").click();
      await page.waitForSelector("#product-form", { state: "detached" });
      await productRow("Cola").locator(".weekly-badge", { hasText: "Scheduled" }).waitFor({ timeout: 5000 });
      const cola = await page.evaluate(async () => {
        const res = await fetch("/api/products");
        return (await res.json()).find((p) => p.name === "Cola");
      });
      if (cola.special_active !== false || cola.cost_price !== null) {
        throw new Error("public product: " + JSON.stringify({ active: cola.special_active, cost: cola.cost_price }));
      }
      return `starts ${tomorrow}; inactive and cost hidden for the kiosk`;
    });

    await step("admin: margins panel reports paid sales against cost", async () => {
      await adminView("reports", "#margins-panel table");
      await page.locator('#margins-panel [data-period="all"]').click();
      await page.waitForSelector('#margins-panel [data-period="all"].btn-primary');
      const rows = await page.locator("#margins-panel tbody tr").count();
      const total = (await page.locator("#margins-panel tfoot").textContent()).replace(/\s+/g, " ").trim();
      if (rows === 0 || !total.includes("%")) throw new Error(`no margins: ${rows} rows, total ${total}`);
      return `${rows} product(s); ${total}`;
    });

    await step("admin: audit log records payments, edits and deliveries", async () => {
      await adminView("audit", "#audit-rows table");
      const actions = await page.locator("#audit-rows .audit-action").allTextContents();
      for (const expected of ["product.restock", "product.update", "customer.reset_payment", "settings.update"]) {
        if (!actions.includes(expected)) throw new Error(`missing ${expected}: ${[...new Set(actions)].join(", ")}`);
      }
      await page.selectOption("#audit-filter", "product.restock");
      await page.waitForFunction(() => {
        const cells = [...document.querySelectorAll("#audit-rows .audit-action")];
        return cells.length > 0 && cells.every((c) => c.textContent === "product.restock");
      });
      return `${actions.length} entries; filter works`;
    });

    await step("admin: system page shows health and takes a backup", async () => {
      await adminView("system", "#backups-panel");
      const db = (await page.locator(".stat-card", { hasText: "Database" }).textContent()).replace(/\s+/g, " ");
      if (!db.includes("sqlite")) throw new Error("database card: " + db);
      await page.locator('[data-action="admin-backup-now"]').click();
      await page.waitForSelector('#backups-panel [data-action="admin-backup-download"]', { timeout: 7000 });
      const name = await page.locator('#backups-panel [data-action="admin-backup-download"]').first().getAttribute("data-name");
      const [download] = await Promise.all([
        page.waitForEvent("download"),
        page.locator('#backups-panel [data-action="admin-backup-download"]').first().click(),
      ]);
      if (download.suggestedFilename() !== name) throw new Error("downloaded " + download.suggestedFilename());
      return `backup ${name} created and downloaded`;
    });

    await step("admin: settings expose idle reset and backup schedule", async () => {
      await adminView("settings", "#s-kiosk_idle_seconds");
      const values = await Promise.all(
        ["#s-kiosk_idle_seconds", "#s-backup_interval_hours", "#s-backup_keep"].map((s) => page.inputValue(s))
      );
      if (values.join(",") !== "90,24,7") throw new Error("unexpected defaults: " + values.join(","));
      if (await page.isChecked("#s-kiosk_barcode_scanning")) throw new Error("self-scanning should be off by default");
      return "idle 90 s, backup every 24 h, keep 7, self-scanning off";
    });

    // ---- 1.0.37: focus, Esc, customer PINs ----
    const activeId = () => page.evaluate(() => document.activeElement?.id || "");
    const buyFirstProduct = async (username) => {
      await page.locator(".product-card .add-btn").first().click();
      await page.locator(".cart-btn", { hasText: "Cart" }).click();
      await page.waitForSelector("#cart-overlay");
      await page.locator(".checkout-btn").click();
      await page.waitForSelector("#checkout-form");
      if ((await activeId()) !== "co-username") throw new Error("cursor not in the username field");
      await page.keyboard.type(username);
      await page.keyboard.press("Enter");
    };

    await step("customer: lookup puts the cursor in the username field; Esc closes it", async () => {
      await freshKiosk();
      await page.locator("#lookup-btn").click();
      await page.waitForSelector("#lookup-form");
      if ((await activeId()) !== "lk-username") throw new Error("cursor not in the lookup field");
      if (await page.locator("#cart-overlay").count()) throw new Error("User lookup also opened the cart");
      await page.keyboard.press("Escape");
      await page.waitForSelector("#modal-overlay", { state: "detached" });
      return "focused; no cart behind it; Esc closed the dialog";
    });

    await step("customer: Esc closes the order confirmation", async () => {
      await buyFirstProduct("pin_e2e");
      await page.waitForFunction(() => (document.querySelector("#modal-overlay")?.textContent || "").includes("Order #"));
      await page.keyboard.press("Escape");
      await page.waitForSelector("#modal-overlay", { state: "detached" });
      return "confirmation closed with Esc";
    });

    await step("customer: sets a PIN from the lookup", async () => {
      await page.evaluate(() => Kiosk.openLookup());
      await page.keyboard.type("pin_e2e");
      await page.keyboard.press("Enter");
      await page.locator('[data-action="kiosk-pin-setup"]', { hasText: "Set a PIN" }).click();
      await page.waitForSelector("#pin-form");
      if ((await activeId()) !== "pin-new") throw new Error("cursor not in the PIN field");
      await page.fill("#pin-new", "4826");
      await page.fill("#pin-repeat", "4826");
      await page.locator("#pin-form button[type=submit]").click();
      await page.waitForSelector('[data-action="kiosk-pin-setup"]:has-text("Change PIN")', { timeout: 7000 });
      await page.keyboard.press("Escape");
      return "PIN set; lookup now offers Change PIN";
    });

    await step("customer: a PIN is required to look up and to buy", async () => {
      await page.evaluate(() => Kiosk.openLookup());
      await page.keyboard.type("pin_e2e");
      await page.keyboard.press("Enter");
      await page.waitForSelector("#lk-pin-group:not([hidden])");
      if ((await activeId()) !== "lk-pin") throw new Error("cursor not in the lookup PIN field");
      await page.locator('#lk-pin-group [data-action="kiosk-forgot-pin"]').click();
      const help = await page.locator("#lk-pin-group .pin-forgot-help").textContent();
      if (!help.includes("Pay your outstanding balance") || !help.includes("tell the staff")) {
        throw new Error("forgot-PIN help missing: " + help);
      }
      await page.locator("#lk-pin").focus();
      await page.keyboard.type("1111");
      await page.keyboard.press("Enter");
      await page.waitForSelector(".toast.error >> text=Wrong PIN", { timeout: 5000 });
      await page.fill("#lk-pin", "4826");
      await page.keyboard.press("Enter");
      await page.waitForSelector(".balance-big", { timeout: 7000 });
      await page.keyboard.press("Escape");
      await page.waitForSelector("#modal-overlay", { state: "detached" });

      await buyFirstProduct("pin_e2e");
      await page.waitForSelector("#co-pin-group:not([hidden])", { timeout: 7000 });
      if ((await activeId()) !== "co-pin") throw new Error("cursor not in the checkout PIN field");
      await page.keyboard.type("4826");
      await page.keyboard.press("Enter");
      await page.waitForFunction(() => (document.querySelector("#modal-overlay")?.textContent || "").includes("Order #"));
      await page.keyboard.press("Escape");
      return "lookup and checkout asked for the PIN; wrong PIN rejected";
    });

    await step("admin: PIN reset waits until the balance is paid", async () => {
      await adminView("customers", "#admin-main-container table");
      const row = () => page.locator("tbody tr").filter({ has: page.locator("td:first-child", { hasText: /^\s*pin_e2e/ }) });
      if (!(await row().textContent()).includes("PIN")) throw new Error("no PIN badge");
      if (!(await row().locator('[data-action="admin-reset-pin"]').isDisabled())) throw new Error("reset allowed with unpaid balance");
      await row().locator(".reset-payment").click();
      await page.locator("#confirm-reset").click();
      await page.waitForFunction(() => {
        const btn = [...document.querySelectorAll('[data-action="admin-reset-pin"]')]
          .find((b) => b.closest("tr")?.textContent.includes("pin_e2e"));
        return btn && !btn.disabled;
      }, undefined, { timeout: 7000 });
      await row().locator('[data-action="admin-reset-pin"]').click();
      await page.locator("#confirm-reset-pin").click();
      await page.waitForSelector(".toast.success >> text=PIN removed for pin_e2e", { timeout: 5000 });
      await page.waitForFunction(() => ![...document.querySelectorAll("tbody tr")]
        .some((tr) => tr.textContent.includes("pin_e2e") && tr.textContent.includes("🔒")));
      return "reset blocked while unpaid, allowed after payment";
    });
  } catch (e) {
    results.push("FAIL  outer — " + e.message);
  }

  await browser.close();
  if (!backupDirExisted) fs.rmSync(BACKUP_DIR, { recursive: true, force: true });
  if (!pinPepperExisted) fs.rmSync(PIN_PEPPER, { force: true });
  server.close();
  backend.kill("SIGTERM");
  console.log("\n" + results.join("\n"));
  console.log("\nConsole/page errors:");
  console.log(errors.length ? errors.join("\n") : "(none)");
  // Steps that intentionally hit an error response: the overdue checkout block (403)
  // and the unknown-user lookup (404). Anything else is a real failure.
  const expectedErrors = [
    /status of 403 .*\/api\/orders\]$/,
    /status of 404 .*\/api\/customers\/ghost_user_x\]$/,
    // PIN steps: "PIN required" (428) and the deliberate wrong PIN (403).
    /status of 428 .*\/api\/(orders|customers\/pin_e2e)\]$/,
    /status of 403 .*\/api\/customers\/pin_e2e\]$/,
  ];
  const unexpected = errors.filter((e) => !expectedErrors.some((re) => re.test(e)));
  if (unexpected.length) {
    results.push("FAIL  unexpected console/page errors — " + unexpected.join(" | "));
    console.log("FAIL  unexpected console/page errors: " + unexpected.length);
  }
  const fails = results.filter((r) => r.startsWith("FAIL"));
  process.exit(fails.length ? 1 : 0);
});
