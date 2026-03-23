import { expect, test } from "@playwright/test";

import { bootStudio } from "./helpers";

test("filters promising drugs and opens the information card", async ({ page }) => {
  await bootStudio(page);

  await page.click("#promisingDrugsViewButton");
  await expect(page.getByRole("heading", { name: "Promising Drugs" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Therapeutic Library" })).toBeVisible();
  await expect(page.locator("#promisingDrugsSummary")).toContainText("tracked");

  await expect(page.locator("#drugCards .drug-card")).toHaveCount(2);

  await page.fill("#drugSearchInput", "lumatrol");
  await expect(page.locator("#drugCards .drug-card")).toHaveCount(1);
  await expect(page.locator("#drugCards")).toContainText("Lumatrol");

  await page.selectOption("#drugPromisingFilter", "promising");
  await page.selectOption("#drugTargetFilter", "KRAS G12D");
  await page.selectOption("#drugToolFilter", "refua_admet_profile");

  const candidateCard = page.locator("#drugCards .drug-card").first();
  await candidateCard.click();

  await expect(page.locator("#drugDetail")).toContainText("Lumatrol");
  await expect(page.locator("#drugDetail")).toContainText("KRAS G12D");
  await expect(page.locator("#drugDetail")).toContainText(
    "ADMET profile remains favorable after cross-check."
  );

  await page.click("#clearDrugFiltersButton");
  await page.selectOption("#drugPromisingFilter", "watchlist");
  await expect(page.locator("#drugCards")).toContainText("Heliomab");
  await expect(page.locator("#drugCards")).not.toContainText("Lumatrol");
});
