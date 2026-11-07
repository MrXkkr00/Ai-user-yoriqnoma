// Order E2E (Playwright TS): create an order, then cancel it.
import { expect, test } from "@playwright/test";

test("buyurtma berish va bekor qilish", async ({ page }) => {
  await page.goto("/app/orders/new");
  await page.getByLabel("Mahsulot").selectOption("2");
  await page.getByLabel("Miqdor").fill("2");
  await page.getByLabel("Yetkazish manzili").fill("Toshkent, Yunusobod 4-17");
  await page.getByLabel("Telefon raqami").fill("+998901112233");
  await page.getByRole("button", { name: "Buyurtma berish" }).click();
  await expect(page).toHaveURL(/\/app\/orders\/\d+/);
  await page.getByRole("button", { name: "Bekor qilish" }).click();
  await page.getByRole("button", { name: "Ha, bekor qilish" }).click();
  await expect(page.getByText("Bekor qilingan")).toBeVisible();
});
