/**
 * i18n system - minimal inline dictionary with JSON file loading
 * Supports 7 languages: pt-BR, en, es, fr, de, ja, zh-CN
 * Usage: const t = createTranslator('en'); t('title');
 */

const i18n = (() => {
  const translations = {};
  const supportedLangs = ['pt-BR', 'en', 'es', 'fr', 'de', 'ja', 'zh-CN'];
  let currentLang = 'en';

  // Initialize with all translation files
  supportedLangs.forEach(lang => {
    translations[lang] = {};
  });

  /**
   * Load translation JSON from /../i18n/*.json
   * Falls back to English if file not found or missing keys
   */
  async function loadLanguage(lang) {
    if (!supportedLangs.includes(lang)) {
      console.warn(`Unsupported language: ${lang}, falling back to 'en'`);
      lang = 'en';
    }
    currentLang = lang;
    try {
      const response = await fetch(`/complex-sim-platform/i18n/${lang}.json`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      // Merge: keep existing keys and override with new ones
      translations[lang] = { ...translations[lang], ...data };
    } catch (e) {
      console.error(`Failed to load language ${lang}`, e);
      // Fallback to English
      try {
        const response = await fetch('/complex-sim-platform/i18n/en.json');
        if (response.ok) {
          const data = await response.json();
          translations[lang] = { ...translations[lang], ...data };
        }
      } catch (e2) {
        console.error('Failed to load fallback English', e2);
      }
    }
  }

  /**
   * Get the translation function for a specific language
   * @param {string} lang - language code
   * @returns {function} translation function t(key)
   */
  function use(lang) {
    loadLanguage(lang);
    return function t(key) {
      // Try current language, then fallback to English
      const val = translations[currentLang][key];
      if (val !== undefined && val !== null) {
        return val;
      }
      // Fallback to English
      return translations['en'][key] || key;
    };
  }

  // Expose supported languages
  const getSupportedLangs = () => supportedLangs;
  const getCurrentLang = () => currentLang;

  return {
    use,
    getSupportedLangs,
    getCurrentLang,
    setLanguage: lang => { loadLanguage(lang); }
  };
})();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = i18n;
} else {
  window.i18n = i18n;
}