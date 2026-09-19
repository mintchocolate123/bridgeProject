// 中英切換。字典很小,不需要 vue-i18n。
// 用法:const { t } = useI18n();  t('lobby.title')  t('room.board', { n: 3 })

import { ref } from 'vue'
import en from './en'
import zh from './zh'

export type Locale = 'zh' | 'en'
const dictionaries: Record<Locale, Record<string, string>> = { zh, en }

function initialLocale(): Locale {
  try {
    const saved = localStorage.getItem('locale')
    if (saved === 'zh' || saved === 'en') return saved
  } catch {
    /* 無痕模式等情況讀不到,用預設值 */
  }
  return navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

const locale = ref<Locale>(initialLocale())
document.documentElement.lang = locale.value === 'zh' ? 'zh-Hant' : 'en'

function setLocale(value: Locale) {
  locale.value = value
  document.documentElement.lang = value === 'zh' ? 'zh-Hant' : 'en'
  try {
    localStorage.setItem('locale', value)
  } catch {
    /* 存不了就算了,只是下次要再選一次 */
  }
}

function t(key: string, params: Record<string, string | number> = {}): string {
  const text = dictionaries[locale.value][key] ?? dictionaries.en[key] ?? key
  return text.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? `{${name}}`))
}

export function useI18n() {
  return { t, locale, setLocale }
}
