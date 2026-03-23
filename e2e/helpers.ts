import { expect, Page } from "@playwright/test";

export async function bootStudio(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "ClawCures UI" })).toBeVisible();
  await expect(page.locator("#connectionChip"))
    .toHaveClass(/online/, { timeout: 30_000 });
  await expect
    .poll(async () => page.locator("#objectiveTemplateSelect option").count(), {
      timeout: 30_000,
    })
    .toBeGreaterThan(0);
  await expect(page.getByRole("heading", { name: "Campaign" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jobs" })).toBeVisible();
}

export async function expectResultOutputContains(page: Page, text: string): Promise<void> {
  await expect(page.locator("#resultOutput")).toContainText(text, { timeout: 30_000 });
}

export function uniqueId(prefix: string): string {
  const stamp = Date.now();
  const rand = Math.floor(Math.random() * 1_000_000);
  return `${prefix}-${stamp}-${rand}`;
}
