import { useState, useCallback, useEffect } from 'react';

type Theme = 'light' | 'dark';

function getStored(): Theme {
  return localStorage.getItem('klaus-theme') === 'dark' ? 'dark' : 'light';
}

function apply(t: Theme) {
  document.documentElement.classList.toggle('dark', t === 'dark');
  localStorage.setItem('klaus-theme', t);
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(getStored);

  useEffect(() => { apply(theme); }, [theme]);

  const toggle = useCallback(() => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  }, []);

  return { theme, toggle, isDark: theme === 'dark' };
}
