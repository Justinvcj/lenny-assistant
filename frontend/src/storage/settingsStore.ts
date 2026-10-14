/**
 * Client-side Settings Store for Lenny Growth Assistant
 * Persists user preferences to localStorage and updates document element tokens instantly.
 */

export type AppTheme = 'dark' | 'light' | 'system';
export type AccentColor = 'indigo' | 'cyan' | 'emerald' | 'amber' | 'rose';
export type FontSize = 'sm' | 'md' | 'lg';
export type ChatDensity = 'compact' | 'comfortable';

export interface AppSettings {
  theme: AppTheme;
  accentColor: AccentColor;
  fontSize: FontSize;
  sendWithEnter: boolean;
  displayName: string;
  showSources: boolean;
  autoScroll: boolean;
  density: ChatDensity;
}

export const DEFAULT_SETTINGS: AppSettings = {
  theme: 'dark',
  accentColor: 'indigo',
  fontSize: 'md',
  sendWithEnter: true,
  displayName: 'Product Leader',
  showSources: true,
  autoScroll: true,
  density: 'comfortable',
};

const SETTINGS_STORAGE_KEY = 'lenny_settings_v1';

/**
 * Load settings from localStorage with fallback to default tokens.
 */
export function loadSettings(): AppSettings {
  if (typeof window === 'undefined' || !window.localStorage) {
    return DEFAULT_SETTINGS;
  }

  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw);
    return {
      ...DEFAULT_SETTINGS,
      ...parsed,
    };
  } catch (err) {
    console.error('Failed to parse settings from localStorage:', err);
    return DEFAULT_SETTINGS;
  }
}

/**
 * Persist updated settings to localStorage and apply CSS attributes.
 */
export function saveSettings(settings: AppSettings): AppSettings {
  if (typeof window !== 'undefined' && window.localStorage) {
    try {
      window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    } catch (err) {
      console.error('Failed to save settings to localStorage:', err);
    }
  }

  applySettingsToDOM(settings);
  return settings;
}

/**
 * Update partial settings fields.
 */
export function updateSettings(partial: Partial<AppSettings>): AppSettings {
  const current = loadSettings();
  const updated: AppSettings = { ...current, ...partial };
  return saveSettings(updated);
}

/**
 * Apply settings attributes to the root HTML document element.
 */
export function applySettingsToDOM(settings: AppSettings): void {
  if (typeof document === 'undefined') return;

  const root = document.documentElement;

  // 1. Theme (resolve system theme if selected)
  let resolvedTheme = settings.theme;
  if (resolvedTheme === 'system') {
    const prefersDark =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-color-scheme: dark)')?.matches;
    resolvedTheme = prefersDark ? 'dark' : 'light';
  }
  root.setAttribute('data-theme', resolvedTheme);

  // 2. Accent Color
  root.setAttribute('data-accent', settings.accentColor || 'indigo');

  // 3. Font Size
  root.setAttribute('data-font-size', settings.fontSize || 'md');

  // 4. Density
  root.setAttribute('data-density', settings.density || 'comfortable');
}

/**
 * Attach a system theme change listener if theme is 'system'.
 */
export function setupThemeListener(callback: () => void): () => void {
  if (typeof window === 'undefined' || !window.matchMedia) {
    return () => {};
  }

  try {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    if (!mediaQuery) return () => {};
    const handler = () => {
      const current = loadSettings();
      if (current.theme === 'system') {
        applySettingsToDOM(current);
        callback();
      }
    };

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handler);
      return () => mediaQuery.removeEventListener('change', handler);
    } else if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(handler);
      return () => mediaQuery.removeListener(handler);
    }
  } catch {
    // ignore
  }
  return () => {};
}
