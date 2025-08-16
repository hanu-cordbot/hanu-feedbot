// Configuration for GitHub Pages Dashboard
window.CONFIG = {
  // Your Railway API URL - UPDATE THIS after deployment
  API_BASE_URL: 'https://hanu-feedbot-production.up.railway.app',
  
  // Dashboard settings
  DASHBOARD_TITLE: 'Hanu FeedBot Dashboard',
  VERSION: '2.0.0-enhanced',
  
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
