// 主辦方金鑰。只存在這個分頁的 sessionStorage,關掉分頁就忘記,
// 不放 localStorage,避免共用電腦時被下一個人拿到。

import { ref, watch } from 'vue'

const STORAGE = 'bridge-admin-key'

function read(): string {
  try {
    return sessionStorage.getItem(STORAGE) ?? ''
  } catch {
    return ''
  }
}

const key = ref(read())

watch(key, (value) => {
  try {
    if (value) sessionStorage.setItem(STORAGE, value)
    else sessionStorage.removeItem(STORAGE)
  } catch {
    /* 存不了就只留在記憶體 */
  }
})

export function useAdminKey() {
  return key
}
