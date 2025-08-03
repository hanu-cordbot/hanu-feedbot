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
  // Auto-login via password if provided
  if (window.DEFAULT_AUTH_BASE && window.DEFAULT_AUTH_PASSWORD) {
    try {
      const response = await fetch(`${window.DEFAULT_AUTH_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: window.DEFAULT_AUTH_PASSWORD })
      });
      const data = await response.json();
      if (data.success && data.token) {
        HanuAuth.saveToken(data.token);
        console.log('✅ auth-boot auto-login: token saved');
      }
    } catch (err) {
      console.warn('⚠️ auth-boot auto-login failed:', err);
    }
  }
  // Now setup auth and require login (skips UI if token valid)
  await HanuAuth.requireLogin();
}

bootAuth();
