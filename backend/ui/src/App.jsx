import React, { useState, useEffect, useRef, useCallback } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, ResponsiveContainer } from 'recharts';
import logo128 from './assets/logo_128.png';
import logo512 from './assets/logo_512.png';
import logo1024 from './assets/logo_1024.png';
import './App.css';

const API_BASE = '/api';
const DEFAULT_BOT_MESSAGE = 'Hello! I\'m here to support you. How are you feeling today?';
const DEFAULT_EMERGENCY_COUNTRY_CODE = '+91';
const EMERGENCY_COUNTRY_OPTIONS = [
  { code: '+91', label: 'India (+91)' },
  { code: '+1', label: 'United States (+1)' },
  { code: '+44', label: 'United Kingdom (+44)' },
  { code: '+61', label: 'Australia (+61)' },
  { code: '+64', label: 'New Zealand (+64)' },
  { code: '+65', label: 'Singapore (+65)' },
  { code: '+60', label: 'Malaysia (+60)' },
  { code: '+66', label: 'Thailand (+66)' },
  { code: '+62', label: 'Indonesia (+62)' },
  { code: '+63', label: 'Philippines (+63)' },
  { code: '+81', label: 'Japan (+81)' },
  { code: '+82', label: 'South Korea (+82)' },
  { code: '+86', label: 'China (+86)' },
  { code: '+852', label: 'Hong Kong (+852)' },
  { code: '+886', label: 'Taiwan (+886)' },
  { code: '+971', label: 'UAE (+971)' },
  { code: '+966', label: 'Saudi Arabia (+966)' },
  { code: '+974', label: 'Qatar (+974)' },
  { code: '+968', label: 'Oman (+968)' },
  { code: '+965', label: 'Kuwait (+965)' },
  { code: '+973', label: 'Bahrain (+973)' },
  { code: '+92', label: 'Pakistan (+92)' },
  { code: '+880', label: 'Bangladesh (+880)' },
  { code: '+94', label: 'Sri Lanka (+94)' },
  { code: '+977', label: 'Nepal (+977)' },
  { code: '+975', label: 'Bhutan (+975)' },
  { code: '+95', label: 'Myanmar (+95)' },
  { code: '+49', label: 'Germany (+49)' },
  { code: '+33', label: 'France (+33)' },
  { code: '+39', label: 'Italy (+39)' },
  { code: '+34', label: 'Spain (+34)' },
  { code: '+31', label: 'Netherlands (+31)' },
  { code: '+32', label: 'Belgium (+32)' },
  { code: '+41', label: 'Switzerland (+41)' },
  { code: '+46', label: 'Sweden (+46)' },
  { code: '+47', label: 'Norway (+47)' },
  { code: '+45', label: 'Denmark (+45)' },
  { code: '+358', label: 'Finland (+358)' },
  { code: '+48', label: 'Poland (+48)' },
  { code: '+43', label: 'Austria (+43)' },
  { code: '+351', label: 'Portugal (+351)' },
  { code: '+353', label: 'Ireland (+353)' },
  { code: '+7', label: 'Russia (+7)' },
  { code: '+90', label: 'Turkey (+90)' },
  { code: '+20', label: 'Egypt (+20)' },
  { code: '+27', label: 'South Africa (+27)' },
  { code: '+234', label: 'Nigeria (+234)' },
  { code: '+254', label: 'Kenya (+254)' },
  { code: '+255', label: 'Tanzania (+255)' },
  { code: '+251', label: 'Ethiopia (+251)' },
  { code: '+212', label: 'Morocco (+212)' },
  { code: '+55', label: 'Brazil (+55)' },
  { code: '+52', label: 'Mexico (+52)' },
  { code: '+54', label: 'Argentina (+54)' },
  { code: '+56', label: 'Chile (+56)' },
  { code: '+57', label: 'Colombia (+57)' },
  { code: '+58', label: 'Venezuela (+58)' },
  { code: '+51', label: 'Peru (+51)' },
  { code: '+593', label: 'Ecuador (+593)' },
  { code: '+502', label: 'Guatemala (+502)' },
  { code: '+507', label: 'Panama (+507)' },
  { code: '+506', label: 'Costa Rica (+506)' },
  { code: '+598', label: 'Uruguay (+598)' },
  { code: '+595', label: 'Paraguay (+595)' },
  { code: '+591', label: 'Bolivia (+591)' },
  { code: '+53', label: 'Cuba (+53)' },
  { code: '+509', label: 'Haiti (+509)' }
];
const GENDER_OPTIONS = [
  { value: '', label: 'Select gender (optional)' },
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'prefer_not_to_say', label: 'Prefer not to say' }
];

const SETTINGS_SECTION_CONTENT = {
  security: {
    title: 'Security',
    description: 'Manage your account security, PIN settings, and active sessions securely.'
  },
  privacy: {
    title: 'Privacy',
    description: 'Control how your conversations and personal data are stored, used, and protected.'
  },
  support: {
    title: 'Support',
    description: 'Configure crisis support features, helplines, and emergency contact preferences.'
  },
  appearance: {
    title: 'Appearance',
    description: 'Customize the visual experience including theme, chat style, and display settings.'
  },
  account: {
    title: 'Account',
    description: 'Manage your account details, email preferences, and account-related actions.'
  }
};

function composeEmergencyContact(countryCode, localNumber) {
  const normalizedCountryCode = (countryCode || '').replace(/[^\d+]/g, '');
  const normalizedLocalNumber = (localNumber || '').replace(/\D/g, '');
  return `${normalizedCountryCode}${normalizedLocalNumber}`;
}

const IMMEDIATE_SELF_HARM_PATTERNS = [
  /\bi want to hurt myself\b/,
  /\bwant to hurt myself\b/,
  /\babout to hurt myself\b/,
  /\bhurt myself\b/,
  /\bhurting myself\b/,
  /\bharm myself\b/,
  /\bkill myself\b/,
  /\bend my life\b/,
  /\bi want to die\b/,
  /\bdon't want to live\b/,
  /\bdont want to live\b/,
  /\bthinking of hurting\b/,
  /\bthoughts of hurting\b/,
  /\bsuicid(?:e|al)\b/
];

function detectImmediateSafetyUiState(text) {
  const normalized = (text || '').trim().toLowerCase();
  if (!normalized) return null;
  if (IMMEDIATE_SELF_HARM_PATTERNS.some((pattern) => pattern.test(normalized))) {
    return 'crisis_1_card';
  }
  return null;
}

function createConversationId() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

function BrandMark({ className = '', alt = 'Serenity logo' }) {
  const classes = ['brand-mark', className].filter(Boolean).join(' ');
  return (
    <div className={classes}>
      <img src={logo128} alt={alt} className="brand-mark-image" />
    </div>
  );
}

function App() {
  // Chat state
  const [messages, setMessages] = useState([
    { role: 'bot', text: DEFAULT_BOT_MESSAGE }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  // UI State
  const [showCrisisModal, setShowCrisisModal] = useState(false);
  const [showSafetyCard, setShowSafetyCard] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [chatSessionId, setChatSessionId] = useState(null);
  const [showAuth, setShowAuth] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [guestMode, setGuestMode] = useState(false);
  const [currentView, setCurrentView] = useState('chat');
  const [themePreference, setThemePreference] = useState(() => {
    if (typeof window === 'undefined') return 'light';
    return window.localStorage.getItem('themePreference') || 'light';
  });
  const [chatBubbleStyle, setChatBubbleStyle] = useState(() => {
    if (typeof window === 'undefined') return 'rounded';
    return window.localStorage.getItem('chatBubbleStyle') || 'rounded';
  });
  const [fontSize, setFontSize] = useState(() => {
    if (typeof window === 'undefined') return 'medium';
    return window.localStorage.getItem('chatFontSize') || 'medium';
  });
  const [isDarkMode, setIsDarkMode] = useState(false);

  // Auth state
  const [authStep, setAuthStep] = useState('email');
  const [authMode, setAuthMode] = useState('signin');
  const [userId, setUserId] = useState('');
  const [username, setUsername] = useState(() => {
    if (typeof window === 'undefined') return '';
    return window.localStorage.getItem('username') || '';
  });
  const [otp, setOtp] = useState('');
  const [gender, setGender] = useState(() => {
    if (typeof window === 'undefined') return '';
    return window.localStorage.getItem('gender') || '';
  });
  const [pin, setPin] = useState('');
  const [pinConfirm, setPinConfirm] = useState('');
  const [pinError, setPinError] = useState('');
  const [authLoading, setAuthLoading] = useState(false);

  // Emergency contact (onboarding)
  const [emergencyCountryCode, setEmergencyCountryCode] = useState(DEFAULT_EMERGENCY_COUNTRY_CODE);
  const [emergencyLocalNumber, setEmergencyLocalNumber] = useState('');
  const [emergencyRelationship, setEmergencyRelationship] = useState('');
  const [showConsentModal, setShowConsentModal] = useState(false);

  // Settings
  const [settings, setSettings] = useState(null);
  const [emergencyContactSettings, setEmergencyContactSettings] = useState(null);
  const [changePinCurrent, setChangePinCurrent] = useState('');
  const [changePinNew, setChangePinNew] = useState('');
  const [changePinConfirm, setChangePinConfirm] = useState('');
  const [changePinMsg, setChangePinMsg] = useState('');
  const [resetPinStep, setResetPinStep] = useState('');
  const [resetPinEmail, setResetPinEmail] = useState('');
  const [resetPinOtp, setResetPinOtp] = useState('');
  const [resetPinNew, setResetPinNew] = useState('');
  const [resetPinConfirm, setResetPinConfirm] = useState('');
  const [deleteAccountPin, setDeleteAccountPin] = useState('');
  const [logoutPin, setLogoutPin] = useState('');
  const [settingsMsg, setSettingsMsg] = useState('');
  const [settingsSection, setSettingsSection] = useState('security');
  const [changeEmailStep, setChangeEmailStep] = useState('');
  const [changeEmailMethod, setChangeEmailMethod] = useState('pin');
  const [changeEmailPin, setChangeEmailPin] = useState('');
  const [changeEmailOldOtp, setChangeEmailOldOtp] = useState('');
  const [changeEmailNew, setChangeEmailNew] = useState('');
  const [changeEmailNewOtp, setChangeEmailNewOtp] = useState('');
  const [usernameDraft, setUsernameDraft] = useState('');
  const [genderDraft, setGenderDraft] = useState('');

  // Dashboard state
  const [dashboardPinVerified, setDashboardPinVerified] = useState(false);
  const [historyPinVerified, setHistoryPinVerified] = useState(false);
  const [pinInput, setPinInput] = useState('');
  const [historyPinRequired, setHistoryPinRequired] = useState(false);
  const [historyPinInput, setHistoryPinInput] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [stats, setStats] = useState(null);
  const [globalStats, setGlobalStats] = useState(null);
  const [globalTrendData, setGlobalTrendData] = useState([]);
  const [userTrendData, setUserTrendData] = useState([]);
  const [conversations, setConversations] = useState([]);

  const messagesEndRef = useRef(null);
  const messagesRef = useRef(messages);
  const previousViewRef = useRef('chat');
  const chatInputRef = useRef(null);
  const activeChatRequestRef = useRef(null);
  const activeChatRequestIdRef = useRef(0);

  function focusChatInput() {
    if (typeof window === 'undefined') return;

    window.requestAnimationFrame(() => {
      const inputEl = chatInputRef.current;
      if (!inputEl || currentView !== 'chat') return;

      inputEl.focus();

      const caretPosition = inputEl.value.length;
      if (typeof inputEl.setSelectionRange === 'function') {
        inputEl.setSelectionRange(caretPosition, caretPosition);
      }
    });
  }

  function cancelActiveChatRequest() {
    if (activeChatRequestRef.current) {
      activeChatRequestRef.current.abort();
      activeChatRequestRef.current = null;
    }
  }

  const applySafetyUiState = useCallback((uiState) => {
    switch (uiState) {
      case 'crisis_2_modal':
      case 'crisis_1_card':
        setShowCrisisModal(false);
        setShowSafetyCard('crisis-1');
        break;
      case 'abuse_card':
        setShowCrisisModal(false);
        setShowSafetyCard('abuse');
        break;
      case 'third_person_card':
      case 'third_person_safety_card':
        setShowCrisisModal(false);
        setShowSafetyCard('third-person-safety');
        break;
      case 'third_person_crisis_card':
        setShowCrisisModal(false);
        setShowSafetyCard('third-person-crisis');
        break;
      default:
        break;
    }
  }, []);

  function resetAuthFields() {
    setOtp('');
    setPin('');
    setPinConfirm('');
    setPinError('');
    setAuthLoading(false);
  }

  function switchAuthMode(mode) {
    setAuthMode(mode);
    setAuthStep('email');
    resetAuthFields();
  }

  // Load session on mount. Protected views require fresh PIN unlocks.
  useEffect(() => {
    const storedSession = localStorage.getItem('sessionId');
    const storedConversationId = localStorage.getItem('conversationId');
    const storedUserId = localStorage.getItem('userId');
    const storedUsername = localStorage.getItem('username');
    const storedGender = localStorage.getItem('gender');
    const storedGuestMode = sessionStorage.getItem('guestMode') === 'true';
    localStorage.removeItem('guestMode');
    if (storedSession) setSessionId(storedSession);
    if (storedUserId) setUserId(storedUserId);
    if (storedUsername) {
      setUsername(storedUsername);
      setUsernameDraft(storedUsername);
    }
    if (storedGender) {
      setGender(storedGender);
      setGenderDraft(storedGender);
    }
    setGuestMode(storedGuestMode);
    if (storedConversationId) setChatSessionId(storedConversationId);
    setShowAuth(!(storedSession && storedUserId) && !storedGuestMode);
    setAuthReady(true);
  }, []);

  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('sessionId', sessionId);
    }
  }, [sessionId]);

  useEffect(() => {
    if (chatSessionId) {
      localStorage.setItem('conversationId', chatSessionId);
    } else {
      localStorage.removeItem('conversationId');
    }
  }, [chatSessionId]);

  useEffect(() => {
    if (!settings || typeof window === 'undefined') return;
    const savedPreference = window.localStorage.getItem('themePreference');
    if (!savedPreference && typeof settings.dark_mode === 'boolean') {
      setThemePreference(settings.dark_mode ? 'dark' : 'light');
    }
  }, [settings]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const applyTheme = () => {
      const dark = themePreference === 'system' ? mediaQuery.matches : themePreference === 'dark';
      document.body.classList.toggle('dark-mode', dark);
      localStorage.setItem('themePreference', themePreference);
      localStorage.setItem('theme', dark ? 'dark' : 'light');
      setIsDarkMode(dark);
    };

    applyTheme();
    mediaQuery.addEventListener('change', applyTheme);

    return () => mediaQuery.removeEventListener('change', applyTheme);
  }, [themePreference]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    document.body.dataset.chatBubbleStyle = chatBubbleStyle;
    localStorage.setItem('chatBubbleStyle', chatBubbleStyle);
  }, [chatBubbleStyle]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    document.body.dataset.fontSize = fontSize;
    localStorage.setItem('chatFontSize', fontSize);
  }, [fontSize]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    if (!loading && currentView === 'chat' && !showAuth) {
      focusChatInput();
    }
  }, [loading, currentView, showAuth]);

  useEffect(() => {
    if ((showSafetyCard || showCrisisModal) && currentView === 'chat' && !showAuth) {
      focusChatInput();
    }
  }, [showSafetyCard, showCrisisModal, currentView, showAuth]);

  useEffect(() => (
    () => {
      cancelActiveChatRequest();
    }
  ), []);

  const loadConversations = useCallback(async (sessId) => {
    if (!sessId) return;
    try {
      setHistoryError('');
      const res = await fetch(`${API_BASE}/conversations`, {
        headers: { 'Authorization': `Bearer ${sessId}` }
      });
      const data = await res.json();
      if (data.success) {
        const rawList = Array.isArray(data.conversations)
          ? data.conversations
          : Array.isArray(data.sessions)
            ? data.sessions
            : [];

        const mapped = rawList
          .map((c, idx) => ({
            conversation_id: c.conversation_id || c.conversationId || c.session_id || c.sessionId || c.id || `conversation-${idx}`,
            title: c.title || 'New conversation',
            summary: c.summary || c.preview || c.last_summary || '',
            intent: c.intent || c.last_intent || '',
            created_at: c.created_at || c.createdAt || '',
            date: c.date || c.last_message_at || c.lastMessageAt || c.timestamp || '',
            last_message_at: c.last_message_at || c.lastMessageAt || c.date || c.timestamp || ''
          }))
          .filter((c) => !!c.conversation_id);

        setConversations(mapped);
      } else if (data.pin_required || res.status === 403) {
        setHistoryPinRequired(true);
        setConversations([]);
        setHistoryError('');
      } else if (res.status === 401) {
        setHistoryError(data.message || 'Session expired. Please login again.');
        setConversations([]);
        handleLogout();
      } else {
        setHistoryError(data.message || 'Unable to load conversation history.');
        setConversations([]);
      }
    } catch (err) {
      console.error('Load conversations error:', err);
      setHistoryError('Unable to load conversation history. Check connection.');
    }
  }, []);

  async function loadSessionConversation(convSessionId) {
    if (!sessionId || !convSessionId) return;
    try {
      const res = await fetch(`${API_BASE}/conversations/${convSessionId}`, {
        headers: { 'Authorization': `Bearer ${sessionId}` }
      });
      const data = await res.json();
      if (data.success && Array.isArray(data.messages)) {
        const msgs = [];
        data.messages.forEach((m) => {
          if (m.role && m.text) {
            msgs.push({ role: m.role, text: m.text });
            return;
          }
          const s = m.summary || '';
          const parts = s.split(' | ');
          if (parts.length >= 2) {
            const userPart = parts[0].replace(/^User:\s*/i, '').trim();
            const botPart = parts[1].replace(/^Bot:\s*/i, '').trim();
            if (userPart) msgs.push({ role: 'user', text: userPart });
            if (botPart) msgs.push({ role: 'bot', text: botPart });
          } else if (s) {
            msgs.push({ role: 'bot', text: s });
          }
        });
        setMessages(msgs.length > 0 ? msgs : [{ role: 'bot', text: DEFAULT_BOT_MESSAGE }]);
        setChatSessionId(convSessionId);
        localStorage.setItem('conversationId', convSessionId);
        setCurrentView('chat');
      }
    } catch (err) {
      console.error('Load session error:', err);
    }
  }

  const loadUserStats = useCallback(async (sessId) => {
    if (!sessId) return;
    try {
      const res = await fetch(`${API_BASE}/analytics/user`, {
        headers: { 'Authorization': `Bearer ${sessId}` }
      });
      const data = await res.json();
      if (data.success) {
        setStats(data);
        setUserTrendData(data.trend_data || []);
      } else if (res.status === 401) {
        handleLogout();
      } else if (res.status === 403) {
        setDashboardPinVerified(false);
      }
    } catch (err) {
      console.error('Load stats error:', err);
    }
  }, []);

  const loadGlobalStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/analytics/global`);
      const data = await res.json();
      if (data.success) {
        setGlobalStats(data);
        setGlobalTrendData(data.trend_data || []);
      }
    } catch (err) {
      console.error('Load global stats error:', err);
    }
  }, []);

  useEffect(() => {
    if (currentView === 'global') {
      loadGlobalStats();
    }
  }, [currentView, loadGlobalStats]);

  useEffect(() => {
    if (currentView === 'dashboard' && dashboardPinVerified && sessionId) {
      loadUserStats(sessionId);
    }
  }, [currentView, dashboardPinVerified, sessionId, loadUserStats]);

  const loadSettings = useCallback(async () => {
    if (!sessionId) return;
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        headers: { 'Authorization': `Bearer ${sessionId}` }
      });
      const data = await res.json();
      if (data.success) {
        setSettings(data.settings || {});
        setEmergencyContactSettings(data.emergency_contact || {});
        const profileUsername = data.profile?.username || '';
        const profileGender = data.profile?.gender || '';
        setUsername(profileUsername);
        setUsernameDraft(profileUsername);
        setGender(profileGender);
        setGenderDraft(profileGender);
        localStorage.setItem('username', profileUsername);
        localStorage.setItem('gender', profileGender);
      } else if (res.status === 401) {
        handleLogout();
      }
    } catch (err) {
      console.error('Load settings error:', err);
    }
  }, [sessionId]);

  useEffect(() => {
    if (currentView === 'settings' && sessionId) {
      loadSettings();
    }
  }, [currentView, sessionId, loadSettings]);

  useEffect(() => {
    if (currentView !== 'history' || !sessionId || !userId) return;
    if (historyPinVerified) {
      loadConversations(sessionId);
    } else {
      setHistoryPinRequired(true);
    }
  }, [currentView, sessionId, userId, historyPinVerified, loadConversations]);

  useEffect(() => {
    const previousView = previousViewRef.current;
    if (previousView === 'chat' && currentView !== 'chat') {
      cancelActiveChatRequest();
      setLoading(false);
    }
    if (previousView === 'dashboard' && currentView !== 'dashboard') {
      setDashboardPinVerified(false);
      setPinInput('');
      setPinError('');
    }
    if (previousView === 'history' && currentView !== 'history') {
      setHistoryPinVerified(false);
      setHistoryPinRequired(false);
      setHistoryPinInput('');
      setHistoryError('');
    }
    previousViewRef.current = currentView;
  }, [currentView]);

  async function handleSend(e) {
    e.preventDefault();
    if (!input.trim()) return;

    const userText = input.trim();
    const immediateSafetyUiState = detectImmediateSafetyUiState(userText);
    setInput('');
    focusChatInput();
    if (immediateSafetyUiState) {
      applySafetyUiState(immediateSafetyUiState);
    }
    cancelActiveChatRequest();

    const controller = new AbortController();
    const requestId = activeChatRequestIdRef.current + 1;
    activeChatRequestIdRef.current = requestId;
    activeChatRequestRef.current = controller;
    setLoading(true);

    const nextMessages = [...messagesRef.current, { role: 'user', text: userText }];
    messagesRef.current = nextMessages;
    setMessages(nextMessages);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          message: userText,
          session_id: sessionId || '',
          conversation_id: chatSessionId || '',
          chat_session_id: chatSessionId || sessionId || '',
          user_id: userId || undefined,
          completed_messages: nextMessages
        })
      });

      if (requestId !== activeChatRequestIdRef.current) {
        return;
      }

      const data = await res.json();

      if (requestId !== activeChatRequestIdRef.current) {
        return;
      }

      const botText = data.response || "I'm here to support you.";
      setMessages(prev => {
        const updatedMessages = [...prev, { role: 'bot', text: botText }];
        messagesRef.current = updatedMessages;
        return updatedMessages;
      });

      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id);
      }
      const nextConversationId = data.conversation_id || data.chat_session_id || chatSessionId;
      if (nextConversationId && nextConversationId !== chatSessionId) {
        setChatSessionId(nextConversationId);
      }
      if (historyPinVerified && userId) {
        loadConversations(data.session_id || sessionId);
      }

      if (data.ui_state) {
        applySafetyUiState(data.ui_state);
      }

    } catch (err) {
      if (err?.name === 'AbortError') {
        return;
      }
      if (requestId === activeChatRequestIdRef.current) {
        setMessages(prev => {
          const updatedMessages = [...prev, { role: 'bot', text: 'Connection error. Please try again.' }];
          messagesRef.current = updatedMessages;
          return updatedMessages;
        });
      }
    } finally {
      if (requestId === activeChatRequestIdRef.current) {
        activeChatRequestRef.current = null;
        setLoading(false);
      }
    }
  }

  async function handleSendOtp(e) {
    e.preventDefault();
    setAuthLoading(true);
    setPinError('');
    try {
      const res = await fetch(`${API_BASE}/auth/send-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: userId })
      });
      const data = await res.json();
      if (data.success) {
        setAuthStep('otp');
      } else {
        setPinError(data.message || 'Failed to send OTP');
      }
    } catch (err) {
      setPinError('Connection error');
    }
    setAuthLoading(false);
  }

  async function handleVerifyOtp(e) {
    e.preventDefault();
    setAuthLoading(true);
    setPinError('');
    try {
      const res = await fetch(`${API_BASE}/auth/verify-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: userId, otp: otp })
      });
      const data = await res.json();
      if (data.success) {
        if (authMode === 'signup' && data.exists) {
          setPinError('An account already exists for this email. Please sign in with your PIN or use Forgot PIN.');
        } else if (authMode !== 'signup' && data.exists) {
          setSessionId(data.session_id);
          setChatSessionId(null);
          setUsername(data.username || '');
          setUsernameDraft(data.username || '');
          setGender(data.gender || '');
          setGenderDraft(data.gender || '');
          setDashboardPinVerified(false);
          setHistoryPinVerified(false);
          localStorage.setItem('sessionId', data.session_id);
          localStorage.setItem('userId', userId);
          localStorage.setItem('username', data.username || '');
          localStorage.setItem('gender', data.gender || '');
          localStorage.removeItem('conversationId');
          sessionStorage.removeItem('guestMode');
          setGuestMode(false);
          setShowAuth(false);
          setAuthStep('email');
          setAuthMode('signin');
          setOtp('');
          setPin('');
          setMessages([{ role: 'bot', text: DEFAULT_BOT_MESSAGE }]);
        } else {
          if (authMode !== 'signup') {
            setPinError('No new account setup is needed here. Please use Sign up for new accounts.');
            setAuthLoading(false);
            return;
          }
          if (data.username) {
            setUsername(data.username);
            setUsernameDraft(data.username);
          }
          if (data.gender) {
            setGender(data.gender);
            setGenderDraft(data.gender);
          }
          // New user: show Emergency Contact (optional) then PIN setup
          setDashboardPinVerified(false);
          setHistoryPinVerified(false);
          setAuthStep('emergency-contact');
        }
      } else {
        setPinError(data.message || 'Invalid OTP');
      }
    } catch (err) {
      setPinError('Connection error');
    }
    setAuthLoading(false);
  }

  function handleEmergencyContactContinue() {
    const num = composeEmergencyContact(emergencyCountryCode, emergencyLocalNumber);
    if (!/^\+[1-9]\d{7,14}$/.test(num)) {
      setPinError('Use E.164 format like +14155550123 for the emergency contact');
      return;
    }
    if (!emergencyRelationship) {
      setPinError('Please select a relationship');
      return;
    }
    setPinError('');
    setShowConsentModal(true);
  }

  async function handleConsentAgree() {
    setAuthLoading(true);
    setPinError('');
    try {
      const res = await fetch(`${API_BASE}/auth/store-emergency-contact-temp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: userId,
          otp: otp,
          contact_number: composeEmergencyContact(emergencyCountryCode, emergencyLocalNumber),
          relationship: emergencyRelationship
        })
      });
      const data = await res.json();
      if (data.success) {
        setShowConsentModal(false);
        setAuthStep('pin-setup');
      } else {
        setPinError(data.message || 'Failed to save contact');
      }
    } catch (err) {
      setPinError('Connection error');
    }
    setAuthLoading(false);
  }

  function handleConsentSkip() {
    setShowConsentModal(false);
    setAuthStep('pin-setup');
  }

  async function handleChangePin(e) {
    e.preventDefault();
    setChangePinMsg('');
    if (changePinNew !== changePinConfirm) {
      setChangePinMsg('New PIN and confirmation do not match');
      return;
    }
    if (changePinNew.length < 4 || changePinNew.length > 6) {
      setChangePinMsg('PIN must be 4-6 digits');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/auth/change-pin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionId}` },
        body: JSON.stringify({ current_pin: changePinCurrent, new_pin: changePinNew })
      });
      const data = await res.json();
      if (data.success) {
        setChangePinMsg('PIN changed successfully');
        setChangePinCurrent(''); setChangePinNew(''); setChangePinConfirm('');
      } else if (res.status === 401) {
        handleLogout();
      } else {
        setChangePinMsg(data.message || 'Failed to change PIN');
      }
    } catch (err) {
      setChangePinMsg('Connection error');
    }
  }

  async function handleResetPinSendOtp() {
    setSettingsMsg('');
    try {
      const res = await fetch(`${API_BASE}/auth/send-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: userId })
      });
      const data = await res.json();
      if (data.success) {
        setResetPinStep('otp');
        setResetPinEmail(userId);
      } else {
        setSettingsMsg(data.message || 'Failed to send OTP');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleResetPin(e) {
    e.preventDefault();
    setSettingsMsg('');
    if (resetPinNew !== resetPinConfirm) {
      setSettingsMsg('PIN and confirmation do not match');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/auth/reset-pin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: resetPinEmail || userId,
          otp: resetPinOtp,
          new_pin: resetPinNew,
          new_pin_confirm: resetPinConfirm
        })
      });
      const data = await res.json();
      if (data.success) {
        setSettingsMsg('PIN reset successfully');
        setResetPinStep('');
        setResetPinOtp(''); setResetPinNew(''); setResetPinConfirm('');
      } else {
        setSettingsMsg(data.message || 'Failed to reset PIN');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleLogoutAll() {
    try {
      const res = await fetch(`${API_BASE}/auth/logout-all`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${sessionId}` }
      });
      if ((await res.json()).success) {
        handleLogout();
      } else if (res.status === 401) {
        handleLogout();
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleClearHistory() {
    if (!window.confirm('Clear all conversation history? This cannot be undone.')) return;
    try {
      const res = await fetch(`${API_BASE}/privacy/clear-history`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${sessionId}` }
      });
      const data = await res.json();
      if (data.success) {
        setSettingsMsg('Conversation history cleared');
        loadConversations(sessionId);
      } else if (res.status === 401) {
        handleLogout();
      } else {
        setSettingsMsg(data.message || 'Failed');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleUpdateCrisisHelpline(enabled) {
    const prev = settings?.crisis_helpline_enabled !== false;
    setSettings(s => ({ ...(s || {}), crisis_helpline_enabled: enabled }));
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionId}` },
        body: JSON.stringify({ crisis_helpline_enabled: enabled })
      });
      if ((await res.json()).success) {
        setSettingsMsg('Updated');
      } else if (res.status === 401) {
        setSettings(s => ({ ...(s || {}), crisis_helpline_enabled: prev }));
        handleLogout();
      } else {
        setSettings(s => ({ ...(s || {}), crisis_helpline_enabled: prev }));
        setSettingsMsg('Failed');
      }
    } catch (err) {
      setSettings(s => ({ ...(s || {}), crisis_helpline_enabled: prev }));
      setSettingsMsg('Connection error');
    }
  }

  async function handleUpdateEmergencyContact(updates) {
    const prev = emergencyContactSettings || {};
    const ec = { ...prev, ...updates };
    const isToggleUpdate = Object.prototype.hasOwnProperty.call(updates, 'enabled') ||
      Object.prototype.hasOwnProperty.call(updates, 'consent_enabled');
    setEmergencyContactSettings(ec);
    try {
      const res = await fetch(`${API_BASE}/settings/emergency-contact`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionId}` },
        body: JSON.stringify(ec)
      });
      const data = await res.json();
      if (data.success) {
        setSettingsMsg('Updated');
      } else if (res.status === 401) {
        if (isToggleUpdate) {
          setEmergencyContactSettings(prev);
        }
        handleLogout();
      } else {
        if (isToggleUpdate) {
          setEmergencyContactSettings(prev);
        }
        setSettingsMsg(data.message || 'Failed');
      }
    } catch (err) {
      if (isToggleUpdate) {
        setEmergencyContactSettings(prev);
      }
      setSettingsMsg('Connection error');
    }
  }

  async function persistThemePreference(preference) {
    const enabled = preference === 'system'
      ? (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches)
      : preference === 'dark';
    setThemePreference(preference);
    setSettings(s => ({ ...(s || {}), dark_mode: enabled }));
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionId}` },
        body: JSON.stringify({ dark_mode: enabled })
      });
      if ((await res.json()).success) {
        setSettingsMsg('Updated');
      } else if (res.status === 401) {
        handleLogout();
      } else {
        setSettingsMsg('Theme saved locally. Server sync failed.');
      }
    } catch (err) {
      setSettingsMsg('Theme saved locally. Connection error while syncing.');
    }
  }

  async function handleLogoutWithPin(e) {
    e.preventDefault();
    setSettingsMsg('');

    if (!logoutPin.trim()) {
      setSettingsMsg('Enter your PIN to logout safely.');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/auth/verify-pin`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${sessionId}`
        },
        body: JSON.stringify({ pin: logoutPin })
      });
      const data = await res.json();

      if (data.success) {
        setLogoutPin('');
        handleLogout();
      } else if (res.status === 401) {
        setLogoutPin('');
        handleLogout();
      } else if (data.pin_not_set) {
        setLogoutPin('');
        setShowAuth(true);
        setAuthStep('pin-setup');
        setPinError(data.message || 'PIN not set. Please create your PIN.');
      } else {
        setSettingsMsg(data.message || 'Incorrect PIN');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleUpdateDarkMode(enabled) {
    await persistThemePreference(enabled ? 'dark' : 'light');
  }

  async function handleDeleteAccount(e) {
    e.preventDefault();
    if (!window.confirm('Permanently delete your account and all data? This cannot be undone.')) return;
    try {
      const res = await fetch(`${API_BASE}/account`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionId}` },
        body: JSON.stringify({ pin: deleteAccountPin })
      });
      const data = await res.json();
      if (data.success) {
        handleLogout();
      } else if (res.status === 401) {
        handleLogout();
      } else {
        setSettingsMsg(data.message || 'Failed');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleSendOldEmailOtp() {
    setSettingsMsg('');
    try {
      const res = await fetch(`${API_BASE}/account/change-email/request-old-otp`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${sessionId}` }
      });
      const data = await res.json();
      if (data.success) {
        setSettingsMsg('OTP sent to your current email');
      } else if (res.status === 401) {
        handleLogout();
      } else {
        setSettingsMsg(data.message || 'Failed to send OTP');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleVerifyChangeEmailIdentity(e) {
    e.preventDefault();
    setSettingsMsg('');
    try {
      const body = changeEmailMethod === 'pin'
        ? { method: 'pin', pin: changeEmailPin }
        : { method: 'otp_old', otp: changeEmailOldOtp };
      const res = await fetch(`${API_BASE}/account/change-email/verify-identity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionId}` },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (data.success) {
        setChangeEmailStep('new-email');
        setChangeEmailPin('');
        setChangeEmailOldOtp('');
      } else if (res.status === 401) {
        handleLogout();
      } else {
        setSettingsMsg(data.message || 'Verification failed');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleSendNewEmailOtp(e) {
    e.preventDefault();
    setSettingsMsg('');
    try {
      const res = await fetch(`${API_BASE}/account/change-email/request-new-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionId}` },
        body: JSON.stringify({ new_email: changeEmailNew })
      });
      const data = await res.json();
      if (data.success) {
        setChangeEmailStep('verify-new');
        setSettingsMsg('OTP sent to your new email');
      } else if (res.status === 401) {
        handleLogout();
      } else {
        setSettingsMsg(data.message || 'Failed to send OTP');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleConfirmNewEmailOtp(e) {
    e.preventDefault();
    setSettingsMsg('');
    try {
      const res = await fetch(`${API_BASE}/account/change-email/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionId}` },
        body: JSON.stringify({ new_email: changeEmailNew, otp: changeEmailNewOtp })
      });
      const data = await res.json();
      if (data.success) {
        setUserId(data.user_id);
        localStorage.setItem('userId', data.user_id);
        setChangeEmailStep('');
        setChangeEmailNew('');
        setChangeEmailNewOtp('');
        setSettingsMsg('Email updated successfully');
      } else if (res.status === 401) {
        handleLogout();
      } else {
        setSettingsMsg(data.message || 'Failed to update email');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleSetupPin(e) {
    e.preventDefault();
    if (username.trim().length < 2) {
      setPinError('Please enter a username with at least 2 characters');
      return;
    }
    if (pin.length < 4 || pin.length > 6) {
      setPinError('PIN must be 4-6 digits');
      return;
    }
    if (pin !== pinConfirm) {
      setPinError('PIN and confirmation do not match');
      return;
    }
    setAuthLoading(true);
    setPinError('');
    try {
      const res = await fetch(`${API_BASE}/auth/setup-pin`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(sessionId ? { 'Authorization': `Bearer ${sessionId}` } : {})
        },
        body: JSON.stringify({ email: userId, otp: otp, username: username, gender: gender, pin: pin, pin_confirm: pinConfirm })
      });
      const data = await res.json();
      if (data.success) {
        setSessionId(data.session_id);
        setChatSessionId(null);
        setUsername(data.username || username);
        setUsernameDraft(data.username || username);
        setGender(data.gender || gender);
        setGenderDraft(data.gender || gender);
        setDashboardPinVerified(false);
        setHistoryPinVerified(false);
        localStorage.setItem('sessionId', data.session_id);
        localStorage.setItem('userId', userId);
        localStorage.setItem('username', data.username || username);
        localStorage.setItem('gender', data.gender || gender);
        localStorage.removeItem('conversationId');
        sessionStorage.removeItem('guestMode');
        setGuestMode(false);
        setShowAuth(false);
        setAuthStep('email');
        setAuthMode('signin');
        setOtp('');
        setPin('');
        setPinConfirm('');
        setMessages([{ role: 'bot', text: DEFAULT_BOT_MESSAGE }]);
      } else {
        setPinError(data.message || 'Failed to setup account');
      }
    } catch (err) {
      setPinError('Connection error');
    }
    setAuthLoading(false);
  }

  async function handleUpdateUsername(e) {
    e.preventDefault();
    setSettingsMsg('');
    if (usernameDraft.trim().length < 2) {
      setSettingsMsg('Username must be at least 2 characters');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/account/username`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionId}` },
        body: JSON.stringify({ username: usernameDraft })
      });
      const data = await res.json();
      if (data.success) {
        const nextUsername = data.profile?.username || usernameDraft.trim();
        setUsername(nextUsername);
        setUsernameDraft(nextUsername);
        localStorage.setItem('username', nextUsername);
        setSettingsMsg(data.message || 'Username updated successfully');
      } else if (res.status === 401) {
        handleLogout();
      } else {
        setSettingsMsg(data.message || 'Failed to update username');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handleUpdateProfile(e) {
    e.preventDefault();
    setSettingsMsg('');
    if (usernameDraft.trim().length < 2) {
      setSettingsMsg('Username must be at least 2 characters');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/account/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionId}` },
        body: JSON.stringify({ username: usernameDraft, gender: genderDraft })
      });
      const data = await res.json();
      if (data.success) {
        const profile = data.profile || {};
        const nextUsername = profile.username || usernameDraft.trim();
        const nextGender = profile.gender || '';
        setUsername(nextUsername);
        setUsernameDraft(nextUsername);
        setGender(nextGender);
        setGenderDraft(nextGender);
        localStorage.setItem('username', nextUsername);
        localStorage.setItem('gender', nextGender);
        setSettingsMsg(data.message || 'Profile updated successfully');
      } else if (res.status === 401) {
        handleLogout();
      } else {
        setSettingsMsg(data.message || 'Failed to update profile');
      }
    } catch (err) {
      setSettingsMsg('Connection error');
    }
  }

  async function handlePinVerify(e) {
    e.preventDefault();
    setPinError('');

    try {
      const res = await fetch(`${API_BASE}/auth/verify-pin`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${sessionId}`
        },
        body: JSON.stringify({ pin: pinInput })
      });
      const data = await res.json();

      if (data.success) {
        setDashboardPinVerified(true);
        setPinInput('');
        loadUserStats(sessionId);
        if (currentView === 'settings') loadSettings();
      } else if (data.pin_not_set) {
        setDashboardPinVerified(false);
        setPinInput('');
        setHistoryPinRequired(false);
        setShowAuth(true);
        setAuthStep('pin-setup');
        setPinError(data.message || 'PIN not set. Please create your PIN.');
      } else {
        setPinError(data.message || 'Incorrect PIN');
        if (res.status === 401 && data.message && data.message.includes('Session expired')) {
          handleLogout();
        }
      }
    } catch (err) {
      setPinError('Verification failed');
    }
  }

  async function handleHistoryPinVerify(e) {
    e.preventDefault();

    try {
      const res = await fetch(`${API_BASE}/auth/verify-pin`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${sessionId}`
        },
        body: JSON.stringify({ pin: historyPinInput })
      });
      const data = await res.json();

      if (data.success) {
        setHistoryPinRequired(false);
        setHistoryPinInput('');
        setHistoryPinVerified(true);
        setHistoryError('');
        loadConversations(sessionId);
      } else if (data.pin_not_set) {
        setHistoryPinRequired(false);
        setHistoryPinInput('');
        setHistoryPinVerified(false);
        setShowAuth(true);
        setAuthStep('pin-setup');
        setPinError(data.message || 'PIN not set. Please create your PIN.');
      } else {
        alert(data.message || 'Incorrect PIN');
        if (res.status === 401 && data.message && data.message.includes('Session expired')) {
          handleLogout();
        }
      }
    } catch (err) {
      alert('Verification failed');
    }
  }

  async function handleNewChat() {
    cancelActiveChatRequest();
    setLoading(false);
    let newChatId = createConversationId();
    if (sessionId && userId) {
      try {
        const res = await fetch(`${API_BASE}/conversations`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${sessionId}` }
        });
        const data = await res.json();
        if (data.success && data.conversation_id) {
          newChatId = data.conversation_id;
        }
      } catch (err) {
        console.error('Create conversation error:', err);
      }
    }
    setChatSessionId(newChatId);
    setMessages([{ role: 'bot', text: DEFAULT_BOT_MESSAGE }]);
    setShowCrisisModal(false);
    setShowSafetyCard(null);
    setCurrentView('chat');
    setInput('');
    if (historyPinVerified && sessionId) {
      loadConversations(sessionId);
    }
  }

  function handleLogout() {
    cancelActiveChatRequest();
    localStorage.removeItem('sessionId');
    localStorage.removeItem('conversationId');
    localStorage.removeItem('userId');
    localStorage.removeItem('username');
    localStorage.removeItem('gender');
    sessionStorage.removeItem('guestMode');
    setSessionId(null);
    setChatSessionId(null);
    setUserId('');
    setUsername('');
    setUsernameDraft('');
    setGender('');
    setGenderDraft('');
    setGuestMode(false);
    setDashboardPinVerified(false);
    setHistoryPinVerified(false);
    setStats(null);
    setConversations([]);
    setHistoryPinRequired(false);
    setChangeEmailStep('');
    setChangeEmailPin('');
    setChangeEmailOldOtp('');
    setChangeEmailNew('');
    setChangeEmailNewOtp('');
    setLogoutPin('');
    setDeleteAccountPin('');
    setSettingsMsg('');
    setLoading(false);
    setMessages([{ role: 'bot', text: DEFAULT_BOT_MESSAGE }]);
    setShowAuth(true);
    setAuthMode('signin');
    setAuthStep('email');
    setCurrentView('chat');
  }

  function handleContinueAsGuest() {
    sessionStorage.setItem('guestMode', 'true');
    setGuestMode(true);
    setChatSessionId(null);
    setShowAuth(false);
    setAuthStep('email');
    setAuthMode('signin');
    setPinError('');
    setCurrentView('chat');
  }

  function openAuthModal() {
    setShowAuth(true);
    switchAuthMode('signin');
  }

  function handleCloseAuthModal() {
    setShowAuth(false);
    switchAuthMode('signin');
    setCurrentView('chat');
  }

  async function handlePinLogin(e) {
    e.preventDefault();
    setAuthLoading(true);
    setPinError('');
    try {
      const res = await fetch(`${API_BASE}/auth/login-pin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: userId, pin })
      });
      const data = await res.json();
      if (data.success) {
        setSessionId(data.session_id);
        setChatSessionId(null);
        setUsername(data.username || '');
        setUsernameDraft(data.username || '');
        setGender(data.gender || '');
        setGenderDraft(data.gender || '');
        setDashboardPinVerified(false);
        setHistoryPinVerified(false);
        localStorage.setItem('sessionId', data.session_id);
        localStorage.setItem('userId', data.user_id || userId);
        localStorage.setItem('username', data.username || '');
        localStorage.setItem('gender', data.gender || '');
        localStorage.removeItem('conversationId');
        sessionStorage.removeItem('guestMode');
        setGuestMode(false);
        setShowAuth(false);
        switchAuthMode('signin');
        setMessages([{ role: 'bot', text: DEFAULT_BOT_MESSAGE }]);
      } else {
        setPinError(data.message || 'Login failed');
      }
    } catch (err) {
      setPinError('Connection error');
    }
    setAuthLoading(false);
  }

  function handleNavigate(view) {
    const requiresAuth = ['dashboard', 'history', 'settings'].includes(view);
    if (requiresAuth && !(sessionId && userId)) {
      openAuthModal();
      return;
    }

    if (view === 'chat') {
      setCurrentView('chat');
      return;
    }

    if (view === 'global') {
      setCurrentView('global');
      return;
    }

    if (view === 'dashboard') {
      setCurrentView('dashboard');
      if (!dashboardPinVerified) setPinError('');
      return;
    }

    if (view === 'history') {
      handleHistoryClick();
      return;
    }

    if (view === 'settings') {
      setCurrentView('settings');
      loadSettings();
    }
  }

  function handleHistoryClick() {
    setCurrentView('history');
    setHistoryError('');
    if (userId && sessionId) {
      if (!historyPinVerified) {
        setHistoryPinRequired(true);
      } else {
        loadConversations(sessionId);
      }
    }
  }

  function formatHistoryDateLabel(dateString) {
    if (!dateString) return 'Unknown';
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return 'Unknown';
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfMessageDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.round((startOfToday - startOfMessageDay) / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function formatHistoryTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }

  const renderSafetyCard = () => {
    if (showSafetyCard === 'crisis-1') {
      return (
        <div className="modal-overlay centered-safety-overlay">
          <div className="crisis-modal user-alert-modal user-alert-crisis centered-safety-card" aria-live="assertive">
            <h2 style={{ color: '#d32f2f' }}>You Matter</h2>
            <p>I'm really concerned about you right now. Please reach out for immediate help:</p>
            <p><strong>AASRA (24/7):</strong> +91 9820466726</p>
            <p><strong>iCall (24/7):</strong> +91 9152987821</p>
            <p><strong>Vandrevala Foundation:</strong> 9999 666 555</p>
            <p><strong>Emergency (India):</strong> 108</p>
            {emergencyContactSettings?.enabled && emergencyContactSettings?.contact_number && (
              <p>
                <strong>Your emergency contact:</strong>{' '}
                {emergencyContactSettings.relationship ? `${emergencyContactSettings.relationship} - ` : ''}
                {emergencyContactSettings.contact_number}
              </p>
            )}
            <p><strong>Website:</strong> <a href="https://www.befrienders.org" target="_blank" rel="noopener noreferrer">befrienders.org</a></p>
            <button onClick={() => { setShowSafetyCard(null); focusChatInput(); }} style={{ marginTop: '15px', padding: '10px 20px' }}>
              I've reached out for help
            </button>
          </div>
        </div>
      );
    }
    if (showSafetyCard === 'abuse') {
      return (
        <div className="modal-overlay centered-safety-overlay">
          <div className="crisis-modal user-alert-modal user-alert-safety centered-safety-card" aria-live="assertive">
            <h2 style={{ color: '#d32f2f' }}>You deserve safety</h2>
            <p>Nobody deserves to be harmed. Help is available to keep you safe:</p>
            <p><strong>Women Helpline:</strong> 181</p>
            <p><strong>National Emergency Number:</strong> 112</p>
            <p><strong>Domestic Abuse Line:</strong> 1091</p>
            <p><strong>Website:</strong> <a href="https://www.befrienders.org" target="_blank" rel="noopener noreferrer">befrienders.org</a></p>
            <button onClick={() => { setShowSafetyCard(null); focusChatInput(); }} style={{ marginTop: '15px', padding: '10px 20px' }}>
              I've reached out for help
            </button>
          </div>
        </div>
      );
    }
    if (showSafetyCard === 'third-person-crisis') {
      return (
        <div className="safety-card third-person third-person-crisis">
          <h3>Let's help them through this crisis</h3>
          <p>It is good that you care. If someone else may be in crisis, ask them to reach immediate support:</p>
          <p><strong>iCall:</strong> +91 9152987821</p>
          <p><strong>AASRA:</strong> +91 9820466726</p>
          <p><strong>Website:</strong> <a href="https://www.befrienders.org" target="_blank" rel="noopener noreferrer">befrienders.org</a></p>
          <button onClick={() => setShowSafetyCard(null)}>Continue Chat</button>
        </div>
      );
    }
    if (showSafetyCard === 'third-person-safety') {
      return (
        <div className="safety-card third-person third-person-safety">
          <h3>Help them stay safe</h3>
          <p>If someone else is being harmed or abused, encourage immediate safety support:</p>
          <p><strong>Women Helpline:</strong> 181</p>
          <p><strong>National Emergency Number:</strong> 112</p>
          <p><strong>Domestic Abuse Line:</strong> 1091</p>
          <p><strong>Website:</strong> <a href="https://www.befrienders.org" target="_blank" rel="noopener noreferrer">befrienders.org</a></p>
          <button onClick={() => setShowSafetyCard(null)}>Continue Chat</button>
        </div>
      );
    }
    return null;
  };

  // Gradient Area Chart using Recharts - real data only
  const GradientAreaChart = ({ data, dataKey, color, gradientId, title, height = 200 }) => {
    const chartData = data && data.length > 0 ? data : [];
    const axisColor = isDarkMode ? '#D5CFF0' : '#7A7489';
    const gridColor = isDarkMode ? '#3A3450' : '#E8E3F0';
    return (
      <div className="gradient-chart-container">
        <h3>{title}</h3>
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.8} />
                <stop offset="100%" stopColor={color} stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis dataKey="day" tick={{ fontSize: 12, fill: axisColor }} stroke={axisColor} />
            <YAxis tick={{ fontSize: 12, fill: axisColor }} stroke={axisColor} allowDecimals={false} />
            <Area
              type="monotone"
              dataKey={dataKey}
              stroke={color}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    );
  };

  // Stat boxes (cylinder-style metric cards)
  const renderStatBox = (label, value, isCrisis = false) => (
    <div className={`stat-box ${isCrisis ? 'crisis' : ''}`}>
      <span className="stat-number">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );

  const formatPercentageValue = (value, decimals = 0) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '0%';
    const percent = Math.max(0, Math.min(100, numeric <= 1 ? numeric * 100 : numeric));
    const fixed = decimals > 0 ? percent.toFixed(decimals) : Math.round(percent).toString();
    return `${fixed.replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1')}%`;
  };

  const formatConfidenceValue = (value) => {
    return formatPercentageValue(value, 0);
  };

  const formatCrisisRateValue = (value) => {
    return formatPercentageValue(value, 1);
  };

  const currentSettingsContent = SETTINGS_SECTION_CONTENT[settingsSection];
  const isAuthenticated = Boolean(sessionId && userId);
  const hasAppAccess = isAuthenticated || guestMode;
  const showAuthShowcase = !hasAppAccess && (
    authMode === 'signin'
    || authMode === 'signup'
    || authStep === 'otp'
  );
  const showWelcomeScreen = currentView === 'chat'
    && messages.length === 1
    && messages[0]?.role === 'bot'
    && messages[0]?.text === DEFAULT_BOT_MESSAGE
    && !loading;

  const renderAuthCard = () => (
    <div className="auth-modal">
      <div className="auth-logo-wrap">
        <img src={logo512} alt="Serenity logo" className="auth-logo" />
      </div>
      {guestMode && showAuth && (
        <button
          type="button"
          className="auth-close-btn"
          onClick={handleCloseAuthModal}
          aria-label="Close login popup"
        >
          ×
        </button>
      )}
      {authStep === 'email' && (
        <>
          <h2>{authMode === 'signin' ? 'Welcome Back' : authMode === 'forgot-pin' ? 'Login With OTP' : 'Create Account'}</h2>
          <form onSubmit={authMode === 'signin' ? handlePinLogin : handleSendOtp}>
            <input
              type="email"
              placeholder="Email Address"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              required
            />
            {authMode === 'signin' && (
              <input
                type="password"
                placeholder="Enter your PIN"
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
                minLength={4}
                required
              />
            )}
            {pinError && <p className="error">{pinError}</p>}
            <button type="submit" disabled={authLoading}>
              {authLoading
                ? (authMode === 'signin' ? 'Signing in...' : 'Sending OTP...')
                : (authMode === 'signin' ? 'Login' : 'Send OTP')}
            </button>
          </form>
          {authMode === 'signin' && (
            <div className="auth-link-stack compact">
              <button type="button" className="auth-inline-link" onClick={() => switchAuthMode('forgot-pin')}>
                Forgot PIN?
              </button>
              <p className="auth-helper-text compact">
                Don&apos;t have an account?{' '}
                <button type="button" className="auth-inline-link" onClick={() => switchAuthMode('signup')}>
                  Sign up
                </button>
              </p>
            </div>
          )}
          {authMode !== 'signin' && (
            <p className="auth-helper-text">
              <button type="button" className="auth-inline-link" onClick={() => switchAuthMode('signin')}>
                {authMode === 'signup' ? 'Already have an account? Sign in' : 'Back to sign in'}
              </button>
            </p>
          )}
        </>
      )}

      {authStep === 'otp' && (
        <>
          <h2>{authMode === 'signup' ? 'Verify Your Email' : 'Verify OTP'}</h2>
          <form onSubmit={handleVerifyOtp}>
            <p>Sent to: {userId}</p>
            <input
              type="text"
              placeholder="Enter 6-digit OTP"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              maxLength={6}
              required
            />
            {pinError && <p className="error">{pinError}</p>}
            <button type="submit" disabled={authLoading}>
              {authLoading ? 'Verifying...' : 'Verify OTP'}
            </button>
          </form>
          <p className="auth-helper-text">
            <button type="button" className="auth-inline-link" onClick={() => switchAuthMode(authMode)}>
              Back
            </button>
          </p>
        </>
      )}

      {authStep === 'emergency-contact' && (
        <>
          <h2>Emergency Support Contact (Optional)</h2>
          <p className="subtext">For additional safety support. You can skip this step.</p>
          <div className="emergency-form">
            <label className="phone-field-label">Mobile</label>
            <div className="phone-input-group">
              <select
                aria-label="Country code"
                className="country-code-input"
                value={emergencyCountryCode}
                onChange={(e) => setEmergencyCountryCode(e.target.value)}
              >
                {EMERGENCY_COUNTRY_OPTIONS.map((option) => (
                  <option key={`${option.code}-${option.label}`} value={option.code}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span className="phone-input-divider" aria-hidden="true" />
              <input
                type="tel"
                placeholder="9123 4567"
                className="mobile-number-input"
                value={emergencyLocalNumber}
                onChange={(e) => setEmergencyLocalNumber(e.target.value.replace(/\D/g, '').slice(0, 14))}
              />
            </div>
            <select
              value={emergencyRelationship}
              onChange={(e) => setEmergencyRelationship(e.target.value)}
            >
              <option value="">Select relationship</option>
              <option value="Mother">Mother</option>
              <option value="Father">Father</option>
              <option value="Brother">Brother</option>
              <option value="Sister">Sister</option>
              <option value="Friend">Friend</option>
              <option value="Partner">Partner</option>
              <option value="Guardian">Guardian</option>
              <option value="Relative">Relative</option>
              <option value="Other">Other</option>
            </select>
            {pinError && <p className="error">{pinError}</p>}
            <div className="emergency-buttons">
              <button type="button" onClick={handleEmergencyContactContinue}>Continue</button>
              <button type="button" className="skip-btn" onClick={() => { setPinError(''); setAuthStep('pin-setup'); }}>Skip This Step</button>
            </div>
          </div>
        </>
      )}

      {authStep === 'pin-setup' && (
        <>
          <h2>Setup Security PIN</h2>
          <form onSubmit={handleSetupPin}>
            <p>Protect your private data.</p>
            <input
              type="text"
              placeholder="Choose a username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              maxLength={40}
              required
            />
            <select value={gender} onChange={(e) => setGender(e.target.value)}>
              {GENDER_OPTIONS.map((option) => (
                <option key={`auth-${option.value || 'blank'}`} value={option.value}>{option.label}</option>
              ))}
            </select>
            <input
              type="password"
              placeholder="Create a 4-6 digit PIN"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              maxLength={6}
              minLength={4}
              required
            />
            <input
              type="password"
              placeholder="Confirm PIN"
              value={pinConfirm}
              onChange={(e) => setPinConfirm(e.target.value)}
              maxLength={6}
              minLength={4}
              required
            />
            {pinError && <p className="error">{pinError}</p>}
            <button type="submit" disabled={authLoading}>
              {authLoading ? 'Saving...' : 'Save PIN & Login'}
            </button>
          </form>
        </>
      )}

    </div>
  );

  const renderConsentModal = () => (
    <div className="modal-overlay">
      <div className="consent-modal">
        <h3>Emergency Support Consent</h3>
        <div className="consent-scroll">
          <p>This system can notify your selected emergency contact if repeated crisis signals, safety concerns, or extremely low emotional confidence are detected during your interactions with the chatbot.</p>
          <p>The notification will only send a short and gentle message asking the contact to check in with you. It will NOT include your conversations, personal messages, or any private details.</p>
          <p>This feature is optional and intended only for emergency support situations.</p>
          <p className="consent-note">Your contact information will only be used for emergency support and will never be shared or used for any other purpose.</p>
        </div>
        {pinError && <p className="error">{pinError}</p>}
        <div className="consent-buttons">
          <button type="button" onClick={handleConsentAgree} disabled={authLoading}>
            {authLoading ? 'Saving...' : 'Agree and Enable Support Contact'}
          </button>
          <button type="button" className="secondary" onClick={handleConsentSkip}>Continue Without This Feature</button>
        </div>
      </div>
    </div>
  );

  if (!authReady) {
    return (
      <div className="app auth-loading-screen">
        <div className="auth-loading-card">
          <div className="auth-loading-mark">
            <img src={logo512} alt="Serenity logo" className="auth-loading-logo" />
          </div>
          <h2>Serenity</h2>
          <p>Preparing your safe space...</p>
        </div>
      </div>
    );
  }

  if (!hasAppAccess) {
    if (!showAuthShowcase) {
      return (
        <div className="app auth-entry-app">
          <div className="auth-entry-shell">
            {renderAuthCard()}
            <button type="button" className="guest-entry-btn auth-entry-guest" onClick={handleContinueAsGuest}>
              Continue as guest
            </button>
          </div>
          {showConsentModal && renderConsentModal()}
        </div>
      );
    }

    return (
      <div className="app auth-gate-app">
        <div className="auth-gate-shell">
          <div className="auth-gate-visual">
            <div className="auth-gate-brand">
              <BrandMark alt="Serenity logo" />
              <div className="brand-copy">
                <h1>Serenity</h1>
                <p>Mental Wellness Assistant</p>
              </div>
            </div>
            <div className="auth-hero-logo-wrap">
              <img src={logo1024} alt="Serenity main logo" className="auth-hero-logo" />
            </div>
            <div className="auth-gate-preview">
              <div className="preview-bubble bot">Hello, I'm here to listen and support you.</div>
              <div className="preview-bubble user">I want a calm space to reflect.</div>
              <div className="preview-bubble bot">We can take this one step at a time.</div>
            </div>
            <div className="auth-gate-benefits">
              <div className="auth-benefit-card">
                <strong>Private by default</strong>
                <span>Secure OTP login, PIN protection, and thoughtful support features.</span>
              </div>
              <div className="auth-benefit-card">
                <strong>Designed for calm</strong>
                <span>Gentle conversations, trends, history, and personalized settings.</span>
              </div>
            </div>
          </div>
          <div className="auth-gate-panel">
            <div className="auth-gate-copy">
              <span className="welcome-badge welcome-badge--brand">Serenity</span>
              <h2>Welcome to Serenity</h2>
              <p>Your safe space to talk, reflect, and find support.</p>
              <p>Verify your email to continue creating your account.</p>
            </div>
            {renderAuthCard()}
          </div>
        </div>
        {showConsentModal && renderConsentModal()}
      </div>
    );
  }

  return (
    <div className="app">
      {/* Crisis Modal */}
      {showCrisisModal && (
        <div className="modal-overlay">
          <div className="crisis-modal">
            <h2 style={{ color: '#d32f2f' }}>❤️ You Matter</h2>
            <p>I'm really concerned about you right now. Please reach out for immediate help:</p>
            <p><strong>AASRA (24/7):</strong> +91 9820466726</p>
            <p><strong>iCall (24/7):</strong> +91 9152987821</p>
            <p><strong>Vandrevala Foundation:</strong> 9999 666 555</p>
            <p><strong>Emergency (India):</strong> 108</p>
            <p><strong>Website:</strong> <a href="https://www.befrienders.org" target="_blank" rel="noopener noreferrer">befrienders.org</a></p>
            <button onClick={() => setShowCrisisModal(false)} style={{ marginTop: '15px', padding: '10px 20px' }}>
              I've reached out for help
            </button>
          </div>
        </div>
      )}

      {/* Auth Modal - show when in auth/onboarding flow (not just when !sessionId; guests may have sessionId) */}
      {showAuth && (
        <div className="modal-overlay">
          {renderAuthCard()}
        </div>
      )}

      {/* Emergency Support Consent Modal */}
      {showConsentModal && renderConsentModal()}

      <div className="app-layout">
        <div className="main-content">
          <div className="app-header">
            <div className="header-left">
              <BrandMark alt="Serenity logo" />
              <div className="brand-copy">
                <h1>Serenity</h1>
                <p>Mental Wellness Assistant</p>
              </div>
            </div>
            <div className="header-buttons">
              {currentView === 'chat' ? (
                <button className="primary-nav-btn" onClick={handleNewChat}>✨ New Chat</button>
              ) : (
                <button onClick={() => handleNavigate('chat')}>💬 Chat</button>
              )}
              <button className={currentView === 'global' ? 'active-nav-btn' : ''} onClick={() => handleNavigate('global')}>Global Trends</button>
              <button className={currentView === 'dashboard' ? 'active-nav-btn' : ''} onClick={() => handleNavigate('dashboard')}>My Trends</button>
              <button className={currentView === 'history' ? 'active-nav-btn' : ''} onClick={() => handleNavigate('history')}>History</button>
              <button className={currentView === 'settings' ? 'active-nav-btn' : ''} onClick={() => handleNavigate('settings')}>⚙ Settings</button>
              {!sessionId && (
                <button onClick={openAuthModal}>Login</button>
              )}
            </div>
          </div>

          {currentView === 'chat' && (
            <div className={`chat-container bubble-${chatBubbleStyle} font-${fontSize}`}>
              <div className="messages-area">
                {showWelcomeScreen ? (
                  <div className="welcome-screen">
                    <div className="welcome-card">
                      <img src={logo512} alt="Serenity logo" className="welcome-logo" />
                      <div className="welcome-badge welcome-badge--brand">Serenity</div>
                      <h2>Welcome to Serenity</h2>
                      <p>Your safe space to talk, reflect, and find support.</p>
                      <p>Start a conversation anytime.</p>
                    </div>
                  </div>
                ) : messages.map((msg, i) => (
                  <div key={i} className={`message ${msg.role}`}>
                    <div className="message-content">{msg.text}</div>
                  </div>
                ))}
                {loading && (
                  <div className="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                )}
                {renderSafetyCard()}
                <div ref={messagesEndRef} />
              </div>
              <form className="input-area" onSubmit={handleSend}>
                <input
                  ref={chatInputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Share what’s on your mind..."
                />
                <button type="submit" disabled={!input.trim()}>Send</button>
              </form>
            </div>
          )}

          {currentView === 'history' && (
            <div className="history-view">
              <div className="history-page-header">
                <h2>Conversation History</h2>
                <p>View your past conversations</p>
              </div>

              {historyPinRequired && sessionId && userId ? (
                <div className="history-pin-required history-page-pin-card">
                  <p>Enter PIN to view history</p>
                  <form onSubmit={handleHistoryPinVerify}>
                    <input
                      type="password"
                      value={historyPinInput}
                      onChange={(e) => setHistoryPinInput(e.target.value)}
                      placeholder="PIN"
                      maxLength={6}
                    />
                    <button type="submit">Unlock</button>
                  </form>
                </div>
              ) : !userId ? (
                <div className="history-list history-page-list">
                  <p className="no-history">Login to view history</p>
                </div>
              ) : (
                <div className="history-page-list">
                  {conversations.length > 0 ? (
                    conversations.map((conv, i) => (
                      <button
                        key={conv.conversation_id || conv.session_id || i}
                        type="button"
                        className="history-page-item"
                        onClick={() => loadSessionConversation(conv.conversation_id || conv.session_id)}
                      >
                        <div className="history-item-left">
                          <span className="history-item-icon">💬</span>
                          <div className="history-item-text">
                            <h3>{conv.title || 'New conversation'}</h3>
                            <p>{formatHistoryDateLabel(conv.last_message_at || conv.date || conv.created_at)}</p>
                          </div>
                        </div>
                        <div className="history-item-right">
                          <span className="history-item-time">{formatHistoryTime(conv.last_message_at || conv.date)}</span>
                          <span className="history-arrow">›</span>
                        </div>
                      </button>
                    ))
                  ) : historyError ? (
                    <p className="no-history">{historyError}</p>
                  ) : (
                    <p className="no-history">
                      No conversation history for {username || userId || 'this account'} yet
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {currentView === 'settings' && sessionId && (
            <div className="settings-view">
              <div className="settings-shell">
                <aside className="settings-sidebar">
                  <h3>Settings</h3>
                  <button className={`settings-nav-item ${settingsSection === 'security' ? 'active' : ''}`} onClick={() => setSettingsSection('security')}><span className="nav-icon">S</span>Security</button>
                  <button className={`settings-nav-item ${settingsSection === 'privacy' ? 'active' : ''}`} onClick={() => setSettingsSection('privacy')}><span className="nav-icon">P</span>Privacy</button>
                  <button className={`settings-nav-item ${settingsSection === 'support' ? 'active' : ''}`} onClick={() => setSettingsSection('support')}><span className="nav-icon">H</span>Support</button>
                  <button className={`settings-nav-item ${settingsSection === 'appearance' ? 'active' : ''}`} onClick={() => setSettingsSection('appearance')}><span className="nav-icon">A</span>Appearance</button>
                  <button className={`settings-nav-item ${settingsSection === 'account' ? 'active' : ''}`} onClick={() => setSettingsSection('account')}><span className="nav-icon">C</span>Account</button>
                </aside>

                <div className="settings-content">
                  <div className="settings-header">
                    <h2>{currentSettingsContent.title}</h2>
                    <p>{currentSettingsContent.description}</p>
                  </div>
                  {settingsMsg && <p className="settings-msg">{settingsMsg}</p>}

                  {settingsSection === 'security' && (
                    <section className="settings-panel">
                      <div className="settings-item">
                        <span>Change PIN</span>
                        <form onSubmit={handleChangePin} className="inline-form">
                          <input type="password" placeholder="Current PIN" value={changePinCurrent} onChange={(e) => setChangePinCurrent(e.target.value)} maxLength={6} />
                          <input type="password" placeholder="New PIN" value={changePinNew} onChange={(e) => setChangePinNew(e.target.value)} maxLength={6} />
                          <input type="password" placeholder="Confirm" value={changePinConfirm} onChange={(e) => setChangePinConfirm(e.target.value)} maxLength={6} />
                          <button type="submit">Change</button>
                        </form>
                        {changePinMsg && <small className="error">{changePinMsg}</small>}
                      </div>
                      <div className="settings-item">
                        <span>Reset PIN (Email OTP)</span>
                        {!resetPinStep ? (
                          <button onClick={handleResetPinSendOtp}>Send OTP</button>
                        ) : (
                          <form onSubmit={handleResetPin} className="inline-form">
                            <input type="text" placeholder="OTP" value={resetPinOtp} onChange={(e) => setResetPinOtp(e.target.value)} maxLength={6} />
                            <input type="password" placeholder="New PIN" value={resetPinNew} onChange={(e) => setResetPinNew(e.target.value)} maxLength={6} />
                            <input type="password" placeholder="Confirm" value={resetPinConfirm} onChange={(e) => setResetPinConfirm(e.target.value)} maxLength={6} />
                            <button type="submit">Reset</button>
                            <button type="button" className="secondary-btn" onClick={() => setResetPinStep('')}>Cancel</button>
                          </form>
                        )}
                      </div>
                      <div className="settings-item">
                        <span>Logout from all sessions</span>
                        <button onClick={handleLogoutAll} className="danger">Logout All</button>
                      </div>
                    </section>
                  )}

                  {settingsSection === 'privacy' && (
                    <section className="settings-panel">
                      <div className="settings-item account-email-row">
                        <span>Username</span>
                        <strong className="account-email-value">{username || 'Not set'}</strong>
                      </div>

                      <div className="settings-item account-actions">
                        <span>Profile</span>
                        <form onSubmit={handleUpdateProfile} className="inline-form">
                          <input
                            type="text"
                            placeholder="Enter new username"
                            value={usernameDraft}
                            onChange={(e) => setUsernameDraft(e.target.value)}
                            maxLength={40}
                          />
                          <select className="inline-form-select" value={genderDraft} onChange={(e) => setGenderDraft(e.target.value)}>
                            {GENDER_OPTIONS.map((option) => (
                              <option key={`settings-${option.value || 'blank'}`} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                          <button type="submit">Save</button>
                        </form>
                      </div>

                      <div className="settings-item account-email-row">
                        <span>Gender</span>
                        <strong className="account-email-value">
                          {gender === 'male' ? 'Male' : gender === 'female' ? 'Female' : 'Prefer not to say'}
                        </strong>
                      </div>

                      <div className="settings-item">
                        <span>Clear conversation history</span>
                        <button onClick={handleClearHistory}>Clear History</button>
                      </div>
                    </section>
                  )}

                  {settingsSection === 'support' && (
                    <section className="settings-panel">
                      <div className="settings-item setting-row">
                        <span>Crisis helpline suggestions</span>
                        <label className="toggle">
                          <input type="checkbox" checked={settings?.crisis_helpline_enabled !== false} onChange={(e) => handleUpdateCrisisHelpline(e.target.checked)} />
                          <span className="slider"></span>
                        </label>
                      </div>
                      <div className="settings-item emergency-contact-settings">
                        <h4>Emergency Support Contact</h4>
                        <div className="row setting-row">
                          <span>Enable</span>
                          <label className="toggle">
                            <input type="checkbox" checked={emergencyContactSettings?.enabled || false} onChange={(e) => handleUpdateEmergencyContact({ enabled: e.target.checked })} />
                            <span className="slider"></span>
                          </label>
                        </div>
                        <input type="tel" placeholder="Contact Number" value={emergencyContactSettings?.contact_number || ''} onChange={(e) => setEmergencyContactSettings(ec => ({ ...ec, contact_number: e.target.value }))} onBlur={(e) => handleUpdateEmergencyContact({ contact_number: e.target.value })} />
                        <select value={emergencyContactSettings?.relationship || ''} onChange={(e) => handleUpdateEmergencyContact({ relationship: e.target.value })}>
                          <option value="">Relationship</option>
                          <option value="Mother">Mother</option>
                          <option value="Father">Father</option>
                          <option value="Brother">Brother</option>
                          <option value="Sister">Sister</option>
                          <option value="Friend">Friend</option>
                          <option value="Partner">Partner</option>
                          <option value="Guardian">Guardian</option>
                          <option value="Relative">Relative</option>
                          <option value="Other">Other</option>
                        </select>
                        <div className="row setting-row">
                          <span>Consent</span>
                          <label className="toggle">
                            <input type="checkbox" checked={emergencyContactSettings?.consent_enabled !== false} onChange={(e) => handleUpdateEmergencyContact({ consent_enabled: e.target.checked })} />
                            <span className="slider"></span>
                          </label>
                        </div>
                      </div>
                    </section>
                  )}

                  {settingsSection === 'appearance' && (
                    <section className="settings-panel appearance-panel">
                      <div className="appearance-row">
                        <div className="appearance-copy">
                          <span>Theme</span>
                          <small>Choose how Serenity should look across your device.</small>
                        </div>
                        <div className="select-wrap appearance-select-wrap">
                          <select
                            className="serenity-select"
                            aria-label="Theme"
                            value={themePreference}
                            onChange={(e) => persistThemePreference(e.target.value)}
                          >
                            <option value="light">Light</option>
                            <option value="dark">Dark</option>
                            <option value="system">System</option>
                          </select>
                        </div>
                      </div>
                      <div className="appearance-divider" aria-hidden="true"></div>
                      <div className="appearance-row">
                        <div className="appearance-copy">
                          <span>Chat Bubble Style</span>
                          <small>Set the tone of your conversation bubbles.</small>
                        </div>
                        <div className="select-wrap appearance-select-wrap">
                          <select
                            className="serenity-select"
                            aria-label="Chat bubble style"
                            value={chatBubbleStyle}
                            onChange={(e) => setChatBubbleStyle(e.target.value)}
                          >
                            <option value="rounded">Rounded</option>
                            <option value="minimal">Minimal</option>
                            <option value="card">Card</option>
                          </select>
                        </div>
                      </div>
                      <div className="appearance-divider" aria-hidden="true"></div>
                      <div className="appearance-row">
                        <div className="appearance-copy">
                          <span>Font Size</span>
                          <small>Pick a comfortable reading size for chats and controls.</small>
                        </div>
                        <div className="select-wrap appearance-select-wrap">
                          <select
                            className="serenity-select"
                            aria-label="Font size"
                            value={fontSize}
                            onChange={(e) => setFontSize(e.target.value)}
                          >
                            <option value="small">Small</option>
                            <option value="medium">Medium</option>
                            <option value="large">Large</option>
                          </select>
                        </div>
                      </div>
                    </section>
                  )}

                  {settingsSection === 'account' && (
                    <section className="settings-panel">
                      <div className="settings-item account-actions">
                        <span>Change Email</span>
                        {!changeEmailStep ? (
                          <button onClick={() => { setChangeEmailStep('verify'); setSettingsMsg(''); }}>Start</button>
                        ) : (
                          <button className="secondary-btn" onClick={() => { setChangeEmailStep(''); setChangeEmailPin(''); setChangeEmailOldOtp(''); setChangeEmailNew(''); setChangeEmailNewOtp(''); }}>
                            Cancel
                          </button>
                        )}
                      </div>

                      {changeEmailStep === 'verify' && (
                        <form className="inline-form account-flow" onSubmit={handleVerifyChangeEmailIdentity}>
                          <div className="email-method-tabs">
                            <button type="button" className={changeEmailMethod === 'pin' ? 'active' : ''} onClick={() => setChangeEmailMethod('pin')}>Verify with PIN</button>
                            <button type="button" className={changeEmailMethod === 'otp_old' ? 'active' : ''} onClick={() => setChangeEmailMethod('otp_old')}>Verify with Current Email OTP</button>
                          </div>
                          {changeEmailMethod === 'pin' ? (
                            <input type="password" placeholder="Enter account PIN" value={changeEmailPin} onChange={(e) => setChangeEmailPin(e.target.value)} maxLength={6} />
                          ) : (
                            <div className="account-actions">
                              <input type="text" placeholder="Enter OTP from current email" value={changeEmailOldOtp} onChange={(e) => setChangeEmailOldOtp(e.target.value)} maxLength={6} />
                              <button type="button" onClick={handleSendOldEmailOtp}>Send OTP</button>
                            </div>
                          )}
                          <button type="submit">Verify Identity</button>
                        </form>
                      )}

                      {changeEmailStep === 'new-email' && (
                        <form className="inline-form account-flow" onSubmit={handleSendNewEmailOtp}>
                          <input type="email" placeholder="Enter new email" value={changeEmailNew} onChange={(e) => setChangeEmailNew(e.target.value)} />
                          <button type="submit">Send OTP to New Email</button>
                        </form>
                      )}

                      {changeEmailStep === 'verify-new' && (
                        <form className="inline-form account-flow" onSubmit={handleConfirmNewEmailOtp}>
                          <input type="text" placeholder="OTP from new email" value={changeEmailNewOtp} onChange={(e) => setChangeEmailNewOtp(e.target.value)} maxLength={6} />
                          <button type="submit">Confirm Email Change</button>
                        </form>
                      )}

                      <div className="settings-item account-actions">
                        <span>Logout</span>
                        <form onSubmit={handleLogoutWithPin} className="inline-form">
                          <input
                            type="password"
                            placeholder="PIN required"
                            value={logoutPin}
                            onChange={(e) => setLogoutPin(e.target.value)}
                            maxLength={6}
                          />
                          <button type="submit">Logout</button>
                        </form>
                      </div>

                      <div className="settings-item">
                        <span>Delete Account</span>
                        <form onSubmit={handleDeleteAccount} className="inline-form">
                          <input type="password" placeholder="PIN confirmation required" value={deleteAccountPin} onChange={(e) => setDeleteAccountPin(e.target.value)} maxLength={6} />
                          <button type="submit" className="danger">Delete Account</button>
                        </form>
                      </div>

                      <div className="settings-item account-email-row">
                        <span>Logged in Email</span>
                        <strong className="account-email-value">{userId || 'Not logged in'}</strong>
                      </div>
                    </section>
                  )}
                </div>
              </div>
            </div>
          )}

          {currentView === 'global' && (
            <div className="dashboard stats-view">
              <h2>Global Trends</h2>

              {/* Two graphs side-by-side in one row */}
              <div className="charts-row">
                <div className="chart-section">
                  <GradientAreaChart
                    data={globalTrendData}
                    dataKey="messages"
                    color="#7C5FC4"
                    gradientId="globalMessagesGradient"
                    title="Conversation Activity (Last 7 Days)"
                    height={200}
                  />
                </div>
                <div className="chart-section">
                  <GradientAreaChart
                    data={globalTrendData}
                    dataKey="crisis"
                    color="#D47272"
                    gradientId="globalCrisisGradient"
                    title="Crisis Level Trend (Last 7 Days)"
                    height={200}
                  />
                </div>
              </div>

              {/* Four metric cards in horizontal row below graphs */}
              <div className="stats-row metrics-row">
                {renderStatBox('Total Messages', globalStats?.total_messages ?? 0)}
                {renderStatBox('Sessions', globalStats?.total_sessions ?? 0)}
                {renderStatBox(
                  'Crisis Rate',
                  formatCrisisRateValue(
                    globalStats?.crisis_rate ?? (
                      (globalStats?.total_messages ?? 0) > 0
                        ? (globalStats?.crisis_count ?? 0) / globalStats.total_messages
                        : 0
                    )
                  ),
                  true
                )}
                {renderStatBox('Confidence', formatConfidenceValue(globalStats?.avg_confidence ?? globalStats?.confidence))}
              </div>
            </div>
          )}

          {currentView === 'dashboard' && sessionId && (
            <div className="dashboard stats-view">
              {!dashboardPinVerified ? (
                <div className="pin-required">
                  <h3>PIN Required</h3>
                  <p>Enter PIN to view your analytics</p>
                  <form onSubmit={handlePinVerify}>
                    <input
                      type="password"
                      value={pinInput}
                      onChange={(e) => setPinInput(e.target.value)}
                      placeholder="Enter PIN"
                      maxLength={6}
                    />
                    {pinError && <p className="error">{pinError}</p>}
                    <button type="submit">Verify</button>
                  </form>
                </div>
              ) : (
                <div>
                  <h2>My Trends</h2>

                  {/* Two graphs side-by-side */}
                  <div className="charts-row">
                    <div className="chart-section">
                      <GradientAreaChart
                        data={userTrendData}
                        dataKey="messages"
                        color="#7C5FC4"
                        gradientId="userMessagesGradient"
                        title="Your Activity (Last 7 Days)"
                        height={200}
                      />
                    </div>
                    <div className="chart-section">
                      <GradientAreaChart
                        data={userTrendData}
                        dataKey="crisis"
                        color="#D47272"
                        gradientId="userCrisisGradient"
                        title="Crisis Level Trend (Last 7 Days)"
                        height={200}
                      />
                    </div>
                  </div>

                  {/* Four metric cards in horizontal row */}
                  <div className="stats-row metrics-row">
                    {renderStatBox('Messages', stats?.total_messages ?? 0)}
                    {renderStatBox('Sessions', stats?.total_sessions ?? 0)}
                    {renderStatBox(
                      'Crisis Rate',
                      formatCrisisRateValue(
                        stats?.crisis_rate ?? (
                          (stats?.total_messages ?? 0) > 0
                            ? (stats?.crisis_count ?? 0) / stats.total_messages
                            : 0
                        )
                      ),
                      true
                    )}
                    {renderStatBox('Confidence', formatConfidenceValue(stats?.avg_confidence ?? stats?.confidence))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
