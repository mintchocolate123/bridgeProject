<script setup lang="ts">
import { watchEffect } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useI18n } from './i18n'

const { t, locale, setLocale } = useI18n()
watchEffect(() => (document.title = t('app.title')))
</script>

<template>
  <header class="app-header">
    <RouterLink to="/" class="brand">
      <span class="logo" aria-hidden="true">♠</span>
      {{ t('app.title') }}
    </RouterLink>
    <nav>
      <RouterLink to="/">{{ t('nav.lobby') }}</RouterLink>
      <RouterLink to="/admin">{{ t('nav.admin') }}</RouterLink>
      <button class="lang" @click="setLocale(locale === 'zh' ? 'en' : 'zh')">{{ t('app.lang') }}</button>
    </nav>
  </header>
  <main>
    <RouterView :key="$route.fullPath.split('?')[0]" />
  </main>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 20px;
  background: var(--header-bg);
  color: #fff;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #fff;
  font-weight: 700;
  font-size: 1.05rem;
  text-decoration: none;
}
.logo {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: #fff;
  color: var(--header-bg);
}
nav {
  display: flex;
  align-items: center;
  gap: 16px;
}
nav a {
  color: rgb(255 255 255 / 0.8);
  text-decoration: none;
  font-size: 0.92rem;
}
nav a.router-link-exact-active {
  color: #fff;
  font-weight: 600;
}
.lang {
  background: transparent;
  border-color: rgb(255 255 255 / 0.5);
  color: #fff;
  padding: 3px 10px;
}
main {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}
@media (max-width: 620px) {
  main {
    padding: 12px;
  }
  .app-header {
    padding: 8px 12px;
  }
}
</style>
