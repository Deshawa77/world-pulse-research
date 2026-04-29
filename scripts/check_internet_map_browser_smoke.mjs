import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const frontendUrl = process.env.INTERNET_MAP_FRONTEND_URL || "http://127.0.0.1:5173";
const backendUrl = process.env.INTERNET_MAP_BACKEND_URL || "http://127.0.0.1:8000";
const screenshotPath = path.join(root, "monitoring", "internet_map", "smoke", "internet-map-smoke.png");
const headless = process.argv.includes("--headless") ? true : false;

async function loadPlaywright() {
  const localPackage = path.join(process.env.USERPROFILE || "", "AppData", "Local", "ms-playwright-go", "1.50.1", "package", "index.mjs");
  if (!existsSync(localPackage)) {
    throw new Error(`Playwright package not found at ${localPackage}`);
  }
  return import(pathToFileURL(localPackage).href);
}

async function registerUser() {
  const email = `smoke.internet.map.${Date.now()}@example.com`;
  const response = await fetch(`${backendUrl}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: "Internet Smoke",
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

function ensure(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function launchBrowser(chromium) {
  try {
    return await chromium.launch({ channel: "msedge", headless, args: ["--window-size=1440,1100"] });
  } catch {
    return chromium.launch({
      executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
      headless,
      args: ["--window-size=1440,1100"],
    });
  }
}

async function main() {
  const { chromium } = await loadPlaywright();
  const auth = await registerUser();
  mkdirSync(path.dirname(screenshotPath), { recursive: true });

  const browser = await launchBrowser(chromium);
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  await context.addInitScript(({ token, role, userType, name, email, apiUrl }) => {
    window.localStorage.setItem("token", token);
    window.localStorage.setItem("role", role || "user");
    window.localStorage.setItem("user_type", userType || "researcher");
    window.localStorage.setItem("name", name || "Internet Smoke");
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
  await page.goto(`${frontendUrl}/internet-map`, { waitUntil: "domcontentloaded" });
  await page.waitForURL(/\/internet-map/);
  await page.waitForSelector("text=REAL-TIME");
  await page.waitForSelector("text=Packet-flow visualization");
  await page.waitForSelector("text=Delivery and persistence");
  await page.waitForSelector(".internet-map-country-card");

  const firstCountryCard = page.locator(".internet-map-country-card").first();
  const selectedLabel = (await firstCountryCard.locator("strong").first().textContent())?.trim() || "";
  await firstCountryCard.click();
  await page.waitForTimeout(500);
  const focusHeading = (await page.locator(".internet-map-focus-panel h3").textContent())?.trim() || "";
  ensure(Boolean(focusHeading), "country focus heading missing");
  ensure(!selectedLabel || focusHeading.toLowerCase().includes(selectedLabel.toLowerCase()), `country focus did not update to ${selectedLabel}`);

  const ackButton = page.locator(".internet-map-action-buttons button", { hasText: "Ack" }).first();
  await ackButton.click();
  await page.waitForTimeout(800);
  const assignButton = page.locator(".internet-map-action-buttons button", { hasText: "Assign Me" }).first();
  await assignButton.click();
  await page.waitForTimeout(800);
  const falsePositiveButton = page.locator(".internet-map-action-buttons button", { hasText: "False Positive" }).first();
  await falsePositiveButton.click();
  await page.waitForTimeout(1000);
  const noticeText = (await page.locator(".internet-map-notice").textContent())?.trim() || "";
  ensure(noticeText.length > 0, "operator action notice missing after acknowledgement");

  const sourceCards = await page.locator(".internet-map-source-card").count();
  const replayCards = await page.locator(".internet-map-replay-card").count();
  const eventCards = await page.locator(".internet-map-event-card").count();
  ensure(sourceCards >= 4, `expected at least 4 source cards, found ${sourceCards}`);
  ensure(replayCards >= 1, `expected replay cards, found ${replayCards}`);
  ensure(eventCards >= 1, `expected threat event cards, found ${eventCards}`);

  const replayButton = page.locator(".internet-map-replay-button").first();
  await replayButton.click();
  await page.waitForTimeout(600);
  const stageStatusReplay = ((await page.locator(".internet-map-stage-status-row").textContent()) || "").trim();
  ensure(stageStatusReplay.toLowerCase().includes("replay"), "stage did not enter replay mode");

  const attackFilterButton = page.locator(".internet-map-stage-pill", { hasText: "Attack" }).first();
  await attackFilterButton.click();
  await page.waitForTimeout(350);
  const activeFilterClass = await attackFilterButton.getAttribute("class");
  ensure(String(activeFilterClass || "").includes("is-active"), "attack filter did not activate");

  const corridorButton = page.locator(".internet-map-corridor-row").first();
  await corridorButton.click();
  await page.waitForTimeout(500);
  const stageStatusPinned = ((await page.locator(".internet-map-stage-status-row").textContent()) || "").trim();
  ensure(stageStatusPinned.toLowerCase().includes("pinned corridor"), "corridor pinning did not update stage status");

  const liveButton = page.locator(".internet-map-stage-pill", { hasText: "Live" }).first();
  await liveButton.click();
  await page.waitForTimeout(400);

  await page.screenshot({ path: screenshotPath, fullPage: true });
  await page.waitForTimeout(headless ? 0 : 1200);
  await browser.close();

  console.log(JSON.stringify({
    status: "ok",
    frontendUrl,
    backendUrl,
    screenshotPath,
    sourceCards,
    replayCards,
    eventCards,
    focusedCountry: focusHeading,
    noticeText,
    headless,
  }, null, 2));
}

main().catch((error) => {
  console.error(JSON.stringify({ status: "error", message: error instanceof Error ? error.message : String(error) }, null, 2));
  process.exit(1);
});

