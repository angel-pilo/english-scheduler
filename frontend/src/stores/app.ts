import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const sidebarOpen = ref(false)

  function toggleSidebar(): void {
    sidebarOpen.value = !sidebarOpen.value
  }

  return { sidebarOpen, toggleSidebar }
})
