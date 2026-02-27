import { expect, test } from "@playwright/test";

import { bootStudio, expectResultOutputContains } from "./helpers";

test("validates plan and submits run job", async ({ page }) => {
  await bootStudio(page);

  // Keep run request decoupled from command-center program linkage.
  await page.fill("#programIdInput", "");
  await page.locator("#dryRunToggle").check();
  await page.click("#validatePlanButton");
  await expectResultOutputContains(page, "Plan Validation");

  await page.click("#runButton");
  await expect
    .poll(async () => (await page.locator("#resultOutput").textContent()) || "", {
      timeout: 30_000,
    })
    .toMatch(/Run Submitted|Selected Job/);

  await page.click("#refreshJobsButton");
  await expect.poll(async () => page.locator("#jobsBody tr").count()).toBeGreaterThan(0);

  const firstRow = page.locator("#jobsBody tr").first();
  await firstRow.click();
  await expectResultOutputContains(page, "Selected Job");
});
