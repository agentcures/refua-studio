import { expect, Page } from "@playwright/test";

export async function bootStudio(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Refua Studio" })).toBeVisible();
  await expect(page.locator("#connectionChip"))
    .toHaveClass(/online/, { timeout: 30_000 });
  await expect.poll(async () => page.locator("#commandCenterCapabilities .command-cap").count(), {
    timeout: 30_000,
  }).toBe(4);
  await expect
    .poll(async () => page.locator("#gateTemplateSelect option").count(), {
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
