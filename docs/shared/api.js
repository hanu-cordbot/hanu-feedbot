// API wrapper for HANU Dashboard - Complete Implementation
import HanuAuth from './auth.js';

class HanuAPI {
  constructor() {
    // Use GitHub API directly for all operations
    this.baseUrl = 'https://api.github.com';
    this.githubRepo = 'hanu-cordbot/hanu-feedbot';
    this.localDataEnabled = window.CONFIG?.DATA_SYNC?.enabled || false;
    this.localDataPath = window.CONFIG?.DATA_SYNC?.localDataPath || './data/';
  }

  // Smart data loading: try local first, then Railway API
  async loadDataSmart(endpoint, localFile = null) {
    // If we're on GitHub Pages and have local data enabled
    if (this.localDataEnabled && localFile) {
      try {
        console.log(`📁 Trying local data: ${this.localDataPath}${localFile}`);
        const localUrl = `${this.localDataPath}${localFile}`;
        const response = await fetch(localUrl);
        
        if (response.ok) {
          const data = await response.json();
          console.log(`✅ Loaded local data from ${localFile}`);
          return data;
        }
      } catch (error) {
        console.warn(`⚠️ Local data failed for ${localFile}:`, error);
      }
    }

    // Fallback to Railway API
    console.log(`🚂 Falling back to Railway API: ${endpoint}`);
    return this.request(`${this.railwayAPI}${endpoint}`);
  }

  // Get authentication headers for GitHub API
  getHeaders() {
    const headers = {
      'Accept': 'application/vnd.github.v3+json'
    };

    // Add GitHub token if available
    try {
      if (HanuAuth && HanuAuth.getToken && HanuAuth.getToken()) {
        headers['Authorization'] = `Bearer ${HanuAuth.getToken()}`;
      }
    } catch (error) {
      console.warn('Could not get GitHub token:', error);
    }

    return headers;
  }

  // Generic request method
  async request(endpoint, options = {}) {
    // Always use baseUrl defined by hosting page origin
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    
    const config = {
      headers: this.getHeaders(),
      ...options
    };

    // Handle request body
    if (options.body && typeof options.body === 'object') {
      config.body = JSON.stringify(options.body);
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
    // Return mock status for GitHub Pages
    return {
      status: 'ok',
      uptime: 0,
      version: 'GitHub Pages',
      mode: 'read-only'
    };
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
      const response = await fetch(`${this.localDataPath}stats.json`);
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.warn('Could not load local stats:', error);
    }
    // Return mock stats if local file not found
    return {
      total_feeds: 0,
      total_posts: 0,
      active_channels: 0,
      last_updated: new Date().toISOString()
    };
  }

  async getPublicFeeds() {
    try {
      const response = await fetch(`${this.localDataPath}feed_map.json`);
      if (response.ok) {
        const data = await response.json();
        return Object.values(data || {});
      }
    } catch (error) {
      console.warn('Could not load local feeds:', error);
    }
    return [];
  }

  async getChannels() {
    try {
      const response = await fetch(`${this.localDataPath}meta.json`);
      if (response.ok) {
        const data = await response.json();
        return data.channels || [];
      }
    } catch (error) {
      console.warn('Could not load local channels:', error);
    }
    return [];
  }

  // ===== RECENT ACTIVITY LOGS =====

  async getActivityLogs() {
    // Return mock activity logs
    return [
      {
        timestamp: new Date().toISOString(),
        action: 'dashboard_loaded',
        details: 'Dashboard accessed from GitHub Pages'
      }
    ];
  }

  // ===== FEED MANAGEMENT =====

  async getFeeds() {
    // Use stats data instead of separate feeds.json (stats.json contains better feed health info)
    const statsData = await this.loadDataSmart('/api/stats', 'stats.json');
    if (statsData && statsData.stats && statsData.stats.feed_health) {
      const feeds = Object.values(statsData.stats.feed_health).map(feed => ({
        url: feed.url,
        title: feed.title || 'Unknown Feed',
        description: feed.description || '',
        entry_count: feed.entry_count || 0,
        last_post: feed.last_post,
        last_updated: feed.last_updated,
        has_metadata: feed.has_metadata || false,
        channel: feed.channel,
        page_url: feed.page_url,
        status: feed.status || 'unknown'
      }));
      return {
        last_updated: statsData.stats.last_updated,
        feeds: feeds,
        total_feeds: statsData.stats.total_feeds
      };
    }
    // Fallback to empty structure
    return {
      last_updated: new Date().toISOString(),
      feeds: [],
      total_feeds: 0
    };
  }

  async getStats() {
    // Use smart loading for stats data  
    return this.loadDataSmart('/api/stats', 'stats.json');
  }

  async addFeed(feedUrl) {
    throw new Error('Feed management is not available in read-only mode. Please use GitHub repository settings.');
  }

  async removeFeed(feedUrl) {
    throw new Error('Feed management is not available in read-only mode. Please use GitHub repository settings.');
  }

  async updateFeedMapping(feedUrl, channelId) {
    throw new Error('Feed mapping is not available in read-only mode. Please use GitHub repository settings.');
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
    // Prefer admin API when available; otherwise fall back to public list
    if (this.localDataEnabled) {
      try {
        const meta = await this.loadDataSmart('/api/channels', 'meta.json');
        if (meta && meta.channels) return { channels: meta.channels };
      } catch (err) {
        console.warn('Failed to load local meta.json for channels:', err);
      }
    }
    try {
      return await this.get('/api/channels');
    } catch (error) {
      console.warn('Admin channels endpoint unavailable, falling back to public:', error);
      try {
        const url = `${this.baseUrl}/api/public/channels`;
        const response = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
        const data = await response.json();
        if (Array.isArray(data)) return { channels: data };
        if (Array.isArray(data.channels)) return { channels: data.channels };
        return { channels: [] };
      } catch (pubErr) {
        console.warn('Public channels endpoint unavailable:', pubErr);
        return { channels: [] };
      }
    }
  }

  async addChannel(channelId, name = null, type = null) {
    throw new Error('Channel management is not available in read-only mode. Please use GitHub repository settings.');
  }

  async removeChannel(channelId) {
    throw new Error('Channel management is not available in read-only mode. Please use GitHub repository settings.');
  }

  async fetchChannelName(channelId) {
    // This could potentially work with Discord API, but for now return mock data
    return { name: `Channel ${channelId}`, type: 'text' };
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
    if (this.localDataEnabled) {
      try {
        const meta = await this.loadDataSmart('/api/groups', 'meta.json');
        if (meta && meta.groups) return { groups: meta.groups };
      } catch (err) {
        console.warn('Failed to load local meta.json for groups:', err);
      }
    }
    return this.get('/api/groups');
  }

  async addGroup(groupName) {
    throw new Error('Group management is not available in read-only mode. Please use GitHub repository settings.');
  }

  async renameGroup(oldName, newName) {
    throw new Error('Group management is not available in read-only mode. Please use GitHub repository settings.');
  }

  async removeGroup(groupName) {
    throw new Error('Group management is not available in read-only mode. Please use GitHub repository settings.');
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
    // This should trigger the workflow dispatch (already updated in runJob)
    return await this.runJob({ ignoreSeen: false });
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

  // ===== CACHE & SUMMARY MANAGEMENT =====

  async clearCache() {
    return this.delete('/api/cache');
  }

  async resetSummary() {
    return this.post('/api/reset-summary');
  }
  
  // ===== JOB MANAGEMENT =====
  // Trigger a new bot run job via GitHub Actions
  async runJob(options = {}) {
    try {
      // Use GitHub API directly to dispatch workflow
      const githubToken = (HanuAuth && HanuAuth.getToken && HanuAuth.getToken()) || '';
      if (!githubToken) {
        throw new Error('GitHub token required for workflow dispatch');
      }

      const repo = 'hanu-cordbot/hanu-feedbot';
      const workflowId = 'feed-bot.yml';

      const dispatchUrl = `https://api.github.com/repos/${repo}/actions/workflows/${workflowId}/dispatches`;

      const response = await fetch(dispatchUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${githubToken}`,
          'Accept': 'application/vnd.github.v3+json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          ref: 'main',
          inputs: {
            max_age_hours: '36',
            force_run: 'true',
            debug_mode: 'true'
          }
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        console.error('GitHub API Error:', response.status, errorData);
        throw new Error(`GitHub API Error ${response.status}: ${errorData.message || response.statusText}`);
      }

      console.log('✅ Workflow dispatch successful');
      return { success: true, message: 'Workflow dispatched successfully' };

    } catch (err) {
      console.error('❌ Workflow dispatch failed:', err);
      throw err;
    }
  }

  async getSystemHealth() {
    // Return mock health data
    return {
      status: 'ok',
      checks: {
        database: 'ok',
        api: 'ok',
        cache: 'ok'
      }
    };
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
      // If the static dashboard is configured to use local data, prefer the generated JSON files
      if (this.localDataEnabled) {
        try {
          const localFeeds = await this.loadDataSmart('/api/public/feeds', 'feeds.json');
          const localMeta = await this.loadDataSmart('/api/public/meta', 'meta.json');
          // Normalize shape expected by callers
          return {
            feeds: localFeeds?.feeds || localFeeds || [],
            mappings: localFeeds?.mappings || {},
            metadata: localMeta || {},
            groups: (localMeta && localMeta.groups) || {}
          };
        } catch (err) {
          console.warn('Failed to load local dashboard data, falling back to API:', err);
        }
      }

      const url = `${this.baseUrl}/api/public/feeds`;
      const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.warn('Public feeds endpoint not available:', error);
      return { feeds: [] };
    }
  }

  async getPublicStats() {
    try {
      const response = await fetch(`${this.localDataPath}stats.json`);
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.warn('Could not load local stats:', error);
    }
    // Return mock stats if local file not found
    return {
      total_feeds: 0,
      total_posts: 0,
      active_channels: 0,
      last_updated: new Date().toISOString()
    };
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
