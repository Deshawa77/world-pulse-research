import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const frontendUrl = process.env.PLANETARY_FRONTEND_URL || "http://127.0.0.1:5174";
const backendUrl = process.env.PLANETARY_BACKEND_URL || "http://127.0.0.1:8002";
const screenshotPath = path.join(root, "monitoring", "planetary", "smoke", "planetary-console-smoke.png");
const headless = process.argv.includes("--headless");

async function loadPlaywright() {
  const localPackage = path.join(process.env.USERPROFILE || "", "AppData", "Local", "ms-playwright-go", "1.50.1", "package", "index.mjs");
  if (!existsSync(localPackage)) {
    throw new Error(`Playwright package not found at ${localPackage}`);
  }
  return import(pathToFileURL(localPackage).href);
}

async function registerUser() {
  const email = `smoke.planetary.${Date.now()}@example.com`;
  const response = await fetch(`${backendUrl}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: "Planetary Smoke",
      email,
      password: "SmokePass123!",
      user_type: "researcher",
    }),
  });
  if (!response.ok) {
    throw new Error(`register failed: ${response.status} ${await response.text()}`);
  }
  const payload = await response.json();
  if (!payload.access_token) {
    throw new Error("register response missing access_token");
  }
  return payload;
}

async function assertBackendReachable() {
  try {
    const response = await fetch(`${backendUrl}/health/live`, {
      headers: { "x-api-key": process.env.VITE_API_KEY || "super_secure_api_key" },
    });
    if (!response.ok) {
      throw new Error(`health check failed: ${response.status}`);
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(
      `backend listener unreachable at ${backendUrl}. Start the local stack with run_planetary_local_stack.bat or scripts/start_planetary_local_stack.ps1 first. Root cause: ${detail}`,
    );
  }
}

function ensure(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function waitForVisible(page, selector, timeoutMs = 60000) {
  const startedAt = Date.now();
  const locator = page.locator(selector).first();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      if (await locator.isVisible()) {
        return;
      }
    } catch {
      // Keep polling until the route settles.
    }
    await page.waitForTimeout(350);
  }
  throw new Error(`timed out waiting for visible selector: ${selector}`);
}

async function launchBrowser(chromium) {
  try {
    return await chromium.launch({ channel: "msedge", headless, args: ["--window-size=1540,1180"] });
  } catch {
    return chromium.launch({
      executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
      headless,
      args: ["--window-size=1540,1180"],
    });
  }
}

async function main() {
  const { chromium } = await loadPlaywright();
  await assertBackendReachable();
  const auth = await registerUser();
  mkdirSync(path.dirname(screenshotPath), { recursive: true });

  const browser = await launchBrowser(chromium);
  const context = await browser.newContext({ viewport: { width: 1540, height: 1180 } });
  await context.addInitScript(({ token, role, userType, name, email, apiUrl }) => {
    window.localStorage.setItem("token", token);
    window.localStorage.setItem("role", role || "user");
    window.localStorage.setItem("user_type", userType || "researcher");
    window.localStorage.setItem("name", name || "Planetary Smoke");
    window.localStorage.setItem("email", email || "");
    window.localStorage.setItem("wp_active_api_url", apiUrl);
    window.localStorage.setItem("wp_intro_seen_v3", "1");
  }, {
    token: auth.access_token,
    role: auth.role,
    userType: auth.user_type,
    name: auth.name,
    email: auth.email,
    apiUrl: backendUrl,
  });

  const page = await context.newPage();
  await page.goto(`${frontendUrl}/dashboard/planetary-intelligence`, { waitUntil: "domcontentloaded" });
  await page.waitForURL(/\/dashboard\/planetary-intelligence/);
  await waitForVisible(page, "text=Live planetary world map");
  await waitForVisible(page, ".planetary-console__hero-map-toolbar");
  await waitForVisible(page, ".planetary-console__hero-replay-slider");
  await waitForVisible(page, ".planetary-console__hero-globe-frame");

  const layerToggleCount = await page.locator(".planetary-console__toggle").count();
  ensure(layerToggleCount >= 6, `expected layered map controls, found ${layerToggleCount}`);

  const searchInput = page.locator(".planetary-console__hero-map-search input[type='search']").first();
  await searchInput.fill("Ukraine");
  await page.locator(".planetary-console__hero-map-search .planetary-link-button", { hasText: "Jump" }).click();
  await page.waitForTimeout(500);
  const noticeText = ((await page.locator(".planetary-console__notice").textContent()) || "").trim();
  ensure(noticeText.toLowerCase().includes("map focus moved"), "map jump notice missing");

  const timelineCards = page.locator(".planetary-timeline-card");
  const timelineCount = await timelineCards.count();
  ensure(timelineCount >= 1, "expected at least one fusion timeline card");
  await timelineCards.first().click();
  await page.waitForTimeout(350);
  const replayBadge = ((await page.locator(".planetary-badge", { hasText: "Replay active" }).first().textContent()) || "").trim();
  ensure(replayBadge.toLowerCase().includes("replay"), "replay badge did not activate");

  const corridorCards = page.locator("#planetary-network .planetary-list-card");
  const corridorCount = await corridorCards.count();
  ensure(corridorCount >= 1, "expected at least one corridor card");
  await corridorCards.first().click();
  await page.waitForTimeout(600);
  const drawerTitle = ((await page.locator(".planetary-console__drawer-header h3").textContent()) || "").trim();
  ensure(drawerTitle.length > 0, "corridor investigation drawer did not open");

  await page.screenshot({ path: screenshotPath, fullPage: true });
  await page.waitForTimeout(headless ? 0 : 1000);
  await browser.close();

  console.log(JSON.stringify({
    status: "ok",
    frontendUrl,
    backendUrl,
    screenshotPath,
    layerToggleCount,
    timelineCount,
    corridorCount,
    drawerTitle,
    noticeText,
    headless,
  }, null, 2));
}

main().catch((error) => {
  console.error(JSON.stringify({ status: "error", message: error instanceof Error ? error.message : String(error) }, null, 2));
  process.exit(1);
});
