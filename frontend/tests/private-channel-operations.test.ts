import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
const adminSource = await readFile(
  new URL("../src/pages/Admin.tsx", import.meta.url),
  "utf8"
);
const pageSource = await readFile(
  new URL("../src/pages/PrivateChannelOperations.tsx", import.meta.url),
  "utf8"
);
const apiSource = await readFile(
  new URL("../src/api/privateChannelOperations.ts", import.meta.url),
  "utf8"
);
const routePolicySource = await readFile(
  new URL("../src/routing/routePolicy.ts", import.meta.url),
  "utf8"
);

test("private channel operations frontend is not an active route in CLI-only launch", () => {
  assert.doesNotMatch(appSource, /path="\/admin\/private-channel-operations"/);
  assert.doesNotMatch(appSource, /<AdminRoute>/);
  assert.doesNotMatch(appSource, /<PrivateChannelOperations \/>/);
  assert.equal(routePolicySource.includes('"/admin/login"'), false);
  assert.match(adminSource, /to="\/admin\/private-channel-operations"/);
  assert.match(adminSource, /Private Channel Operations/);
  assert.doesNotMatch(appSource, /path="\/private-channel-operations"/);
});

test("operations API client uses read-only protected endpoints only", () => {
  assert.match(apiSource, /\/admin\/private-channel-operations\/overview/);
  assert.match(
    apiSource,
    /\/admin\/private-channel-operations\/channel-configuration/
  );
  assert.match(apiSource, /client\.get<PrivateChannelOperationsOverview>/);
  assert.match(apiSource, /client\.get<PrivateChannelConfigurationResponse>/);
  assert.doesNotMatch(apiSource, /client\.(post|patch|put|delete)/);
  assert.doesNotMatch(apiSource, /retry|backfill|process-due|invite|stripe/i);
});

test("operations page renders required read-only dashboard states", () => {
  assert.match(pageSource, /Private Channel Operations/);
  assert.match(pageSource, /Channel readiness/);
  assert.match(pageSource, /Credentials configured/);
  assert.match(pageSource, /Credentials missing/);
  assert.match(pageSource, /Pending access deliveries/);
  assert.match(pageSource, /Retryable access deliveries/);
  assert.match(pageSource, /Terminal access-delivery failures/);
  assert.match(pageSource, /Pending signal publications/);
  assert.match(pageSource, /Retryable signal publications/);
  assert.match(pageSource, /Terminal signal-publication failures/);
  assert.match(pageSource, /Approved signals/);
  assert.match(pageSource, /Draft signals/);
  assert.match(pageSource, /Loading operations status/);
  assert.match(pageSource, /role="alert"/);
  assert.match(pageSource, /No private channels are configured yet/);
  assert.match(pageSource, /read-only in this slice/);
  assert.match(pageSource, /No automatic scheduler/);
});

test("operations page supports pagination and disabled loading controls", () => {
  assert.match(pageSource, /afterChannelId: cursor/);
  assert.match(pageSource, /setCursor\(null\)/);
  assert.match(pageSource, /channelQuery\.data\?\.has_more/);
  assert.match(pageSource, /setCursor\(channelQuery\.data\?\.next_cursor/);
  assert.match(pageSource, /disabled=\{isFetching\}/);
  assert.match(pageSource, /disabled=\{channelQuery\.isFetching\}/);
  assert.doesNotMatch(pageSource, /while\s*\(|for\s*\(.*has_more/s);
});

test("operations frontend remains provider-neutral and does not expose sensitive fields", () => {
  const prohibitedProviderName = ["Tele", "gram"].join("");
  const prohibitedPattern = new RegExp(prohibitedProviderName, "i");
  const combined = [appSource, adminSource, pageSource, apiSource].join("\n");
  const newOperationsSurface = [pageSource, apiSource].join("\n");
  assert.doesNotMatch(combined, prohibitedPattern);
  assert.doesNotMatch(
    newOperationsSurface,
    /\bbot\b|token|chat_id|raw provider|invitation URL|subscriber email|stripe_/i
  );
  assert.doesNotMatch(pageSource, /retry-publication|retry-fulfillment|process-due|run-due/i);
});
