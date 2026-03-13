import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    component: () => import('../components/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/dashboard'
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/DashboardView.vue')
      },
      {
        path: 'orders',
        name: 'Orders',
        component: () => import('../views/OrdersView.vue')
      },
      {
        path: 'orders/:id',
        name: 'OrderDetail',
        component: () => import('../views/OrderDetailView.vue')
      },
      {
        path: 'orders/new',
        name: 'NewOrder',
        component: () => import('../views/NewOrderView.vue')
      },
      {
        path: 'clients',
        name: 'Clients',
        component: () => import('../views/ClientsView.vue')
      },
      {
        path: 'clients/:id',
        name: 'ClientDetail',
        component: () => import('../views/ClientDetailView.vue')
      },
      {
        path: 'products',
        name: 'Products',
        component: () => import('../views/ProductsView.vue')
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Защита роутов — редирект на /login если не авторизован
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && auth.isAuthenticated) {
    return { path: '/dashboard' }
  }
})

export default router
