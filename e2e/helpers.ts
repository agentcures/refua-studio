import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, Page } from "@playwright/test";

export async function bootStudio(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "ClawCures UI" })).toBeVisible();
  await expect(page.locator("#connectionChip"))
    .toHaveClass(/online/, { timeout: 30_000 });
  await expect.poll(async () => page.getByTestId("agent-card").count(), {
    timeout: 30_000,
  }).toBeGreaterThan(0);
  await expect
    .poll(async () => page.locator("#objectiveTemplateSelect option").count(), {
      timeout: 30_000,
    })
    .toBeGreaterThan(0);
}

export async function expectResultOutputContains(page: Page, text: string): Promise<void> {
  await expect(page.locator("#resultOutput")).toContainText(text, { timeout: 30_000 });
}

export function uniqueId(prefix: string): string {
  const stamp = Date.now();
  const rand = Math.floor(Math.random() * 1_000_000);
  return `${prefix}-${stamp}-${rand}`;
}

export function seedPromisingDrugJob(): void {
  const repoRoot = process.cwd();
  const pythonBin = path.resolve(repoRoot, ".venv_release/bin/python");
  const dataDir = path.resolve(repoRoot, ".playwright-data");

  const payload = {
    promising_cures: [
      {
        cure_id: "refua_fold:kras-prime",
        name: "KRAS Prime",
        smiles: "CCN(CC)CC",
        target: "KRAS G12D",
        tool: "refua_fold",
        score: 92.4,
        promising: true,
        assessment: "promising safety profile with favorable developability",
        metrics: {
          binding_probability: 0.94,
          admet_score: 0.88,
          affinity: -11.2,
          ic50: 0.08,
          kd: 0.11,
        },
        admet: {
          status: "success",
          key_metrics: {
            admet_score: 0.88,
            safety_score: 0.91,
            adme_score: 0.85,
          },
          properties: {
            "results[0].predictions.hERG": 0.08,
            "results[0].predictions.AMES": 0.05,
            "results[0].predictions.clearance": 0.41,
          },
        },
      },
      {
        cure_id: "refua_affinity:egfr-shield",
        name: "EGFR Shield",
        smiles: "COc1ccc(NC(=O)N2CCN(CC2)C)cc1",
        target: "EGFR L858R",
        tool: "refua_affinity",
        score: 78.2,
        promising: true,
        assessment: "good binding profile with acceptable liabilities",
        metrics: {
          binding_probability: 0.81,
          admet_score: 0.69,
          affinity: -9.4,
          kd: 0.42,
        },
        admet: {
          status: "success",
          key_metrics: {
            admet_score: 0.69,
            safety_score: 0.74,
          },
          properties: {
            "results[0].predictions.hERG": 0.18,
            "results[0].predictions.AMES": 0.1,
            "results[0].predictions.solubility": 0.63,
          },
        },
      },
    ],
    results: [],
  };

  const script = `
from pathlib import Path
import json
import os

from clawcures_ui.storage import JobStore

store = JobStore(Path(os.environ["STUDIO_DATA_DIR"]) / "studio.db")
job = store.create_job(
    kind="candidate-run",
    request={"objective": "Playwright discovery fixture"},
)
store.set_running(job["job_id"])
store.set_completed(job["job_id"], json.loads(os.environ["PROMISING_JOB_PAYLOAD"]))
print(job["job_id"])
`;

  execFileSync(pythonBin, ["-"], {
    cwd: repoRoot,
    env: {
      ...process.env,
      PYTHONPATH: "src",
      STUDIO_DATA_DIR: dataDir,
      PROMISING_JOB_PAYLOAD: JSON.stringify(payload),
    },
    input: script,
    encoding: "utf-8",
  });
}
