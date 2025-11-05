// API configuration
const API_BASE_URL = process.env.NODE_ENV === 'production' 
  ? '/api' 
  : '/api'  // Use proxy, don't hardcode port

// Hardcoded user for paper trading (matches backend initialization)
const HARDCODED_USERNAME = 'default'

// Helper function for making API requests
export async function apiRequest(
  endpoint: string, 
  options: RequestInit = {}
): Promise<Response> {
  const url = `${API_BASE_URL}${endpoint}`
  
  const defaultOptions: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  }
  
  const response = await fetch(url, defaultOptions)
  
  if (!response.ok) {
    // Try to extract error message from response body
    try {
      const errorData = await response.json()
      const errorMessage = errorData.detail || errorData.message || `HTTP error! status: ${response.status}`
      throw new Error(errorMessage)
    } catch (e) {
      // If parsing fails, throw generic error
      throw new Error(`HTTP error! status: ${response.status}`)
    }
  }
  
  const contentType = response.headers.get('content-type')
  if (!contentType || !contentType.includes('application/json')) {
    throw new Error('Response is not JSON')
  }
  
  return response
}

// Specific API functions
export async function checkRequiredConfigs() {
  const response = await apiRequest('/config/check-required')
  return response.json()
}

// Crypto-specific API functions
export async function getCryptoSymbols() {
  const response = await apiRequest('/crypto/symbols')
  return response.json()
}

export async function getCryptoPrice(symbol: string) {
  const response = await apiRequest(`/crypto/price/${symbol}`)
  return response.json()
}

export async function getCryptoMarketStatus(symbol: string) {
  const response = await apiRequest(`/crypto/status/${symbol}`)
  return response.json()
}

export async function getPopularCryptos() {
  const response = await apiRequest('/crypto/popular')
  return response.json()
}

// AI Decision Log interfaces and functions
export interface AIDecision {
  id: number
  account_id: number
  decision_time: string
  reason: string
  operation: string
  symbol?: string
  prev_portion: number
  target_portion: number
  total_balance: number
  executed: string
  order_id?: number
}

export interface AIDecisionFilters {
  operation?: string
  symbol?: string
  executed?: boolean
  start_date?: string
  end_date?: string
  limit?: number
}

export async function getAIDecisions(accountId: number, filters?: AIDecisionFilters): Promise<AIDecision[]> {
  const params = new URLSearchParams()
  if (filters?.operation) params.append('operation', filters.operation)
  if (filters?.symbol) params.append('symbol', filters.symbol)
  if (filters?.executed !== undefined) params.append('executed', filters.executed.toString())
  if (filters?.start_date) params.append('start_date', filters.start_date)
  if (filters?.end_date) params.append('end_date', filters.end_date)
  if (filters?.limit) params.append('limit', filters.limit.toString())
  
  const queryString = params.toString()
  const endpoint = `/accounts/${accountId}/ai-decisions${queryString ? `?${queryString}` : ''}`
  
  const response = await apiRequest(endpoint)
  return response.json()
}

export async function getAIDecisionById(accountId: number, decisionId: number): Promise<AIDecision> {
  const response = await apiRequest(`/accounts/${accountId}/ai-decisions/${decisionId}`)
  return response.json()
}

export async function getAIDecisionStats(accountId: number, days?: number): Promise<{
  total_decisions: number
  executed_decisions: number
  execution_rate: number
  operations: { [key: string]: number }
  avg_target_portion: number
}> {
  const params = days ? `?days=${days}` : ''
  const response = await apiRequest(`/accounts/${accountId}/ai-decisions/stats${params}`)
  return response.json()
}

// Chart data API - get balance history for charts
export interface BalanceHistoryPoint {
  timestamp: string
  total_balance: number
  decision_id: number
}

export interface BalanceHistoryParams {
  account_id: number
  time_range: '24h' | '1w' | '30d' | 'all'  // 时间范围
  interval: '6m' | '1h' | '1d'  // 时间周期
  end_time?: string  // 用于分页加载历史数据
  limit?: number  // 返回的数据点数量
}

export async function getBalanceHistory(params: BalanceHistoryParams): Promise<{
  data: BalanceHistoryPoint[]
  has_more: boolean
  next_end_time?: string
}> {
  const queryParams = new URLSearchParams({
    time_range: params.time_range,
    interval: params.interval,
  })
  
  if (params.end_time) queryParams.append('end_time', params.end_time)
  if (params.limit) queryParams.append('limit', params.limit.toString())
  
  const response = await apiRequest(`/accounts/${params.account_id}/balance-history?${queryParams.toString()}`)
  return response.json()
}

// Paginated data APIs
export interface PaginationParams {
  page: number
  page_size: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export async function getAIDecisionsPaginated(
  accountId: number, 
  pagination: PaginationParams,
  filters?: AIDecisionFilters
): Promise<PaginatedResponse<AIDecision>> {
  const params = new URLSearchParams({
    page: pagination.page.toString(),
    page_size: pagination.page_size.toString(),
  })
  
  if (filters?.operation) params.append('operation', filters.operation)
  if (filters?.symbol) params.append('symbol', filters.symbol)
  if (filters?.executed !== undefined) params.append('executed', filters.executed.toString())
  if (filters?.start_date) params.append('start_date', filters.start_date)
  if (filters?.end_date) params.append('end_date', filters.end_date)
  
  const response = await apiRequest(`/accounts/${accountId}/ai-decisions/paginated?${params.toString()}`)
  return response.json()
}

export interface Position {
  id: number
  account_id: number
  symbol: string
  name: string
  market: string
  quantity: number
  available_quantity: number
  avg_cost: number
  last_price?: number
  market_value?: number
}

export async function getPositionsPaginated(
  accountId: number,
  pagination: PaginationParams
): Promise<PaginatedResponse<Position>> {
  const params = new URLSearchParams({
    page: pagination.page.toString(),
    page_size: pagination.page_size.toString(),
  })
  
  const response = await apiRequest(`/accounts/${accountId}/positions/paginated?${params.toString()}`)
  return response.json()
}

export interface Order {
  id: number
  order_no: string
  symbol: string
  name: string
  market: string
  side: string
  order_type: string
  price?: number
  quantity: number
  filled_quantity: number
  status: string
  created_at: string
}

export async function getOrdersPaginated(
  accountId: number,
  pagination: PaginationParams,
  filters?: { status?: string; symbol?: string }
): Promise<PaginatedResponse<Order>> {
  const params = new URLSearchParams({
    page: pagination.page.toString(),
    page_size: pagination.page_size.toString(),
  })
  
  if (filters?.status) params.append('status', filters.status)
  if (filters?.symbol) params.append('symbol', filters.symbol)
  
  const response = await apiRequest(`/accounts/${accountId}/orders/paginated?${params.toString()}`)
  return response.json()
}

export interface Trade {
  id: number
  order_id: number
  account_id: number
  symbol: string
  name: string
  market: string
  side: string
  price: number
  quantity: number
  commission: number
  trade_time: string
}

export async function getTradesPaginated(
  accountId: number,
  pagination: PaginationParams,
  filters?: { symbol?: string }
): Promise<PaginatedResponse<Trade>> {
  const params = new URLSearchParams({
    page: pagination.page.toString(),
    page_size: pagination.page_size.toString(),
  })
  
  if (filters?.symbol) params.append('symbol', filters.symbol)
  
  const response = await apiRequest(`/accounts/${accountId}/trades/paginated?${params.toString()}`)
  return response.json()
}

// User authentication interfaces
export interface User {
  id: number
  username: string
  email?: string
  is_active: boolean
}

export interface UserAuthResponse {
  user: User
  session_token: string
  expires_at: string
}

// Trading Account management functions
export interface TradingAccount {
  id: number
  user_id: number
  name: string  // Display name (e.g., "GPT Trader", "Claude Analyst")
  model?: string  // AI model (e.g., "gpt-4-turbo")
  base_url?: string  // API endpoint
  api_key?: string  // API key (masked in responses)
  okx_api_key?: string  // OKX API Key (masked in responses)
  okx_secret?: string  // OKX API Secret (masked in responses)
  okx_passphrase?: string  // OKX API Passphrase (masked in responses)
  okx_sandbox?: string  // OKX Sandbox environment flag
  initial_capital?: number  // Optional: only for non-OKX accounts
  current_cash?: number  // Optional: real-time data from OKX
  frozen_cash?: number  // Optional: real-time data from OKX
  account_type: string  // "AI" or "MANUAL"
  is_active: boolean
}

export interface TradingAccountCreate {
  name: string
  model?: string
  base_url?: string
  api_key?: string
  okx_api_key?: string
  okx_secret?: string
  okx_passphrase?: string
  okx_sandbox?: string
  initial_capital?: number
  account_type?: string
}

export interface TradingAccountUpdate {
  name?: string
  model?: string
  base_url?: string
  api_key?: string
  okx_api_key?: string
  okx_secret?: string
  okx_passphrase?: string
  okx_sandbox?: string
}


export async function loginUser(username: string, password: string): Promise<UserAuthResponse> {
  const response = await apiRequest('/users/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  return response.json()
}

export async function getUserProfile(sessionToken: string): Promise<User> {
  const response = await apiRequest(`/users/profile?session_token=${sessionToken}`)
  return response.json()
}

// Trading Account management functions (matching backend query parameter style)
export async function listTradingAccounts(sessionToken: string): Promise<TradingAccount[]> {
  const response = await apiRequest(`/accounts/?session_token=${sessionToken}`)
  return response.json()
}

export async function createTradingAccount(account: TradingAccountCreate, sessionToken: string): Promise<TradingAccount> {
  const response = await apiRequest(`/accounts/?session_token=${sessionToken}`, {
    method: 'POST',
    body: JSON.stringify(account),
  })
  return response.json()
}

export async function updateTradingAccount(accountId: number, account: TradingAccountUpdate, sessionToken: string): Promise<TradingAccount> {
  const response = await apiRequest(`/accounts/${accountId}?session_token=${sessionToken}`, {
    method: 'PUT',
    body: JSON.stringify(account),
  })
  return response.json()
}

export async function deleteTradingAccount(accountId: number, sessionToken: string): Promise<void> {
  await apiRequest(`/accounts/${accountId}?session_token=${sessionToken}`, {
    method: 'DELETE',
  })
}

// Account functions for paper trading with hardcoded user
// Note: Backend initializes default user on startup, frontend just queries the endpoints
export async function getAccounts(): Promise<TradingAccount[]> {
  const response = await apiRequest('/account/list')
  return response.json()
}

export async function getOverview(): Promise<any> {
  const response = await apiRequest('/account/overview')
  return response.json()
}

export async function createAccount(account: TradingAccountCreate): Promise<TradingAccount> {
  const response = await apiRequest('/account/', {
    method: 'POST',
    body: JSON.stringify({
      name: account.name,
      model: account.model,
      base_url: account.base_url,
      api_key: account.api_key,
      okx_api_key: account.okx_api_key,
      okx_secret: account.okx_secret,
      okx_passphrase: account.okx_passphrase,
      okx_sandbox: account.okx_sandbox,
      account_type: account.account_type || 'AI',
      initial_capital: account.initial_capital || 10000
    })
  })
  return response.json()
}

export async function updateAccount(accountId: number, account: TradingAccountUpdate): Promise<TradingAccount> {
  const response = await apiRequest(`/account/${accountId}`, {
    method: 'PUT',
    body: JSON.stringify({
      name: account.name,
      model: account.model,
      base_url: account.base_url,
      api_key: account.api_key,
      okx_api_key: account.okx_api_key,
      okx_secret: account.okx_secret,
      okx_passphrase: account.okx_passphrase,
      okx_sandbox: account.okx_sandbox
    })
  })
  return response.json()
}

export async function testLLMConnection(testData: {
  model?: string;
  base_url?: string;
  api_key?: string;
}): Promise<{ success: boolean; message: string; response?: any }> {
  const response = await apiRequest('/account/test-llm', {
    method: 'POST',
    body: JSON.stringify(testData)
  })
  return response.json()
}

// Legacy aliases for backward compatibility
export type AIAccount = TradingAccount
export type AIAccountCreate = TradingAccountCreate

// Updated legacy functions to use default mode for simulation
export const listAIAccounts = () => getAccounts()
export const createAIAccount = (account: any) => {
  console.warn("createAIAccount is deprecated. Use default mode or new trading account APIs.")
  return Promise.resolve({} as TradingAccount)
}
export const updateAIAccount = (id: number, account: any) => {
  console.warn("updateAIAccount is deprecated. Use default mode or new trading account APIs.")
  return Promise.resolve({} as TradingAccount)
}
export const deleteAIAccount = (id: number) => {
  console.warn("deleteAIAccount is deprecated. Use default mode or new trading account APIs.")
  return Promise.resolve()
}

// OKX Account Data API functions
export interface OKXBalance {
  currency: string
  total: number
  free: number
  used: number
}

export interface OKXPosition {
  symbol: string
  side: string
  contracts: number
  contractSize: number
  notional: number
  leverage: number
  unrealizedPnl: number
  percentage: number
  entryPrice: number
  markPrice: number
  liquidationPrice: number
  marginMode: string
  timestamp: number
  datetime: string
}

export interface OKXOrder {
  id: string
  clientOrderId?: string
  symbol: string
  type: string
  side: string
  price: number
  amount: number
  filled: number
  remaining: number
  status: string
  timestamp: number
  datetime: string
}

export interface OKXTrade {
  id: string
  order: string
  symbol: string
  type: string
  side: string
  price: number
  amount: number
  cost: number
  fee?: any
  timestamp: number
  datetime: string
}

export interface OKXAccountSummary {
  total_balance_usdt: number
  positions_value: number
  unrealized_pnl: number
  positions_count: number
  open_orders_count: number
  free_usdt: number
  used_usdt: number
}

export async function getOKXStatus(accountId: number) {
  const response = await apiRequest(`/okx-account/status?account_id=${accountId}`)
  return response.json()
}

export async function getOKXBalance(accountId: number): Promise<{ success: boolean; assets: OKXBalance[] }> {
  const response = await apiRequest(`/okx-account/balance?account_id=${accountId}`)
  return response.json()
}

export async function getOKXPositions(accountId: number, symbol?: string): Promise<{ success: boolean; positions: OKXPosition[]; count: number }> {
  const params = new URLSearchParams({ account_id: accountId.toString() })
  if (symbol) params.append('symbol', symbol)
  const response = await apiRequest(`/okx-account/positions?${params.toString()}`)
  return response.json()
}

export async function getOKXOpenOrders(accountId: number, symbol?: string): Promise<{ success: boolean; orders: OKXOrder[]; count: number }> {
  const params = new URLSearchParams({ account_id: accountId.toString() })
  if (symbol) params.append('symbol', symbol)
  const response = await apiRequest(`/okx-account/orders/open?${params.toString()}`)
  return response.json()
}

export async function getOKXOrderHistory(accountId: number, symbol?: string, limit: number = 100, days: number = 7): Promise<{ success: boolean; orders: OKXOrder[]; count: number }> {
  const params = new URLSearchParams({ account_id: accountId.toString() })
  if (symbol) params.append('symbol', symbol)
  params.append('limit', limit.toString())
  params.append('days', days.toString())
  
  const response = await apiRequest(`/okx-account/orders/history?${params.toString()}`)
  return response.json()
}

export async function getOKXTrades(accountId: number, symbol?: string, limit: number = 100, days: number = 7): Promise<{ success: boolean; trades: OKXTrade[]; count: number }> {
  const params = new URLSearchParams({ account_id: accountId.toString() })
  if (symbol) params.append('symbol', symbol)
  params.append('limit', limit.toString())
  params.append('days', days.toString())
  
  const response = await apiRequest(`/okx-account/trades?${params.toString()}`)
  return response.json()
}

export async function getOKXAccountSummary(accountId: number): Promise<{ success: boolean; summary: OKXAccountSummary }> {
  const response = await apiRequest(`/okx-account/summary?account_id=${accountId}`)
  return response.json()
}

export interface PlaceOKXOrderRequest {
  symbol: string
  side: 'buy' | 'sell'
  quantity: number  // 后端期待的字段名
  orderType: 'market' | 'limit'
  price?: number
  posSide: 'long' | 'short'  // OKX双向持仓模式，必填
  tdMode?: 'cross' | 'isolated'  // 交易模式，默认全仓
  reduceOnly?: boolean  // 是否只减仓
}

export async function placeOKXOrder(accountId: number, orderRequest: PlaceOKXOrderRequest): Promise<{ success: boolean; order_id?: string; error?: string }> {
  // 转换前端的驼峰命名为后端的snake_case
  const backendRequest = {
    symbol: orderRequest.symbol,
    side: orderRequest.side,
    quantity: orderRequest.quantity,
    order_type: orderRequest.orderType,
    price: orderRequest.price,
    pos_side: orderRequest.posSide,
    td_mode: orderRequest.tdMode || 'cross',
    reduce_only: orderRequest.reduceOnly || false
  }
  
  const response = await apiRequest(`/okx-account/order?account_id=${accountId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(backendRequest)
  })
  return response.json()
}