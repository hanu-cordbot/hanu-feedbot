// API wrapper for HANU Dashboard - Complete Implementation
import HanuAuth from './auth.js';

class HanuAPI {
  constructor() {
    this.baseUrl = 'https://hanu-cordbot.snacky496.workers.dev';
    this.railwayUrl = 'https://web-production-b0a5.up.railway.app';
  }

  // Get authentication headers
  getHeaders() {
    const headers = {
      'Content-Type': 'application/json'
    };

    // Add authorization if available
    try {
      if (HanuAuth && HanuAuth.getToken && HanuAuth.getToken()) {
        headers['Authorization'] = `Bearer ${HanuAuth.getToken()}`;
      }
    } catch (error) {
      console.warn('Could not get auth token:', error);
    }

    return headers;
  }

  // Generic request method with comprehensive error handling
  async request(endpoint, options = {}) {
    // Determine if this should go to Railway or Cloudflare Worker by matching path without query
    const pathOnly = endpoint.split('?')[0];
    const railwayEndpoints = [
      '/run', '/health', '/get-current-prompt', '/save-current-prompt',
      '/test-gemini', '/test-entries', '/all-feeds', '/random-entry', '/test-discord'
    ];
    // Force /test-entries with query to be routed to Railway as well
    // Determine railway calls by path or full URL
    const isRailwayEndpoint = endpoint.startsWith(this.railwayUrl)
      || endpoint.startsWith('/test-entries')
      || railwayEndpoints.includes(pathOnly);
    const baseUrl = isRailwayEndpoint ? this.railwayUrl : this.baseUrl;
    const url = endpoint.startsWith('http') ? endpoint : `${baseUrl}${endpoint}`;
    
    const config = {
      headers: this.getHeaders(),
      ...options
    };

    // Handle request body
    if (options.body && typeof options.body === 'object') {
      config.body = JSON.stringify(options.body);
    }

    // Add Railway-specific headers for certain endpoints
    if (isRailwayEndpoint && HanuAuth.getToken()) {
      config.headers['X-Auth'] = HanuAuth.getToken();
    }

    try {
      console.log(`🌐 API Request: ${options.method || 'GET'} ${url}`);
      
      const response = await fetch(url, config);
      
      // Handle authentication errors
      if (response.status === 401) {
        console.error('❌ Authentication failed');
        if (HanuAuth && HanuAuth.logout) {
          HanuAuth.logout();
        }
        throw new Error('Authentication expired. Please login again.');
      }

      // Handle other HTTP errors
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`❌ API Error ${response.status}:`, errorText);
        throw new Error(`HTTP ${response.status}: ${errorText || response.statusText}`);
      }

      // Parse response based on content type
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        const data = await response.json();
        console.log(`✅ API Success: ${url}`, data);
        return data;
      } else {
        const text = await response.text();
        console.log(`✅ API Success: ${url}`, text);
        return text;
      }

    } catch (error) {
      console.error(`❌ API request failed: ${endpoint}`, error);
      throw error;
    }
  }

  // HTTP method helpers
  async get(endpoint) {
    return this.request(endpoint, { method: 'GET' });
  }

  async post(endpoint, body = null) {
    return this.request(endpoint, {
      method: 'POST',
      body
    });
  }

  async put(endpoint, body = null) {
    return this.request(endpoint, {
      method: 'PUT',
      body
    });
  }

  async delete(endpoint, body = null) {
    return this.request(endpoint, {
      method: 'DELETE',
      body
    });
  }

  // ===== SYSTEM STATUS & HEALTH =====
  // Get overall system status
  async getSystemStatus() {
    try {
      return await this.get('/api/status');
    } catch (error) {
      console.warn('System status endpoint not available:', error);
      return { status: 'unknown' };
    }
  }

  // Fetch diagnostic logs as recent activity
  async getDiagnostics() {
    try {
      return await this.get('/api/diagnostics');
    } catch (error) {
      console.warn('Diagnostics endpoint not available:', error);
      return [];
    }
  }

  async getPublicStats() {
    try {
      const url = `${this.baseUrl}/api/public/stats`;
      const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.warn('Public stats endpoint not available:', error);
      // Provide defaults matching expected fields
      return { feedCount: 0, feeds: [], activeFeedCount: 0, uptime: 0 };
    }
  }


  // ===== RECENT ACTIVITY LOGS =====

  async getActivityLogs() {
    // Use diagnostics endpoint and wrap in array for activity list
    try {
      const diag = await this.getDiagnostics();
      return Array.isArray(diag) ? diag : [diag];
    } catch (error) {
      console.warn('Unable to load diagnostics for activity logs:', error);
      return [];
    }
  }

  // ===== FEED MANAGEMENT =====

  async getFeeds() {
    return this.get('/api/feeds');
  }

  async addFeed(feedUrl) {
    if (!feedUrl || !feedUrl.trim()) {
      throw new Error('Feed URL is required');
    }
    return this.post('/api/feeds', { feedUrl: feedUrl.trim() });
  }

  async removeFeed(feedUrl) {
    if (!feedUrl) {
      throw new Error('Feed URL is required');
    }
    return this.delete('/api/feeds', { feedUrl });
  }

  async updateFeedMapping(feedUrl, channelId) {
    return this.post('/api/feed-mappings', { 
      feedUrl, 
      channelId: channelId || null 
    });
  }

  async updateFeedGroup(feedUrl, groupName) {
    return this.post('/api/feed-groups', { 
      feedUrl, 
      groupName: groupName || null 
    });
  }

  async getFeedPerformance() {
    try {
      return await this.get('/api/stats/feeds');
    } catch (error) {
      console.warn('Feed performance endpoint not available');
      return { feeds: [] };
    }
  }

  // ===== CHANNEL MANAGEMENT =====

  async getChannels() {
    return this.get('/api/channels');
  }

  async addChannel(channelId) {
    if (!channelId || !channelId.trim()) {
      throw new Error('Channel ID is required');
    }
    
    // Validate Discord channel ID format
    const cleanId = channelId.trim();
    if (!/^\d{17,20}$/.test(cleanId)) {
      throw new Error('Invalid Discord channel ID format (should be 17-20 digits)');
    }
    
    return this.post('/api/channels', { channelId: cleanId });
  }

  async removeChannel(channelId) {
    if (!channelId) {
      throw new Error('Channel ID is required');
    }
    return this.delete('/api/channels', { channelId });
  }

  async fetchChannelName(channelId) {
    if (!channelId) {
      throw new Error('Channel ID is required');
    }
    try {
      return await this.post('/api/channels/fetch-name', { channelId });
    } catch (error) {
      console.warn('Channel name fetch failed:', error);
      return { success: false, error: error.message };
    }
  }

  async getChannelStats() {
    try {
      return await this.get('/api/stats/channels');
    } catch (error) {
      console.warn('Channel stats endpoint not available');
      return { channels: [] };
    }
  }

  // ===== GROUP MANAGEMENT =====

  async getGroups() {
    return this.get('/api/groups');
  }

  async addGroup(groupName) {
    if (!groupName || !groupName.trim()) {
      throw new Error('Group name is required');
    }
    return this.post('/api/groups', { groupName: groupName.trim() });
  }

  async renameGroup(oldName, newName) {
    if (!oldName || !newName) {
      throw new Error('Both old and new group names are required');
    }
    if (oldName.trim() === newName.trim()) {
      throw new Error('New name must be different from old name');
    }
    return this.put('/api/groups', { 
      oldName: oldName.trim(), 
      newName: newName.trim() 
    });
  }

  async removeGroup(groupName) {
    if (!groupName) {
      throw new Error('Group name is required');
    }
    // Use URL parameter format as expected by the worker
    return this.delete(`/api/groups?name=${encodeURIComponent(groupName)}`);
  }

  // ===== PROMPT MANAGEMENT =====

  async getSystemPrompt() {
    return this.get('/get-current-prompt'); // Railway endpoint
  }

  async updateSystemPrompt(sections) {
    if (!sections || !Array.isArray(sections)) {
      throw new Error('Sections array is required');
    }
    return this.post('/save-current-prompt', { sections }); // Railway endpoint
  }

  async testPrompt(content) {
    try {
      return await this.post('/api/prompt/test', { content });
    } catch (error) {
      console.warn('Prompt test endpoint not available');
      return { success: false, error: error.message };
    }
  }

  async testRandomPrompt(config) {
    try {
      return await this.post('/api/prompt/test-random', config);
    } catch (error) {
      console.warn('Random prompt test endpoint not available');
      return { success: false, error: error.message };
    }
  }

  // ===== BOT CONTROL & TESTING =====

  async runBot() {
    return this.post('/run'); // Railway endpoint
  }

  async testGemini(promptData) {
    return this.post('/test-gemini', promptData); // Railway endpoint
  }

  async getTestEntries(feedUrl = null) {
    // Explicitly call Railway test-entries endpoint with X-Auth
    const path = feedUrl ? `/test-entries?feed=${encodeURIComponent(feedUrl)}` : '/test-entries';
    const url = `${this.railwayUrl}${path}`;
    const token = HanuAuth.getToken();
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-Auth': token
      }
    });
    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errText}`);
    }
    return await response.json();
  }

  async getRandomEntry() {
    return this.get('/random-entry'); // Railway endpoint
  }

  async getAllFeeds() {
    return this.get('/all-feeds'); // Railway endpoint
  }

  async testDiscord(channelId, content, entry = {}) {
    if (!channelId || !content) {
      throw new Error('Channel ID and content are required');
    }
    return this.post('/test-discord', { // Railway endpoint
      channel_id: channelId,
      content: content,
      entry: entry
    });
  }

  // ===== CACHE & DATA MANAGEMENT =====

  async clearCache() {
    try {
      return await this.delete('/api/cache');
    } catch (error) {
      console.warn('Clear cache endpoint not available');
      return { success: false, error: error.message };
    }
  }

  async resetSeenData() {
    try {
      return await this.post('/api/reset-seen');
    } catch (error) {
      console.warn('Reset seen data endpoint not available');
      return { success: false, error: error.message };
    }
  }

  async exportData() {
    try {
      return await this.get('/api/export');
    } catch (error) {
      console.warn('Export data endpoint not available');
      return { success: false, error: error.message };
    }
  }

  // ===== SETTINGS MANAGEMENT =====

  async getSettings() {
    try {
      return await this.get('/api/settings');
    } catch (error) {
      console.warn('Settings endpoint not available, returning defaults');
      return {
        maxAgeHours: 168,
        skipUnmappedFeeds: true,
        continueParsingAll: true
      };
    }
  }

  async updateSettings(settings) {
    if (!settings || typeof settings !== 'object') {
      throw new Error('Settings object is required');
    }
    try {
      return await this.post('/api/settings', { settings });
    } catch (error) {
      console.warn('Update settings endpoint not available');
      return { success: false, error: error.message };
    }
  }

  // ===== PUBLIC ENDPOINTS (No Auth Required) =====

  async getPublicFeeds() {
    try {
      const url = `${this.baseUrl}/api/public/feeds`;
      const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.warn('Public feeds endpoint not available');
      return { feeds: [] };
    }
  }

  async getPublicStats() {
    try {
      const url = `${this.baseUrl}/api/public/stats`;
      const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.warn('Public stats endpoint not available:', error);
      // Provide defaults for dashboard overview
      return { feedCount: 0, feeds: [], activeFeedCount: 0, uptime: 0 };
    }
  }
  // Note: real activity logs via diagnostics
  async getActivityLogs() {
    try {
      const diag = await this.getDiagnostics();
      return Array.isArray(diag) ? diag : [diag];
    } catch (error) {
      console.warn('Unable to load diagnostics for activity logs:', error);
      return [];
    }
  }
  // ===== UTILITY METHODS =====

  async healthCheck() {
    try {
      const [workerHealth, railwayHealth] = await Promise.allSettled([
        fetch(`${this.baseUrl}/health`),
        fetch(`${this.railwayUrl}/health`)
      ]);

      return {
        worker: {
          status: workerHealth.status === 'fulfilled' && workerHealth.value.ok ? 'healthy' : 'unhealthy',
          response: workerHealth.status === 'fulfilled' ? workerHealth.value.status : 'error'
        },
        railway: {
          status: railwayHealth.status === 'fulfilled' && railwayHealth.value.ok ? 'healthy' : 'unhealthy',
          response: railwayHealth.status === 'fulfilled' ? railwayHealth.value.status : 'error'
        }
      };
    } catch (error) {
      return {
        worker: { status: 'error', response: error.message },
        railway: { status: 'error', response: error.message }
      };
    }
  }

  async ping() {
    const start = Date.now();
    try {
      await this.get('/health');
      return {
        success: true,
        latency: Date.now() - start,
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      return {
        success: false,
        latency: Date.now() - start,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  // ===== DEBUG METHODS =====

  getDebugInfo() {
    return {
      baseUrl: this.baseUrl,
      railwayUrl: this.railwayUrl,
      hasAuth: !!HanuAuth,
      hasToken: !!(HanuAuth && HanuAuth.getToken && HanuAuth.getToken()),
      headers: this.getHeaders()
    };
  }

  logDebugInfo() {
    console.table(this.getDebugInfo());
  }
}

// Create singleton instance
const HanuAPIInstance = new HanuAPI();

// Make available globally for non-module scripts
if (typeof window !== 'undefined') {
  window.HanuAPI = HanuAPIInstance;
}

// Export for ES6 modules
export default HanuAPIInstance;


export async function runBotTest(authToken, feedUrl = '') {
  // Use the railway proxy /run endpoint to trigger a random post test
  // If feedUrl is empty, will trigger a random post; if channelId is provided, will send to that channel
  const url = `${HanuAPIInstance.railwayUrl}/run`;
  let headers = {
    'Content-Type': 'application/json',
    'X-Auth': authToken,
    'X-Test-Mode': '1',
    'X-Skip-Filters': '1'
  };
  if (feedUrl) headers['X-Test-Feed'] = feedUrl;
  // Accept third arg for channel
  if (arguments.length > 2 && arguments[2]) headers['X-Test-Channel'] = arguments[2];
  return fetch(url, {
    method: 'POST',
    headers
  });
}
