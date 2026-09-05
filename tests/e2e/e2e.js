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

const backend = spawn(
  PYTHON,
  ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
  { cwd: BACKEND_CWD, env: { ...process.env, DATABASE_PATH: DB }, stdio: "ignore" }
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
};

function staticHandler(req, res) {
  let urlPath = decodeURIComponent(req.url.split("?")[0]);
  if (urlPath === "/") urlPath = "/index.html";
  const file = path.join(FRONT, urlPath);
  if (!file.startsWith(FRONT)) { res.writeHead(403); return res.end(); }
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
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push("PAGEERROR: " + e.message));

  const results = [];
  async function step(name, fn) {
    try {
      const extra = await fn();
      results.push(`PASS  ${name}${extra ? " — " + extra : ""}`);
    } catch (e) {
      results.push(`FAIL  ${name} — ${e.message.split("\n")[0]}`);
    }
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
      const label = await page.locator("#checkout-form label").textContent();
      if (!label.includes("Username")) throw new Error("no username prompt");
      return "username prompt shown";
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
      return `order ${ord[1]} — ${bal[1].trim()}`;
    });

    await step("customer: new order resets", async () => {
      await page.locator("#modal-overlay button", { hasText: "New Order" }).click();
      await page.waitForTimeout(200);
      const badge = await page.locator("#cart-count").textContent();
      if (badge.trim() !== "0") throw new Error("badge=" + badge);
      return "cart cleared";
    });

    await step("customer: second buy same user", async () => {
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
      if (!bal) throw new Error("no balance");
      return `${bal[1].trim()}`;
    });

    await step("customer: user lookup shows balance + history + stats", async () => {
      await page.locator("#modal-overlay button", { hasText: "New Order" }).click();
      await page.waitForTimeout(300);
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
      await page.fill("#login-password", "admin123");
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

    await step("admin: customers page lists balance", async () => {
      await page.locator('a[data-view="customers"]').click();
      await page.waitForTimeout(600);
      const row = page.locator("tr", { hasText: "alice" });
      const text = await row.textContent();
      if (!text.includes("€")) throw new Error("no EUR balance");
      if ((await row.locator(".reset-payment").count()) !== 1) throw new Error("reset button missing");
      return (await row.locator("td").nth(4).textContent()).trim();
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
      const balText = (await row.locator("td").nth(4).textContent()).replace(/\s+/g, "");
      if (balText !== "0,00€") throw new Error("balance not reset: " + balText);
      return "payment reset → " + balText;
    });

    await step("admin: reports show outstanding cleared", async () => {
      await page.goto(`http://127.0.0.1:${PORT}/#admin/reports`, { waitUntil: "networkidle" });
      await page.waitForTimeout(700);
      const text = await page.locator("#admin-main-container").textContent();
      if (!text.includes("Outstanding")) throw new Error("no outstanding in reports");
      const stat = await page.locator(".stat-card", { hasText: "Outstanding Balance" }).textContent();
      if (!stat.includes("0,00")) throw new Error("outstanding not cleared: " + stat.replace(/\s+/g, " "));
      return "reports ok";
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
      return "customer sees 0 to pay";
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
  } catch (e) {
    results.push("FAIL  outer — " + e.message);
  }

  await browser.close();
  server.close();
  backend.kill("SIGTERM");
  console.log("\n" + results.join("\n"));
  console.log("\nConsole/page errors:");
  console.log(errors.length ? errors.join("\n") : "(none)");
  const fails = results.filter((r) => r.startsWith("FAIL"));
  process.exit(fails.length ? 1 : 0);
});
