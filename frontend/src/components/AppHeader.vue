<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { locale, t } = useI18n()

function toggleLocale(): void {
  locale.value = locale.value === 'es' ? 'en' : 'es'
  document.documentElement.lang = locale.value
}
</script>

<template>
  <header class="border-b border-slate-200 bg-white">
    <div class="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
      <div class="flex items-center gap-3">
        <div class="grid size-9 place-items-center rounded-xl bg-teal-700 font-bold text-white">ES</div>
        <div>
          <p class="text-sm font-semibold leading-tight text-slate-900">English Scheduler</p>
          <p class="text-xs text-slate-500">{{ t('app.subtitle') }}</p>
        </div>
      </div>

      <button
        type="button"
        class="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-teal-600 hover:text-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-600 focus:ring-offset-2"
        @click="toggleLocale"
      >
        {{ locale === 'es' ? 'EN' : 'ES' }}
        <span class="sr-only">{{ t('app.changeLanguage') }}</span>
      </button>
    </div>
  </header>
</template>
