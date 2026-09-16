import assert from "node:assert/strict";
import test from "node:test";

import { parseBooleanFlag } from "../src/config/features.ts";
import { loadPublicResource } from "../src/data/publicData.ts";
import {
  LEGACY_CUSTOMER_ROUTES,
  PUBLIC_ROUTES,
  resolveRoutePolicy,
} from "../src/routing/routePolicy.ts";


test("legacy customer feature defaults to disabled and parses safe true values", () => {
  assert.equal(parseBooleanFlag(undefined), false);
  assert.equal(parseBooleanFlag(""), false);
  assert.equal(parseBooleanFlag("false"), false);
  assert.equal(parseBooleanFlag("0"), false);

  for (const value of ["1", "true", "TRUE", " yes ", "on"]) {
    assert.equal(parseBooleanFlag(value), true);
  }
});


test("public routes remain public even when an old JWT exists", () => {
  for (const route of PUBLIC_ROUTES) {
    assert.equal(resolveRoutePolicy(route, false, true), "public");
  }
});


test("legacy routes redirect home while disabled", () => {
  for (const route of LEGACY_CUSTOMER_ROUTES) {
    assert.equal(resolveRoutePolicy(route, false), "redirect-home");
  }
});


test("legacy routes stay redirected even if the old feature flag is set", () => {
  for (const route of LEGACY_CUSTOMER_ROUTES) {
    assert.equal(resolveRoutePolicy(route, true), "redirect-home");
  }
});


test("frontend admin routes are inactive in the CLI-only launch slice", () => {
  assert.equal(resolveRoutePolicy("/admin", false), "redirect-home");
  assert.equal(resolveRoutePolicy("/admin/login", false), "redirect-home");
  assert.equal(
    resolveRoutePolicy("/admin/private-channel-operations", false),
    "redirect-home"
  );
  assert.equal(
    resolveRoutePolicy("/admin/private-channel-operations", true),
    "redirect-home"
  );
});


test("failed optional public data loads resolve to null", async () => {
  const result = await loadPublicResource(async () => {
    throw new Error("market data unavailable");
  });

  assert.equal(result, null);
});
