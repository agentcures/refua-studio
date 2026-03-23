import { expect, test } from "@playwright/test";

import { bootStudio } from "./helpers";

test("loads the core campaign workspace", async ({ page }) => {
  await bootStudio(page);

  await expect(page.getByRole("heading", { name: "Stack Health" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Responses" })).toBeVisible();
  await expect(page.locator("#defaultObjectiveText")).not.toHaveText("Loading...");
  await expect(page.locator("#productGrid .product-card").first()).toBeVisible();
  await expect(page.locator("#jobsCountSummary")).toContainText("running:");
});
