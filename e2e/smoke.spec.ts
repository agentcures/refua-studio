import { expect, test } from "@playwright/test";

import { bootStudio } from "./helpers";

test("loads the core campaign workspace", async ({ page }) => {
  await bootStudio(page);

  await expect(page.getByRole("button", { name: "Promising Drugs" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Campaign" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Responses" })).toBeVisible();
  await expect(page.locator("#objectiveInput")).toHaveValue(/Find cures for all diseases/i);
  await expect(page.locator("#jobsCountSummary")).toContainText("running:");
});
