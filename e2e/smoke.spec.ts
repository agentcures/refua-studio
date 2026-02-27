import { expect, test } from "@playwright/test";

import { bootStudio } from "./helpers";

test("loads mission control dashboard", async ({ page }) => {
  await bootStudio(page);

  await expect(page.getByRole("heading", { name: "Platform" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jobs" })).toBeVisible();
  await expect(page.locator("#widgetToolsOnline")).toHaveText(/\d+/);
  await expect.poll(async () => page.locator("#jobsBody tr").count()).toBeGreaterThan(0);
});
