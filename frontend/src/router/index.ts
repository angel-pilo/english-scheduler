import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '../layouts/AppLayout.vue'
import HomeView from '../views/HomeView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: AppLayout,
      children: [{ path: '', name: 'home', component: HomeView }],
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
