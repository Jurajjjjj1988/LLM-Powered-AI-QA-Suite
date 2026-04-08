```typescript
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

const VALID_CREDENTIALS = {
  email: 'testuser@example.com',
  password: 'ValidPassword123!'
};

const INVALID_CREDENTIALS = {
  email: 'invalid@example.com',
  password: 'WrongPassword123!'
};

test.describe('User Login Feature', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');
  });

  test.afterEach(async ({ page }) => {
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  });

  test.describe('Successful Login', () => {
    test('should return JWT token on valid credentials', async ({ page }) => {
      let responseBody: { token?: string } = {};

      page.on('response', async (response) => {
        if (response.url().includes('/api/auth/login') && response.status() === 200) {
          responseBody = await response.json();
        }
      });

      await page.fill('[data-testid="email-input"], input[type="email"], #email', VALID_CREDENTIALS.email);
      await page.fill('[data-testid="password-input"], input[type="password"], #password', VALID_CREDENTIALS.password);
      await page.click('[data-testid="login-button"], button[type="submit"], #login-btn');

      await page.waitForResponse(
        (response) => response.url().includes('/api/auth/login') && response.status() === 200,
        { timeout: 10000 }
      );

      expect(responseBody.token).toBeDefined();
      expect(typeof responseBody.token).toBe('string');
      expect(responseBody.token!.length).toBeGreaterThan(0);

      const tokenParts = responseBody.token!.split('.');
      expect(tokenParts.length).toBe(3);
    });

    test('should redirect to dashboard after successful login', async ({ page }) => {
      await page.fill('[data-testid="email-input"], input[type="email"], #email', VALID_CREDENTIALS.email);
      await page.fill('[data-testid="password-input"], input[type="password"], #password', VALID_CREDENTIALS.password);
      await page.click('[data-testid="login-button"], button[type="submit"], #login-btn');

      await page.waitForURL(/\/(dashboard|home|profile)/, { timeout: 10000 });
      expect(page.url()).not.toContain('/login');
    });

    test('should store JWT token in localStorage after successful login', async ({ page }) => {
      await page.fill('[data-testid="email-input"], input[type="email"], #email', VALID_CREDENTIALS.email);
      await page.fill('[data-testid="password-input"], input[type="password"], #password', VALID_CREDENTIALS.password);
      await page.click('[data-testid="login-button"], button[type="submit"], #login-btn');

      await page.waitForResponse(
        (response) => response.url().includes('/api/auth/login') && response.status() === 200,
        { timeout: 10000 }
      );

      const token = await page.evaluate(() => {
        return localStorage.getItem('token') || 
               localStorage.getItem('jwt') || 
               localStorage.getItem('authToken') ||
               sessionStorage.getItem('token');
      });

      expect(token).toBeTruthy();
    });
  });

  test.describe('Failed Login - Invalid Credentials', () => {
    test('should return 401 error on invalid credentials', async ({ page }) => {
      const responsePromise = page.waitForResponse(
        (response) => response.url().includes('/api/auth/login'),
        { timeout: 10000 }
      );

      await page.fill('[data-testid="email-input"], input[type="email"], #email', INVALID_CREDENTIALS.email);
      await page.fill('[data-testid="password-input"], input[type="password"], #password', INVALID_CREDENTIALS.password);
      await page.click('[data-testid="login-button"], button[type="submit"], #login-btn');

      const response = await responsePromise;
      expect(response.status()).toBe(401);
    });

    test('should display error message on invalid credentials', async ({ page }) => {
      await page.fill('[data-testid="email-input"], input[type="email"], #email', INVALID_CREDENTIALS.email);
      await page.fill('[data-testid="password-input"], input[type="password"], #password', INVALID_CREDENTIALS.password);
      await page.click('[data-testid="login-button"], button[type="submit"], #login-btn');

      const errorMessage = page.locator(
        '[data-testid="error-message"], .error-message, .alert-error, [role="alert"], .error'
      );
      await expect(errorMessage).toBeVisible({ timeout: 5000 });
      
      const errorText = await errorMessage.textContent();
      expect(errorText).toBeTruthy();
    });

    test('should remain on login page after failed login', async ({ page }) => {
      await page.fill('[data-testid="email-input"], input[type="email"], #email', INVALID_CREDENTIALS.email);
      await page.fill('[data-testid="password-input"], input[type="password"], #password', INVALID_CREDENTIALS.password);
      await page.click('[data-testid="login-button"], button[type="submit"], #login-btn');

      await page.waitForResponse(
        (response) => response.url().includes('/api/auth/login'),
        { timeout: 10000 }
      );

      expect(page.url()).toContain('/login');
    });

    test('should not store token in localStorage on failed login', async ({ page }) => {
      await page.fill('[data-testid="email-input"], input[type="email"], #email', INVALID_CREDENTIALS.email);
      await page.fill('[data-testid="password-input"], input[type="password"], #password', INVALID_CREDENTIALS.password);
      await page.click('[data-testid="login-button"], button[type="submit"], #login-btn');

      await page.waitForResponse(
        (response) => response.url().includes('/api/auth/login'),
        { timeout: 10000 }
      );

      const token = await page.evaluate(() => {
        return localStorage.getItem('token') || 
               localStorage.getItem('jwt') || 
               localStorage.getItem('authToken') ||
               sessionStorage.getItem('token');
      });

      expect(token).toBeNull();
    });
  });

  test.describe('Edge Cases', () => {
    test('should show validation error for empty email field', async ({ page }) => {
      await page.fill('[data-testid="password-input"], input[type="password"], #password', VALID_CREDENTIALS.password);
      await page.click('[data-testid="login-button"], button[type="submit"], #login-btn');

      const emailInput = page.locator('[data-testid="email-input"], input[type="email"], #email');
      
      const validationMessage = await emailInput.evaluate((el: HTMLInputElement) => el.validationMessage);
      const hasErrorClass = await emailInput.evaluate((el) => 
        el.classList.contains('error') || el.classList.contains('is-invalid')
      );
      
      const errorVisible = page.locator('[data-testid="email-error"], .email-error, #email-error');
      
      const hasValidation = validationMessage !== '' || 
                           hasErrorClass || 
                           await errorVisible.isVisible().catch(() => false);
      
      expect(hasValidation).toBeTruthy();