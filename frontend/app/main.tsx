import { useEffect, useRef, useState } from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import { Toaster, toast } from 'react-hot-toast'

// Create a module-level WebSocket singleton to avoid duplicate connections in React StrictMode
let __WS_SINGLETON__: WebSocket | null = null;

const resolveWsUrl = () => {
  if (typeof window === 'undefined') return 'ws://localhost:5611/ws'
  
  // In development, always connect to backend port 5611
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'ws://localhost:5611/ws'
  }
  
  // In production, use the same host
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

import Header from '@/components/layout/Header'
import Sidebar from '@/components/layout/Sidebar'
import OKXAccountView from '@/components/portfolio/OKXAccountView'
import ManualTradingView from '@/components/trading/ManualTradingView'
import BalanceChartView from '@/components/portfolio/BalanceChartView'
import TradingDataView from '@/components/portfolio/TradingDataView'

interface User {
  id: number
  username: string
}

interface Account {
  id: number
  user_id: number
  name: string
  account_type: string
  initial_capital: number
  current_cash: number
  frozen_cash: number
}

interface Overview {
  account: Account
  total_assets: number
  positions_value: number
  portfolio?: {
    total_assets: number
    positions_value: number
  }
}

const PAGE_TITLES: Record<string, string> = {
  chart: 'Balance Chart',
  data: 'Trading Data',
  manual: 'Manual Trading',
  okx: 'OKX Account',
}

function App() {
  const [user, setUser] = useState<User | null>(null)
  const [account, setAccount] = useState<Account | null>(null)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [currentPage, setCurrentPage] = useState<string>('chart')
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let reconnectTimer: NodeJS.Timeout | null = null
    let ws = __WS_SINGLETON__
    const created = !ws || ws.readyState === WebSocket.CLOSING || ws.readyState === WebSocket.CLOSED
    
    const connectWebSocket = () => {
      try {
        const wsUrl = resolveWsUrl()
        console.log('🔌 Attempting WebSocket connection to:', wsUrl)
        ws = new WebSocket(wsUrl)
        __WS_SINGLETON__ = ws
        wsRef.current = ws
        
        const handleOpen = () => {
          console.log('✅ WebSocket connected successfully')
          // Start with hardcoded default user for paper trading
          const bootstrapMsg = { type: 'bootstrap', username: 'default', initial_capital: 10000 }
          console.log('📤 Sending bootstrap message:', bootstrapMsg)
          ws!.send(JSON.stringify(bootstrapMsg))
        }
        
        const handleMessage = (e: MessageEvent) => {
          try {
            console.log('📨 WebSocket message received:', e.data.substring(0, 200))
            const msg = JSON.parse(e.data)
            console.log('📦 Parsed message type:', msg.type)
            if (msg.type === 'bootstrap_ok') {
              console.log('✅ Bootstrap successful!')
              if (msg.user) {
                console.log('👤 User set:', msg.user)
                setUser(msg.user)
              }
              if (msg.account) {
                console.log('💼 Account set:', msg.account)
                setAccount(msg.account)
              }
              // request initial snapshot to get overview data
              console.log('📤 Requesting initial snapshot')
              ws!.send(JSON.stringify({ type: 'get_snapshot' }))
            } else if (msg.type === 'snapshot') {
              console.log('📊 Snapshot received')
              setOverview(msg.overview)
            } else if (msg.type === 'order_filled') {
              toast.success('Order filled')
              ws!.send(JSON.stringify({ type: 'get_snapshot' }))
            } else if (msg.type === 'order_pending') {
              toast('Order placed, waiting for fill', { icon: '⏳' })
              ws!.send(JSON.stringify({ type: 'get_snapshot' }))
            } else if (msg.type === 'user_switched') {
              toast.success(`Switched to ${msg.user.username}`)
              setUser(msg.user)
            } else if (msg.type === 'account_switched') {
              toast.success(`Switched to ${msg.account.name}`)
              setAccount(msg.account)
            } else if (msg.type === 'error') {
              console.error(msg.message)
              toast.error(msg.message || 'Order error')
            }
          } catch (err) {
            console.error('Failed to parse WebSocket message:', err)
          }
        }
        
        const handleClose = (event: CloseEvent) => {
          console.log('❌ WebSocket closed - Code:', event.code, 'Reason:', event.reason)
          console.log('   Clean close:', event.wasClean)
          __WS_SINGLETON__ = null
          if (wsRef.current === ws) wsRef.current = null
          
          // Attempt to reconnect after 3 seconds if the close wasn't intentional
          if (event.code !== 1000 && event.code !== 1001) {
            console.log('🔄 Will attempt to reconnect in 3 seconds...')
            reconnectTimer = setTimeout(() => {
              console.log('🔄 Attempting to reconnect WebSocket...')
              connectWebSocket()
            }, 3000)
          }
        }
        
        const handleError = (event: Event) => {
          console.error('🚨 WebSocket error:', event)
          console.error('   WebSocket state:', ws?.readyState)
        }

        ws.addEventListener('open', handleOpen)
        ws.addEventListener('message', handleMessage)
        ws.addEventListener('close', handleClose)
        ws.addEventListener('error', handleError)
        
        return () => {
          ws?.removeEventListener('open', handleOpen)
          ws?.removeEventListener('message', handleMessage)
          ws?.removeEventListener('close', handleClose)
          ws?.removeEventListener('error', handleError)
        }
      } catch (err) {
        console.error('Failed to create WebSocket:', err)
        reconnectTimer = setTimeout(connectWebSocket, 5000)
      }
    }
    
    if (created) {
      connectWebSocket()
    } else {
      wsRef.current = ws
    }

    return () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
    }
  }, [])

  const switchUser = (username: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('WS not connected, cannot switch user')
      toast.error('Not connected to server')
      return
    }
    try {
      wsRef.current.send(JSON.stringify({ type: 'switch_user', username }))
      toast('Switching account...', { icon: '🔄' })
    } catch (e) {
      console.error(e)
      toast.error('Failed to switch user')
    }
  }

  const handleAccountUpdated = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'get_snapshot' }))
    }
  }

  if (!user || !account || !overview) return <div className="p-8">Connecting to trading server...</div>

  const pageTitle = PAGE_TITLES[currentPage] ?? PAGE_TITLES.comprehensive

  return (
    <div className="h-screen flex overflow-hidden">
      <Sidebar
        currentPage={currentPage}
        onPageChange={setCurrentPage}
        onAccountUpdated={handleAccountUpdated}
      />
      <div className="flex-1 flex flex-col w-full md:w-auto">
        <Header
          title={pageTitle}
          currentUser={user}
          currentAccount={account}
          showAccountSelector={false}
          onUserChange={switchUser}
        />
        <main className="flex-1 p-2 md:p-4 overflow-hidden pb-20 md:pb-4">
          {currentPage === 'chart' && account && (
            <BalanceChartView accountId={account.id} />
          )}
          {currentPage === 'data' && account && (
            <TradingDataView accountId={account.id} />
          )}
          {currentPage === 'manual' && account && (
            <ManualTradingView accountId={account.id} />
          )}
          {currentPage === 'okx' && account && (
            <OKXAccountView accountId={account.id} />
          )}
        </main>
      </div>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <>
    <Toaster position="top-right" />
    <App />
  </>,
)
