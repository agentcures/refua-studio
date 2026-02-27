import { expect, test } from "@playwright/test";

import { bootStudio, uniqueId } from "./helpers";

test("creates trial, enrolls patient, and records outcome", async ({ page }) => {
  await bootStudio(page);

  const trialId = uniqueId("e2e-trial");
  const patientId = uniqueId("patient");

  await page.fill("#clinicalTrialIdInput", trialId);
  await page.fill(
    "#clinicalTrialConfigInput",
    JSON.stringify(
      {
        replicates: 4,
        enrollment: { total_n: 24 },
        adaptive: { burn_in_n: 8, interim_every: 8 },
      },
      null,
      2
    )
  );

  await page.click("#addClinicalTrialButton");
  await expect(page.locator("#resultOutput")).toContainText("Clinical Trial Detail", { timeout: 30_000 });

  await page.click("#loadClinicalTrialButton");
  await expect(page.locator("#resultOutput")).toContainText("Clinical Trial Detail", { timeout: 30_000 });
  await expect(page.locator("#clinicalTrialSummary")).toContainText(trialId);

  await page.fill(
    "#clinicalPatientInput",
    JSON.stringify(
      {
        patient_id: patientId,
        source: "human",
        arm_id: "control",
        demographics: { age: 55, weight: 74 },
        baseline: { endpoint_value: 42.3 },
      },
      null,
      2
    )
  );
  await page.click("#enrollClinicalPatientButton");
  await expect(page.locator("#clinicalTrialSummary")).toContainText(patientId, { timeout: 30_000 });

  await page.fill(
    "#clinicalResultInput",
    JSON.stringify(
      {
        patient_id: patientId,
        result_type: "endpoint",
        visit: "week-4",
        source: "human",
        values: {
          arm_id: "control",
          change: 1.7,
          responder: true,
          safety_event: false,
        },
      },
      null,
      2
    )
  );
  await page.click("#addClinicalResultButton");
  await expect(page.locator("#clinicalTrialSummary")).toContainText('"result_count": 1', { timeout: 30_000 });
});
