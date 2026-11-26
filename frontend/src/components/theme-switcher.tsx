import { useEffect, useState } from 'react'
import { SearchCombobox } from '@/components/search-combobox'
export type Theme = 'light' | 'dark' | 'system'
export function ThemeSwitcher() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const value = localStorage.getItem('hi10-theme')
      return ['dark', 'light', 'system'].includes(value || '') ? (value as Theme) : 'system'
    } catch {
      return 'system'
    }
  })
  useEffect(() => {
    const media = matchMedia('(prefers-color-scheme: dark)')
    const apply = () =>
      document.documentElement.classList.toggle(
        'dark',
        theme === 'dark' || (theme === 'system' && media.matches),
      )
    apply()
    try {
      localStorage.setItem('hi10-theme', theme)
    } catch {
      /* Storage can be unavailable in private contexts. */
    }
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [theme])
  return (
    <SearchCombobox
      label="Theme"
      value={theme}
      onChange={(value) => setTheme(value as Theme)}
      options={[
        { value: 'light', label: 'Light' },
        { value: 'dark', label: 'Dark' },
        { value: 'system', label: 'System' },
      ]}
      className="w-28"
    />
  )
}
