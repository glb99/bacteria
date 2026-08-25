/**
 * Points at a server that is already running, deliberately.
 *
 * Starting one here would test a process nobody is looking at. The defects this
 * exists for are found while a person is using the console, so the check drives
 * the same instance they are — `just e2e` brings up the server if it is down.
 */
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  // Above the 5s default: signing in exchanges a key, and the console then
  // fetches the graph and its conclusions before a tab can be asserted on. Under
  // a run of several files that reliably passed 5s, and the failure read as
  // "#workspace is hidden" -- a rendering bug that was a timeout.
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env["BACTERIA_URL"] ?? "http://127.0.0.1:8000",
    // On by default: the failures here are visual and sequential, and a trace is
    // the difference between "the click did nothing" and knowing which listener
    // ran.
    trace: "retain-on-failure",
  },
  reporter: [["list"]],
});
