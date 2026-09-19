import { createRouter, createWebHistory } from 'vue-router'
import LobbyPage from './pages/LobbyPage.vue'
import RoomPage from './pages/RoomPage.vue'
import ReplayPage from './pages/ReplayPage.vue'
import AdminPage from './pages/AdminPage.vue'

// 房號一律轉大寫,網址打小寫也能進
const upper = (route: { params: Record<string, unknown> }) => ({
  code: String(route.params.code).toUpperCase(),
})

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: LobbyPage },
    { path: '/rooms/:code', component: RoomPage, props: upper },
    { path: '/rooms/:code/replay', component: ReplayPage, props: upper },
    { path: '/admin', component: AdminPage },
    { path: '/admin/rooms/:code', component: RoomPage, props: (r) => ({ ...upper(r), admin: true }) },
    // 預留:真人玩家頁面 /play/:code,用玩家 token 呼叫 /state 與 /action,牌桌元件直接沿用
    { path: '/:rest(.*)*', redirect: '/' },
  ],
})
