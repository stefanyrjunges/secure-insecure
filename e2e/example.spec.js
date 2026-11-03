// @ts-check
import { test, expect } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const password = 'playwright-test-password';

function uniqueAccount(label) {
  const id = randomUUID();
  return {
    displayName: `Playwright ${label} ${id.slice(0, 8)}`,
    email: `playwright-${id}@example.com`,
  };
}

async function registerAccount(page, account) {
  await page.goto('/register');
  await page.getByLabel('Display name').fill(account.displayName);
  await page.getByLabel('Email').fill(account.email);
  await page.getByLabel(/Password/).fill(password);
  await page.getByRole('button', { name: 'Register' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(
    page.getByText('Your account has been created. You can now log in.'),
  ).toBeVisible();
}

async function signIn(page, email, userPassword = password, expectSuccess = true) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(userPassword);
  await page.getByRole('button', { name: 'Log in' }).click();
  if (expectSuccess) {
    await expect(page).toHaveURL(/\/dashboard$/);
  } else {
    await expect(page.getByText('The email or password is incorrect.')).toBeVisible();
  }
}

function promoteAccount(email) {
  const result = spawnSync(
    'python',
    ['-m', 'flask', '--app', 'app', 'make-admin', email],
    {
      cwd: process.cwd(),
      encoding: 'utf8',
      env: {
        ...process.env,
        DATABASE_PATH: resolve('database/playwright.db'),
        SECRET_KEY: 'playwright-test-secret-key',
      },
    },
  );
  expect(result.error).toBeUndefined();
  return result;
}

test('login page links to account registration', async ({ page }) => {
  await page.goto('/login');

  await expect(page).toHaveTitle('Log in');
  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible();
  await page.getByRole('link', { name: 'Create an account' }).click();
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.getByRole('heading', { name: 'Create an account' })).toBeVisible();
});

test('UC-1: a visitor can register once with valid details', async ({ page }) => {
  const account = uniqueAccount('Registration');
  await registerAccount(page, account);

  await page.goto('/register');
  await page.getByLabel('Display name').fill(account.displayName);
  await page.getByLabel('Email').fill(account.email);
  await page.getByLabel(/Password/).fill(password);
  await page.getByRole('button', { name: 'Register' }).click();
  await expect(
    page.getByText('An account with that email address already exists.'),
  ).toBeVisible();
});

test('UC-2: a registered user can sign in and invalid credentials are rejected', async ({ page }) => {
  const account = uniqueAccount('Login');
  await registerAccount(page, account);

  await signIn(page, account.email);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText(`Welcome, ${account.displayName}.`)).toBeVisible();

  await page.getByRole('button', { name: 'Log out' }).click();
  await signIn(page, account.email, 'wrong-playwright-password', false);
  await expect(page).toHaveURL(/\/login$/);
});

test('UC-3: a user can update and reload their profile', async ({ page }) => {
  const account = uniqueAccount('Profile');
  const biography = 'A synthetic biography for the Playwright test.';
  await registerAccount(page, account);
  await signIn(page, account.email);

  await page.goto('/profile');
  await page.getByLabel('Display name').fill(`${account.displayName} Updated`);
  await page.getByLabel(/Biography/).fill(biography);
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByText('Your profile has been updated.')).toBeVisible();
  await page.reload();

  await expect(page.getByLabel('Display name')).toHaveValue(`${account.displayName} Updated`);
  await expect(page.getByLabel(/Biography/)).toHaveValue(biography);
});

test('UC-4: signing out clears access to protected pages', async ({ page }) => {
  const account = uniqueAccount('Logout');
  await registerAccount(page, account);
  await signIn(page, account.email);

  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/\/login$/);
});

test('UC-5: only administrators can search accounts', async ({ page, browser }) => {
  const administrator = uniqueAccount('Admin');
  const target = uniqueAccount('Search target');
  await registerAccount(page, administrator);
  const targetPage = await browser.newPage();
  await registerAccount(targetPage, target);
  await signIn(targetPage, target.email);
  await targetPage.goto('/profile');
  await targetPage.getByLabel('Display name').fill(target.displayName);
  await targetPage.getByLabel(/Biography/).fill('Private synthetic profile details.');
  await targetPage.getByRole('button', { name: 'Save profile' }).click();
  await targetPage.close();

  const promotion = promoteAccount(administrator.email);
  expect(promotion.status, promotion.stderr).toBe(0);
  await signIn(page, administrator.email);

  await page.goto('/admin/users');
  await page.getByLabel('Search by email or display name').fill(target.email);
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByText(target.displayName)).toBeVisible();
  await expect(page.getByText(target.email)).toBeVisible();
  await expect(page.getByText('No users found.')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Private synthetic profile details.');
  await expect(page.locator('body')).not.toContainText(password);

  await page.getByLabel('Search by email or display name').fill(target.displayName);
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByText(target.email)).toBeVisible();

  await page.getByLabel('Search by email or display name').fill('no-such-playwright-user');
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByText('No users found.')).toBeVisible();
});

test('UC-5: a regular user is denied access to account management', async ({ page }) => {
  const account = uniqueAccount('Non-admin');
  await registerAccount(page, account);
  await signIn(page, account.email);

  const response = await page.goto('/admin/users');
  expect(response?.status()).toBe(403);
});

test('UC-6: an administrator can disable and re-enable another account', async ({ page, browser }) => {
  const administrator = uniqueAccount('Status admin');
  const target = uniqueAccount('Status target');
  await registerAccount(page, administrator);
  const targetPage = await browser.newPage();
  await registerAccount(targetPage, target);
  await targetPage.close();

  const promotion = promoteAccount(administrator.email);
  expect(promotion.status, promotion.stderr).toBe(0);
  await signIn(page, administrator.email);
  await page.goto(`/admin/users?search=${encodeURIComponent(target.email)}`);
  const targetRow = page.getByRole('listitem').filter({ hasText: target.email });

  await targetRow.getByRole('button', { name: 'Disable account' }).click();
  await expect(page.getByText('The account status has been updated.')).toBeVisible();
  await expect(targetRow).toContainText('Disabled');

  const targetBrowser = await browser.newContext();
  const disabledPage = await targetBrowser.newPage();
  await signIn(disabledPage, target.email, password, false);

  await targetRow.getByRole('button', { name: 'Enable account' }).click();
  await expect(targetRow).toContainText('Active');
  await signIn(disabledPage, target.email);
  await expect(disabledPage).toHaveURL(/\/dashboard$/);

  await targetBrowser.close();
});

test('UC-7: the CLI promotes an existing account and rejects an unknown email', async ({ page }) => {
  const account = uniqueAccount('Promotion');
  await registerAccount(page, account);

  const promotion = promoteAccount(account.email);
  expect(promotion.status, promotion.stderr).toBe(0);
  expect(promotion.stdout).toContain('Administrator role granted.');

  await signIn(page, account.email);
  await expect(page.getByRole('link', { name: 'Manage users' })).toBeVisible();

  const unknown = promoteAccount(`missing-${randomUUID()}@example.com`);
  expect(unknown.status).not.toBe(0);
  expect(unknown.stderr).toContain('No account found with that email address.');
});
