/**
 * API Service for Mental Health Chatbot
 * Debug version with extra logging
 */

const API_BASE_URL = '/api';

/**
 * Send a chat message to the backend
 */
export async function sendChatMessage(message, sessionId) {
  console.log('[API] sendChatMessage called:', { message, sessionId });
  
  try {
    const requestBody = {
      message,
      session_id: sessionId || ''
    };
    console.log('[API] Request body:', JSON.stringify(requestBody));
    
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });

    console.log('[API] Response status:', response.status);
    console.log('[API] Response ok:', response.ok);

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[API] HTTP Error:', response.status, errorText);
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    console.log('[API] Response data:', JSON.stringify(data));
    
    // Ensure response field is always present
    const result = {
      success: true,
      response: data.response || data.bot_response || data.message || '',
      ui_state: data.ui_state || 'normal_chat',
      session_id: data.session_id || sessionId,
      status: data.status || 'success',
      ...data
    };
    
    console.log('[API] Returning result:', JSON.stringify(result));
    return result;
  } catch (error) {
    console.error('[API] Chat API error:', error);
    // Return a fallback response so UI doesn't get stuck
    return {
      success: false,
      response: 'I\'m here to support you. How are you feeling today?',
      ui_state: 'normal_chat',
      status: 'error',
      error: error.message
    };
  }
}

/**
 * Register a new user
 */
export async function registerUser(userId, pin) {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ user_id: userId, pin }),
    });

    const data = await response.json();
    return { success: response.ok, ...data };
  } catch (error) {
    console.error('Register error:', error);
    return { success: false, status: 'error' };
  }
}

/**
 * Login with user ID and PIN
 */
export async function loginUser(userId, pin) {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ user_id: userId, pin }),
    });

    const data = await response.json();
    return { success: response.ok, ...data };
  } catch (error) {
    console.error('Login error:', error);
    return { success: false, status: 'error' };
  }
}

/**
 * Get conversation history
 */
export async function getConversations(sessionId) {
  try {
    const response = await fetch(`${API_BASE_URL}/conversations`, {
      headers: {
        'Authorization': `Bearer ${sessionId}`,
      },
    });

    const data = await response.json();
    return { success: response.ok, ...data };
  } catch (error) {
    console.error('Conversations error:', error);
    return { success: false, conversations: [] };
  }
}

/**
 * Get global analytics (no PIN required)
 */
export async function getGlobalAnalytics() {
  try {
    const response = await fetch(`${API_BASE_URL}/analytics/global`);
    const data = await response.json();
    return { success: response.ok, ...data };
  } catch (error) {
    console.error('Analytics error:', error);
    return { success: false };
  }
}

/**
 * Get user analytics (PIN required)
 */
export async function getUserAnalytics(sessionId) {
  try {
    const response = await fetch(`${API_BASE_URL}/analytics/user`, {
      headers: {
        'Authorization': `Bearer ${sessionId}`,
      },
    });

    const data = await response.json();
    return { success: response.ok, ...data };
  } catch (error) {
    console.error('User analytics error:', error);
    return { success: false };
  }
}

/**
 * Submit feedback on a message
 * @param {string|number} messageId - Message ID
 * @param {number} rating - 1 for positive, -1 for negative
 * @param {string} [sessionId] - Optional session for validation
 * @param {string} [intent] - Optional intent for quality monitor
 */
export async function submitFeedback(messageId, rating, sessionId, intent) {
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (sessionId) {
      headers['Authorization'] = `Bearer ${sessionId}`;
    }
    const response = await fetch(`${API_BASE_URL}/feedback`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ message_id: messageId, rating, intent: intent || 'general' }),
    });

    return { success: response.ok };
  } catch (error) {
    console.error('Feedback error:', error);
    return { success: false };
  }
}

/**
 * Verify PIN for user dashboard access
 */
export async function verifyPin(sessionId, pin) {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/verify-pin`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${sessionId}`,
      },
      body: JSON.stringify({ pin }),
    });

    const data = await response.json();
    return { success: response.ok, status: response.status, ...data };
  } catch (error) {
    console.error('PIN verification error:', error);
    return { success: false, status: 500 };
  }
}
