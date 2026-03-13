/**
 * API-клиент для взаимодействия с FastAPI-бэкендом.
 */
import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// Автоматически добавляем JWT-токен в заголовки
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// При 401 — перенаправляем на страницу входа
http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function login(username, password) {
  const form = new URLSearchParams()
  form.append('username', username)
  form.append('password', password)
  const { data } = await http.post('/auth/token', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  })
  return data
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export async function getDashboard() {
  const { data } = await http.get('/dashboard')
  return data
}

// ---------------------------------------------------------------------------
// Reference
// ---------------------------------------------------------------------------

export async function getReference() {
  const { data } = await http.get('/reference')
  return data
}

// ---------------------------------------------------------------------------
// Orders
// ---------------------------------------------------------------------------

export async function getOrders(params = {}) {
  const { data } = await http.get('/orders', { params })
  return data
}

export async function getOrder(id) {
  const { data } = await http.get(`/orders/${id}`)
  return data
}

export async function createOrder(body) {
  const { data } = await http.post('/orders', body)
  return data
}

export async function updateOrderStatus(id, status) {
  const { data } = await http.patch(`/orders/${id}/status`, { status })
  return data
}

export async function updateOrderTracking(id, trackingNumber) {
  const { data } = await http.patch(`/orders/${id}/tracking`, {
    tracking_number: trackingNumber
  })
  return data
}

// ---------------------------------------------------------------------------
// Clients
// ---------------------------------------------------------------------------

export async function getClients() {
  const { data } = await http.get('/clients')
  return data
}

export async function getClient(id) {
  const { data } = await http.get(`/clients/${id}`)
  return data
}

// ---------------------------------------------------------------------------
// Products
// ---------------------------------------------------------------------------

export async function getProducts(inStockOnly = false) {
  const { data } = await http.get('/products', {
    params: inStockOnly ? { in_stock_only: true } : {}
  })
  return data
}

export async function createProduct(body) {
  const { data } = await http.post('/products', body)
  return data
}

export async function updateProduct(id, body) {
  const { data } = await http.patch(`/products/${id}`, body)
  return data
}

export async function deleteProduct(id) {
  const { data } = await http.delete(`/products/${id}`)
  return data
}
