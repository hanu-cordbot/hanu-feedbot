// Configuration for GitHub Pages Dashboard
window.CONFIG = {
  // Your Railway API URL - UPDATED WITH ACTUAL DEPLOYMENT
  API_BASE_URL: 'https://hanu-feedbot-production.up.railway.app',
  
  // Dashboard settings
  DASHBOARD_TITLE: 'Hanu FeedBot Dashboard',
  VERSION: '2.0.0-enhanced',
  
  // Data sync settings
  DATA_SYNC: {
    enabled: true,
    localDataPath: './data/', // Path to locally cached data
    fallbackToAPI: true, // Fall back to direct API if local data fails
    cacheTimeout: 3600000 // 1 hour cache timeout
  },
  
  // Last data update timestamp (updated by GitHub Actions)
  "lastDataUpdate": "2025-08-17T19:15:49Z",
  
  // Features enabled
  FEATURES: {
    analytics: true,
    promptEditor: true,
    feedManagement: true,
    stats: true,
    realTimeMonitoring: false // Railway serverless doesn't support websockets
  },
  
  // Refresh intervals (in milliseconds)
  REFRESH_INTERVALS: {
    stats: 30000,      // 30 seconds
    feeds: 60000,      // 1 minute
    analytics: 300000  // 5 minutes
  },
  
  // Theme settings
  THEME: {
    primary: '#5865F2',
    secondary: '#57F287', 
    accent: '#FEE75C',
    dark: '#2C2F33',
    light: '#FFFFFF'
  }
};

// Set API base URL globally
window.API_BASE_URL = window.CONFIG.API_BASE_URL;
