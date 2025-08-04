// shared/auth.js - Complete Authentication System for HANU Dashboard
class HanuAuth {
  constructor() {
    // Use same origin as hosting page for API calls
    this.apiBase = (typeof window !== 'undefined' ? window.location.origin : '');
    this.callbacks = {
      onLogin: [],
      onLogout: [],
      onError: []
    };
    
    // Auto-restore token on page load
    this.restoreToken();
    
    console.log('🔐 HanuAuth initialized');
  }
  
  // ===== TOKEN MANAGEMENT =====
  
  // Save token to storage
  saveToken(token) {
    this.token = token;
    sessionStorage.setItem('HANU_AUTH_TOKEN', token);
    localStorage.setItem('HANU_AUTH_TOKEN', token);
    console.log('💾 Token saved to storage');
  }
  
  // Load token from storage
  loadToken() {
    return sessionStorage.getItem('HANU_AUTH_TOKEN') || 
           localStorage.getItem('HANU_AUTH_TOKEN') || 
           null;
  }
  
  // Restore token from storage
  restoreToken() {
    const stored = this.loadToken();
    if (stored) {
      this.token = stored;
      console.log('🔄 Token restored from storage');
    }
  }
  
  // Get current token (MISSING METHOD - this was causing the error)
  getToken() {
    return this.token;
  }
  
  // Clear token from storage
  clearToken() {
    this.token = null;
    sessionStorage.removeItem('HANU_AUTH_TOKEN');
    localStorage.removeItem('HANU_AUTH_TOKEN');
    console.log('🗑️ Token cleared from storage');
  }
  
  // ===== AUTHENTICATION METHODS =====
  
  // Get authentication headers
  getAuthHeaders() {
    if (!this.token) {
      console.warn('⚠️ No token available for auth headers');
      return {};
    }
    return {
      'Authorization': `Bearer ${this.token}`,
      'Content-Type': 'application/json'
    };
  }
  
  // Check if user is authenticated
  isAuthenticated() {
    const hasToken = !!this.token;
    console.log(`🔐 Authentication status: ${hasToken ? 'authenticated' : 'not authenticated'}`);
    return hasToken;
  }
  
  // Test if current token is valid
  async testAuth() {
    if (!this.token) {
      console.log('🔐 No token to test');
      return false;
    }
    
    try {
      console.log('🔍 Testing authentication...');
      const response = await fetch(`${this.apiBase}/api/status`, {
        headers: this.getAuthHeaders(),
        signal: AbortSignal.timeout(10000) // 10 second timeout
      });
      
      const isValid = response.ok;
      console.log(`🔐 Auth test result: ${isValid ? 'valid' : 'invalid'} (HTTP ${response.status})`);
      
      if (!isValid && response.status === 401) {
        // Token is invalid, clear it
        this.clearToken();
      }
      
      return isValid;
    } catch (error) {
      console.error('❌ Auth test failed:', error);
      return false;
    }
  }
  
  // Test authentication with a specific token
  async testAuthWithToken(token) {
    if (!token) {
      return false;
    }
    
    try {
      console.log('🔍 Testing provided token...');
      const response = await fetch(`${this.apiBase}/api/status`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        signal: AbortSignal.timeout(10000)
      });
      
      const isValid = response.ok;
      console.log(`🔐 Token test result: ${isValid ? 'valid' : 'invalid'} (HTTP ${response.status})`);
      return isValid;
    } catch (error) {
      console.error('❌ Token test failed:', error);
      return false;
    }
  }
  
  // Login with token or password
  async login(tokenOrPass) {
    if (!tokenOrPass || !tokenOrPass.trim()) {
      throw new Error('Authentication token or password is required');
    }
    let authToken = tokenOrPass.trim();
    console.log('🔐 Attempting login...');
    // If input contains no dots (likely raw password), request a token
    if (!authToken.includes('.')) {
      console.log('🔄 Password detected, requesting auth token from server...');
      const response = await fetch(`${this.apiBase}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: authToken })
      });
      const data = await response.json();
      if (!data.success || !data.token) {
        throw new Error(data.error || 'Invalid credentials');
      }
      authToken = data.token;
      console.log('✅ Received auth token from server');
    }
    // Test the token
    const isValid = await this.testAuthWithToken(authToken);
    if (!isValid) {
      throw new Error('Invalid authentication token. Please login again.');
    }
    // Save valid token
    this.saveToken(authToken);
    console.log('✅ Login successful');
    // Notify login callbacks
    this.callbacks.onLogin.forEach(callback => {
      try {
        callback(authToken);
      } catch (error) {
        console.error('❌ Login callback error:', error);
      }
    });
    return true;
  }

  /**
   * Blocks execution until the user is authenticated.
   * Sets up the authentication UI and waits for login.
   * @param {Object} options - Optional UI element IDs.
   * @returns {Promise<void>} Resolves when login is successful.
   */
  async requireLogin(options = {}) {
    // Initialize authentication UI
    this.setupAuthUI(options);
    // If already authenticated and valid, return immediately
    if (this.isAuthenticated() && await this.testAuth()) {
      return;
    }
    // Otherwise, wait for the login callback to resolve
    return new Promise(resolve => {
      this.onLogin(() => resolve());
    });
  }

  // Logout user
  logout() {
    console.log('🚪 Logging out...');
    
    const wasAuthenticated = this.isAuthenticated();
    this.clearToken();
    
    if (wasAuthenticated) {
      // Notify logout callbacks
      this.callbacks.onLogout.forEach(callback => {
        try {
          callback();
        } catch (error) {
          console.error('❌ Logout callback error:', error);
        }
      });
    }
    
    // Optionally reload the page to reset state
    setTimeout(() => {
      if (confirm('You have been logged out. Reload the page?')) {
        window.location.reload();
      }
    }, 500);
  }
  
  // ===== EVENT CALLBACKS =====
  
  // Add login callback
  onLogin(callback) {
    if (typeof callback === 'function') {
      this.callbacks.onLogin.push(callback);
      console.log('📝 Login callback registered');
    } else {
      console.error('❌ Login callback must be a function');
    }
  }
  
  // Add logout callback  
  onLogout(callback) {
    if (typeof callback === 'function') {
      this.callbacks.onLogout.push(callback);
      console.log('📝 Logout callback registered');
    } else {
      console.error('❌ Logout callback must be a function');
    }
  }
  
  // Add error callback
  onError(callback) {
    if (typeof callback === 'function') {
      this.callbacks.onError.push(callback);
      console.log('📝 Error callback registered');
    } else {
      console.error('❌ Error callback must be a function');
    }
  }
  
  // ===== UI MANAGEMENT =====
  
  // Setup authentication UI
  setupAuthUI(options = {}) {
    console.log('🎨 Setting up authentication UI...');
    
    const authSection = document.getElementById(options.authSectionId || 'auth-section');
    const mainContent = document.getElementById(options.mainContentId || 'main-content');
    const tokenInput = document.getElementById(options.tokenInputId || 'auth-token');
    const loginButton = document.getElementById(options.loginButtonId || 'login-button');
    const statusDiv = document.getElementById(options.statusId || 'auth-status');
    
    if (!authSection || !mainContent || !tokenInput || !loginButton) {
      console.error('❌ Required auth UI elements not found:', {
        authSection: !!authSection,
        mainContent: !!mainContent,
        tokenInput: !!tokenInput,
        loginButton: !!loginButton
      });
      return;
    }
    
    console.log('✅ Auth UI elements found');
    
    // Restore token to input if available
    if (this.token) {
      tokenInput.value = this.token;
    }
    
    // Show authentication status
    const showStatus = (message, type = 'info') => {
      if (statusDiv) {
        statusDiv.textContent = message;
        statusDiv.className = `auth-status ${type}`;
        console.log(`📊 Auth status: ${message}`);
      }
    };
    
    // Login button handler
    const handleLogin = async () => {
      const token = tokenInput.value.trim();
      
      if (!token) {
        showStatus('❌ Please enter your AUTH_TOKEN', 'error');
        tokenInput.focus();
        return;
      }
      
      // Disable button during login
      loginButton.disabled = true;
      loginButton.textContent = 'Authenticating...';
      showStatus('⏳ Verifying authentication token...', 'info');
      
      try {
        await this.login(token);
        
        showStatus('✅ Authentication successful!', 'success');
        
        // Hide auth section and show main content
        setTimeout(() => {
          authSection.classList.add('hidden');
          mainContent.classList.remove('hidden');
        }, 1000);
        
      } catch (error) {
        showStatus(`❌ ${error.message}`, 'error');
        console.error('❌ Login failed:', error);
        
        // Trigger error callbacks
        this.callbacks.onError.forEach(callback => {
          try {
            callback(error);
          } catch (callbackError) {
            console.error('❌ Error callback failed:', callbackError);
          }
        });
        
        // Clear invalid token from input
        if (error.message.includes('Invalid')) {
          tokenInput.value = '';
          tokenInput.focus();
        }
      } finally {
        // Re-enable button
        loginButton.disabled = false;
        loginButton.textContent = 'Login';
      }
    };
    
    // Attach event listeners
    loginButton.addEventListener('click', handleLogin);
    
    // Enter key support
    tokenInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && !loginButton.disabled) {
        handleLogin();
      }
    });
    
    // Focus on token input
    tokenInput.focus();
    
    // Auto-login if token exists and page just loaded
    if (this.token && !sessionStorage.getItem('HANU_AUTH_TESTED')) {
      sessionStorage.setItem('HANU_AUTH_TESTED', 'true');
      
      showStatus('⏳ Checking saved authentication...', 'info');
      
      this.testAuth().then(isValid => {
        if (isValid) {
          console.log('✅ Auto-login successful');
          showStatus('✅ Welcome back!', 'success');
          
          setTimeout(() => {
            authSection.classList.add('hidden');
            mainContent.classList.remove('hidden');
          }, 1000);
          
          // Trigger login callbacks
          this.callbacks.onLogin.forEach(callback => {
            try {
              callback(this.token);
            } catch (error) {
              console.error('❌ Auto-login callback error:', error);
            }
          });
        } else {
          console.log('❌ Auto-login failed - token invalid');
          showStatus('🔑 Please log in', 'info');
          this.clearToken();
          tokenInput.value = '';
          tokenInput.focus();
        }
      }).catch(error => {
        console.error('❌ Auto-login test failed:', error);
        showStatus('🔑 Please log in', 'info');
        this.clearToken();
        tokenInput.value = '';
        tokenInput.focus();
      });
    } else if (!this.token) {
      showStatus('🔑 Please enter your authentication token', 'info');
    }
    
    console.log('✅ Auth UI setup complete');
  }
  
  // ===== UTILITY METHODS =====
  
  // Make authenticated API request
  async apiRequest(endpoint, options = {}) {
    if (!this.isAuthenticated()) {
      throw new Error('Authentication required');
    }
    
    const url = endpoint.startsWith('http') ? endpoint : `${this.apiBase}${endpoint}`;
    
    const requestOptions = {
      ...options,
      headers: {
        ...this.getAuthHeaders(),
        ...options.headers
      }
    };
    
    console.log(`🌐 API Request: ${options.method || 'GET'} ${url}`);
    
    try {
      const response = await fetch(url, requestOptions);
      
      if (response.status === 401) {
        console.error('❌ API request unauthorized - clearing token');
        this.clearToken();
        throw new Error('Authentication expired. Please log in again.');
      }
      
      if (!response.ok) {
        throw new Error(`API request failed: HTTP ${response.status}`);
      }
      
      return response;
    } catch (error) {
      console.error('❌ API request failed:', error);
      throw error;
    }
  }
  
  // Get user info (if available)
  async getUserInfo() {
    try {
      const response = await this.apiRequest('/api/status');
      return await response.json();
    } catch (error) {
      console.error('❌ Failed to get user info:', error);
      return null;
    }
  }
  
  // Check if token will expire soon (if your API supports this)
  isTokenExpiringSoon() {
    // This would need to be implemented based on your token structure
    // For now, just return false
    return false;
  }
  
  // Refresh token (if your API supports this)
  async refreshToken() {
    // This would need to be implemented based on your API
    console.log('🔄 Token refresh not implemented');
    return false;
  }
  
  // ===== DEBUG METHODS =====
  
  // Get debug info
  getDebugInfo() {
    return {
      hasToken: !!this.token,
      tokenLength: this.token ? this.token.length : 0,
      isAuthenticated: this.isAuthenticated(),
      apiBase: this.apiBase,
      callbackCounts: {
        onLogin: this.callbacks.onLogin.length,
        onLogout: this.callbacks.onLogout.length,
        onError: this.callbacks.onError.length
      },
      storageCheck: {
        session: !!sessionStorage.getItem('HANU_AUTH_TOKEN'),
        local: !!localStorage.getItem('HANU_AUTH_TOKEN')
      }
    };
  }
  
  // Log debug info
  logDebugInfo() {
    console.table(this.getDebugInfo());
  }
}

// Create and export singleton instance
const HanuAuthInstance = new HanuAuth();

// Make available globally for non-module scripts
if (typeof window !== 'undefined') {
  window.HanuAuth = HanuAuthInstance;
}

// Export for ES6 modules
export default HanuAuthInstance;
