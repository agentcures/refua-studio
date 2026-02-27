import { expect, test } from "@playwright/test";

import { bootStudio, expectResultOutputContains, uniqueId } from "./helpers";

test("upserts program and evaluates stage gate", async ({ page }) => {
  await bootStudio(page);

  const programId = uniqueId("e2e-program");
  await page.fill("#programIdInput", programId);
  await page.fill("#programNameInput", "Playwright Program");
  await page.fill("#programStageInput", "lead_optimization");
  await page.fill("#programIndicationInput", "Oncology");
  await page.fill("#programOwnerInput", "qa-team");

  await page.click("#upsertProgramButton");
  await expectResultOutputContains(page, "Program Upserted");
  await expect(page.locator("#programSummaryOutput")).toContainText(programId);

  await page.click("#loadGateTemplateDefaultsButton");
  await expect.poll(async () => page.locator("#gateCriteriaChecklist .gate-criterion").count()).toBeGreaterThan(0);

  await page.click("#evaluateProgramGateButton");
  await expectResultOutputContains(page, "Program Loaded");
  await expect(page.locator("#programSummaryOutput")).toContainText('"template_id"');
  await expect(page.locator("#programSummaryOutput")).toContainText('"events_count": 1');

  await page.click("#approveProgramButton");
  await expectResultOutputContains(page, "Program Loaded");
  await expect(page.locator("#programSummaryOutput")).toContainText('"approvals_count": 2');

  await expect.poll(async () => page.locator("#programEventTimeline .timeline-item").count()).toBeGreaterThan(1);
});
