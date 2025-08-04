// docs/shared/auth-boot.js
import HanuAuth from './auth.js';

/**
 * Wait for DOM load, then block until user logs in.
 * Shows the little “Enter authentication token” banner automatically.
 */
async function bootAuth() {
  // Wait for DOM to be ready
  if (document.readyState === 'loading') {
    await new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve));
  }
  // Now setup auth and require login
  await HanuAuth.requireLogin();
}

bootAuth();
