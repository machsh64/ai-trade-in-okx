import { useState, useEffect } from 'react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Eye } from 'lucide-react'
import {
  getAIDecisionsPaginated,
  getPositionsPaginated,
  getOrdersPaginated,
  getTradesPaginated,
  AIDecision,
  Position,
  Order,
  Trade,
  PaginatedResponse
} from '@/lib/api'
import { toast } from 'react-hot-toast'

interface TradingDataViewProps {
  accountId: number
}

export default function TradingDataView({ accountId }: TradingDataViewProps) {
  const [activeTab, setActiveTab] = useState('ai-decisions')

  return (
    <div className="h-full flex flex-col w-full">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col w-full">
        <TabsList className="grid w-full grid-cols-4 flex-shrink-0 text-xs md:text-sm">
          <TabsTrigger value="ai-decisions" className="text-xs md:text-sm px-1 md:px-3">AI Decisions</TabsTrigger>
          <TabsTrigger value="positions" className="text-xs md:text-sm px-1 md:px-3">Positions</TabsTrigger>
          <TabsTrigger value="orders" className="text-xs md:text-sm px-1 md:px-3">Orders</TabsTrigger>
          <TabsTrigger value="trades" className="text-xs md:text-sm px-1 md:px-3">Trades</TabsTrigger>
        </TabsList>

        <TabsContent value="ai-decisions" className="flex-1 mt-4 min-h-0">
          <AIDecisionsTable accountId={accountId} />
        </TabsContent>

        <TabsContent value="positions" className="flex-1 mt-4 min-h-0">
          <PositionsTable accountId={accountId} />
        </TabsContent>

        <TabsContent value="orders" className="flex-1 mt-4 min-h-0">
          <OrdersTable accountId={accountId} />
        </TabsContent>

        <TabsContent value="trades" className="flex-1 mt-4 min-h-0">
          <TradesTable accountId={accountId} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// AI Decisions Table with Pagination
function AIDecisionsTable({ accountId }: { accountId: number }) {
  const [data, setData] = useState<PaginatedResponse<AIDecision> | null>(null)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [selectedReason, setSelectedReason] = useState<string | null>(null)

  const loadData = async () => {
    try {
      setLoading(true)
      const result = await getAIDecisionsPaginated(accountId, { page, page_size: pageSize })
      setData(result)
    } catch (error) {
      console.error('Failed to load AI decisions:', error)
      toast.error('Failed to load AI decisions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [accountId, page, pageSize])

  const totalPages = data?.total_pages || 0

  return (
    <Card className="h-full flex flex-col">
      <div className="flex-1 min-h-0 overflow-auto p-2 md:p-4">
        <div className="min-w-[640px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs md:text-sm">Time</TableHead>
                <TableHead className="text-xs md:text-sm">Operation</TableHead>
                <TableHead className="text-xs md:text-sm">Symbol</TableHead>
                <TableHead className="text-xs md:text-sm">Target %</TableHead>
                <TableHead className="text-xs md:text-sm">Balance</TableHead>
                <TableHead className="text-xs md:text-sm">Executed</TableHead>
                <TableHead className="text-xs md:text-sm">Reason</TableHead>
              </TableRow>
            </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8">
                  Loading...
                </TableCell>
              </TableRow>
            ) : data && data.items.length > 0 ? (
              data.items.map((decision) => (
                <TableRow key={decision.id}>
                  <TableCell className="text-xs">
                    {new Date(decision.decision_time).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      decision.operation === 'buy_long' ? 'bg-green-100 text-green-800' :
                      decision.operation === 'sell_short' ? 'bg-red-100 text-red-800' :
                      decision.operation === 'hold' ? 'bg-gray-100 text-gray-800' :
                      'bg-blue-100 text-blue-800'
                    }`}>
                      {decision.operation}
                    </span>
                  </TableCell>
                  <TableCell className="font-medium">{decision.symbol || '-'}</TableCell>
                  <TableCell>{(decision.target_portion * 100).toFixed(1)}%</TableCell>
                  <TableCell>${decision.total_balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</TableCell>
                  <TableCell>
                    {String(decision.executed) === 'true' ? (
                      <span className="text-green-600">✓</span>
                    ) : (
                      <span className="text-red-600">✗</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelectedReason(decision.reason)}
                      className="h-6 px-2"
                    >
                      <Eye className="h-3 w-3 mr-1" />
                      View
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-gray-500">
                  No AI decisions found
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        </div>
      </div>

      <div className="flex-shrink-0 border-t p-2 md:p-4">
        <PaginationControls
          page={page}
          totalPages={totalPages}
          onPageChange={setPage}
          loading={loading}
        />
      </div>

      <ReasonDialog
        reason={selectedReason}
        open={selectedReason !== null}
        onClose={() => setSelectedReason(null)}
      />
    </Card>
  )
}

// Positions Table with Pagination
function PositionsTable({ accountId }: { accountId: number }) {
  const [data, setData] = useState<PaginatedResponse<Position> | null>(null)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)

  const loadData = async () => {
    try {
      setLoading(true)
      const result = await getPositionsPaginated(accountId, { page, page_size: pageSize })
      setData(result)
    } catch (error) {
      console.error('Failed to load positions:', error)
      toast.error('Failed to load positions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [accountId, page, pageSize])

  const totalPages = data?.total_pages || 0

  return (
    <Card className="h-full flex flex-col">
      <div className="flex-1 min-h-0 overflow-auto p-2 md:p-4">
        <div className="min-w-[640px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs md:text-sm">Symbol</TableHead>
                <TableHead className="text-xs md:text-sm">Name</TableHead>
                <TableHead className="text-xs md:text-sm">Quantity</TableHead>
                <TableHead className="text-xs md:text-sm">Available</TableHead>
                <TableHead className="text-xs md:text-sm">Avg Cost</TableHead>
                <TableHead className="text-xs md:text-sm">Last Price</TableHead>
                <TableHead className="text-xs md:text-sm">Market Value</TableHead>
                <TableHead className="text-xs md:text-sm">P/L</TableHead>
              </TableRow>
            </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8">
                  Loading...
                </TableCell>
              </TableRow>
            ) : data && data.items.length > 0 ? (
              data.items.map((position) => {
                const pl = position.last_price && position.market_value
                  ? position.market_value - (position.quantity * position.avg_cost)
                  : 0
                const plPercent = position.avg_cost > 0
                  ? ((position.last_price || 0) - position.avg_cost) / position.avg_cost * 100
                  : 0

                return (
                  <TableRow key={position.id}>
                    <TableCell className="font-medium">{position.symbol}</TableCell>
                    <TableCell>{position.name}</TableCell>
                    <TableCell>{position.quantity.toLocaleString()}</TableCell>
                    <TableCell>{position.available_quantity.toLocaleString()}</TableCell>
                    <TableCell>${position.avg_cost.toFixed(2)}</TableCell>
                    <TableCell>${position.last_price?.toFixed(2) || '-'}</TableCell>
                    <TableCell>${position.market_value?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '-'}</TableCell>
                    <TableCell className={pl >= 0 ? 'text-green-600' : 'text-red-600'}>
                      ${pl.toFixed(2)} ({plPercent >= 0 ? '+' : ''}{plPercent.toFixed(2)}%)
                    </TableCell>
                  </TableRow>
                )
              })
            ) : (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8 text-gray-500">
                  No positions found
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        </div>
      </div>

      <div className="flex-shrink-0 border-t p-2 md:p-4">
        <PaginationControls
          page={page}
          totalPages={totalPages}
          onPageChange={setPage}
          loading={loading}
        />
      </div>
    </Card>
  )
}

// Orders Table with Pagination
function OrdersTable({ accountId }: { accountId: number }) {
  const [data, setData] = useState<PaginatedResponse<Order> | null>(null)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)

  const loadData = async () => {
    try {
      setLoading(true)
      const result = await getOrdersPaginated(accountId, { page, page_size: pageSize })
      setData(result)
    } catch (error) {
      console.error('Failed to load orders:', error)
      toast.error('Failed to load orders')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [accountId, page, pageSize])

  const totalPages = data?.total_pages || 0

  return (
    <Card className="h-full flex flex-col">
      <div className="flex-1 min-h-0 overflow-auto p-2 md:p-4">
        <div className="min-w-[720px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs md:text-sm">Order No</TableHead>
                <TableHead className="text-xs md:text-sm">Time</TableHead>
                <TableHead className="text-xs md:text-sm">Symbol</TableHead>
                <TableHead className="text-xs md:text-sm">Side</TableHead>
                <TableHead className="text-xs md:text-sm">Type</TableHead>
                <TableHead className="text-xs md:text-sm">Price</TableHead>
                <TableHead className="text-xs md:text-sm">Quantity</TableHead>
                <TableHead className="text-xs md:text-sm">Filled</TableHead>
                <TableHead className="text-xs md:text-sm">Status</TableHead>
              </TableRow>
            </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-8">
                  Loading...
                </TableCell>
              </TableRow>
            ) : data && data.items.length > 0 ? (
              data.items.map((order) => (
                <TableRow key={order.id}>
                  <TableCell className="font-mono text-xs">{order.order_no}</TableCell>
                  <TableCell className="text-xs">
                    {new Date(order.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell className="font-medium">{order.symbol}</TableCell>
                  <TableCell>
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      order.side === 'BUY' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                    }`}>
                      {order.side}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs">{order.order_type}</TableCell>
                  <TableCell>${order.price?.toFixed(2) || '-'}</TableCell>
                  <TableCell>{order.quantity.toLocaleString()}</TableCell>
                  <TableCell>{order.filled_quantity.toLocaleString()}</TableCell>
                  <TableCell>
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      order.status === 'FILLED' ? 'bg-green-100 text-green-800' :
                      order.status === 'PENDING' ? 'bg-yellow-100 text-yellow-800' :
                      order.status === 'CANCELLED' ? 'bg-gray-100 text-gray-800' :
                      'bg-red-100 text-red-800'
                    }`}>
                      {order.status}
                    </span>
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-8 text-gray-500">
                  No orders found
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        </div>
      </div>

      <div className="flex-shrink-0 border-t p-2 md:p-4">
        <PaginationControls
          page={page}
          totalPages={totalPages}
          onPageChange={setPage}
          loading={loading}
        />
      </div>
    </Card>
  )
}

// Trades Table with Pagination
function TradesTable({ accountId }: { accountId: number }) {
  const [data, setData] = useState<PaginatedResponse<Trade> | null>(null)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)

  const loadData = async () => {
    try {
      setLoading(true)
      const result = await getTradesPaginated(accountId, { page, page_size: pageSize })
      setData(result)
    } catch (error) {
      console.error('Failed to load trades:', error)
      toast.error('Failed to load trades')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [accountId, page, pageSize])

  const totalPages = data?.total_pages || 0

  return (
    <Card className="h-full flex flex-col">
      <div className="flex-1 min-h-0 overflow-auto p-2 md:p-4">
        <div className="min-w-[640px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs md:text-sm">Time</TableHead>
                <TableHead className="text-xs md:text-sm">Symbol</TableHead>
                <TableHead className="text-xs md:text-sm">Side</TableHead>
                <TableHead className="text-xs md:text-sm">Price</TableHead>
                <TableHead className="text-xs md:text-sm">Quantity</TableHead>
                <TableHead className="text-xs md:text-sm">Amount</TableHead>
                <TableHead className="text-xs md:text-sm">Commission</TableHead>
              </TableRow>
            </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8">
                  Loading...
                </TableCell>
              </TableRow>
            ) : data && data.items.length > 0 ? (
              data.items.map((trade) => (
                <TableRow key={trade.id}>
                  <TableCell className="text-xs">
                    {new Date(trade.trade_time).toLocaleString()}
                  </TableCell>
                  <TableCell className="font-medium">{trade.symbol}</TableCell>
                  <TableCell>
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      trade.side === 'BUY' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                    }`}>
                      {trade.side}
                    </span>
                  </TableCell>
                  <TableCell>${trade.price.toFixed(2)}</TableCell>
                  <TableCell>{trade.quantity.toLocaleString()}</TableCell>
                  <TableCell>${(trade.price * trade.quantity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</TableCell>
                  <TableCell className="text-red-600">
                    ${trade.commission.toFixed(2)}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-gray-500">
                  No trades found
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        </div>
      </div>

      <div className="flex-shrink-0 border-t p-2 md:p-4">
        <PaginationControls
          page={page}
          totalPages={totalPages}
          onPageChange={setPage}
          loading={loading}
        />
      </div>
    </Card>
  )
}

// Reusable Pagination Controls
function PaginationControls({
  page,
  totalPages,
  onPageChange,
  loading
}: {
  page: number
  totalPages: number
  onPageChange: (page: number) => void
  loading: boolean
}) {
  return (
    <div className="flex flex-col md:flex-row items-center justify-between gap-2">
      <div className="text-xs md:text-sm text-gray-500">
        Page {page} of {totalPages || 1}
      </div>
      <div className="flex gap-1 md:gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(1)}
          disabled={page === 1 || loading}
          className="h-8 w-8 md:h-9 md:w-9 p-0"
        >
          <ChevronsLeft className="h-3 w-3 md:h-4 md:w-4" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1 || loading}
          className="h-8 w-8 md:h-9 md:w-9 p-0"
        >
          <ChevronLeft className="h-3 w-3 md:h-4 md:w-4" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages || loading}
          className="h-8 w-8 md:h-9 md:w-9 p-0"
        >
          <ChevronRight className="h-3 w-3 md:h-4 md:w-4" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(totalPages)}
          disabled={page >= totalPages || loading}
          className="h-8 w-8 md:h-9 md:w-9 p-0"
        >
          <ChevronsRight className="h-3 w-3 md:h-4 md:w-4" />
        </Button>
      </div>
    </div>
  )
}

// Reason Dialog Component
function ReasonDialog({
  reason,
  open,
  onClose
}: {
  reason: string | null
  open: boolean
  onClose: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle>AI Decision Reason</DialogTitle>
          <DialogDescription>
            Full explanation of the trading decision
          </DialogDescription>
        </DialogHeader>
        <div className="mt-4 p-4 bg-gray-50 rounded-lg overflow-auto max-h-[60vh]">
          <pre className="text-sm whitespace-pre-wrap font-mono">
            {reason || 'No reason provided'}
          </pre>
        </div>
      </DialogContent>
    </Dialog>
  )
}
