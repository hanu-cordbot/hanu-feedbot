// Analytics tracking library
class HanuAnalytics {
  constructor() {
    this.apiUrl = 'https://hanu-cordbot.snacky496.workers.dev/api/analytics';
    this.sessionId = this.getOrCreateSessionId();
    this.userId = null;
    this.startTime = Date.now();
    this.events = [];
    
    // Auto-track page view
    this.trackPageView();
    
    // Track page unload for session duration
    window.addEventListener('beforeunload', () => {
      this.trackEvent('session_end', 'navigation', {
        duration: Date.now() - this.startTime
      });
      this.flush();
    });
    
    // Batch send events every 30 seconds
    setInterval(() => this.flush(), 30000);
  }
  
  getOrCreateSessionId() {
    let sessionId = sessionStorage.getItem('hanu_session_id');
    if (!sessionId) {
      sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      sessionStorage.setItem('hanu_session_id', sessionId);
    }
    return sessionId;
  }
  
  setUserId(userId) {
    this.userId = userId;
  }
  
  async trackPageView() {
    const loadTime = performance.timing ? 
      performance.timing.loadEventEnd - performance.timing.navigationStart : null;
    
    this.trackEvent('pageview', 'navigation', {
      page: window.location.pathname,
      title: document.title,
      referrer: document.referrer,
      loadTime: loadTime,
      screen: `${screen.width}x${screen.height}`,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      language: navigator.language
    });
  }
  
  trackEvent(action, category, data = {}) {
    const event = {
      type: 'event',
      action: action,
      category: category,
      page: window.location.pathname,
      referrer: document.referrer,
      sessionId: this.sessionId,
      userId: this.userId,
      timestamp: new Date().toISOString(),
      ...data
    };
    
    this.events.push(event);
    console.log('📊 Tracked:', action, data);
    
    // Immediately send critical events
    if (['error', 'bot_run', 'feed_add'].includes(action)) {
      this.flush();
    }
  }
  
  // Track specific dashboard actions
  trackDashboardAction(action, details = {}) {
    this.trackEvent(action, 'dashboard', {
      target: details.target || null,
      value: details.value || null,
      success: details.success !== false
    });
  }
  
  // Track API response times
  trackAPICall(endpoint, duration, success = true) {
    this.trackEvent('api_call', 'performance', {
      endpoint: endpoint,
      duration: duration,
      success: success
    });
  }
  
  // Track errors
  trackError(error, context = '') {
    this.trackEvent('error', 'system', {
      error: error.message || error,
      context: context,
      stack: error.stack || null
    });
  }
  
  // Track user interactions
  trackClick(element, customData = {}) {
    const target = element.id || element.className || element.tagName;
    this.trackEvent('click', 'interaction', {
      target: target,
      text: element.textContent?.slice(0, 50) || '',
      ...customData
    });
  }
  
  // Send events to API
  async flush() {
    if (this.events.length === 0) return;
    
    const eventsToSend = [...this.events];
    this.events = [];
    
    try {
      const response = await fetch(this.apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          events: eventsToSend,
          sessionId: this.sessionId,
          userId: this.userId,
          userAgent: navigator.userAgent,
          page: window.location.pathname,
          referrer: document.referrer
        })
      });
      
      if (!response.ok) {
        console.warn('Analytics failed:', response.status);
      }
    } catch (error) {
      console.warn('Analytics error:', error);
      // Re-add events to queue for retry
      this.events.unshift(...eventsToSend);
    }
  }
}

// Auto-initialize
const Analytics = new HanuAnalytics();

// Global error tracking
window.addEventListener('error', (e) => {
  Analytics.trackError(e.error, `${e.filename}:${e.lineno}`);
});

window.addEventListener('unhandledrejection', (e) => {
  Analytics.trackError(e.reason, 'unhandled_promise');
});

export default Analytics;
