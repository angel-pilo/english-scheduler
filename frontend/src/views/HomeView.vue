<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import { useHealth } from '../composables/useHealth'

const { t } = useI18n()
const { checkHealth, error, isLoading, status } = useHealth()

onMounted(checkHealth)
</script>

<template>
  <section class="grid items-center gap-10 lg:grid-cols-[1.2fr_0.8fr]">
    <div>
      <p class="mb-4 inline-flex rounded-full bg-teal-50 px-3 py-1 text-sm font-semibold text-teal-700">
        {{ t('home.phase') }}
      </p>
      <h1 class="max-w-3xl text-4xl font-bold tracking-tight text-slate-950 sm:text-5xl">
        {{ t('home.title') }}
      </h1>
      <p class="mt-5 max-w-2xl text-lg leading-8 text-slate-600">{{ t('home.description') }}</p>
    </div>

    <aside class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div class="flex items-center justify-between gap-4">
        <div>
          <p class="text-sm font-medium text-slate-500">{{ t('health.title') }}</p>
          <p class="mt-1 text-lg font-semibold text-slate-900">FastAPI + PostgreSQL</p>
        </div>
        <span
          class="size-3 rounded-full"
          :class="status === 'ok' ? 'bg-emerald-500' : error ? 'bg-red-500' : 'animate-pulse bg-amber-400'"
        />
      </div>

      <div class="mt-6 rounded-xl bg-slate-50 p-4 text-sm">
        <p v-if="isLoading" class="text-slate-600">{{ t('health.checking') }}</p>
        <p v-else-if="status === 'ok'" class="font-medium text-emerald-700">{{ t('health.available') }}</p>
        <p v-else class="font-medium text-red-700">{{ t('health.unavailable') }}</p>
      </div>

      <button
        type="button"
        class="mt-4 w-full rounded-xl bg-teal-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-wait disabled:opacity-60"
        :disabled="isLoading"
        @click="checkHealth"
      >
        {{ t('health.retry') }}
      </button>
    </aside>
  </section>
</template>
