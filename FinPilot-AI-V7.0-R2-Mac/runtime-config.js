// Local-safe defaults. The Netlify build replaces this file in its dedicated
// output directory; it never embeds the preview access token or Gemini key.
window.FINPILOT_CONFIG = Object.freeze({
  apiBaseUrl: '',
  previewMode: false,
  dataMode: 'live',
  demoMode: false,
  accessMode: 'local',
  requirePreviewToken: false,
  assistantTimeoutMs: 105000
});
