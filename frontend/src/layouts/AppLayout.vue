<script setup lang="ts">
import { RouterView } from 'vue-router'

import AppHeader from '../components/AppHeader.vue'
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <AppHeader />
    <main class="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-12">
      <RouterView />
    </main>
  </div>
</template>
