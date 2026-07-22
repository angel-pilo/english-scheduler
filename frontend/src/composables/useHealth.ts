import { ref } from 'vue'

import { http } from '../services/http'
import type { HealthResponse } from '../types/api'

export function useHealth() {
  const status = ref<HealthResponse['status'] | null>(null)
  const error = ref<string | null>(null)
  const isLoading = ref(false)

  async function checkHealth(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const response = await http.get<HealthResponse>('/health')
      status.value = response.data.status
    } catch (caught: unknown) {
      status.value = null
      error.value = caught instanceof Error ? caught.message : 'Unknown error'
    } finally {
      isLoading.value = false
    }
  }

  return { checkHealth, error, isLoading, status }
}
