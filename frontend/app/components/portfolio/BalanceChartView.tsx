import { useState, useEffect } from 'react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ChartOptions
} from 'chart.js'
import { getBalanceHistory, BalanceHistoryPoint } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import { toast } from 'react-hot-toast'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

type TimeRange = '24h' | '1w' | '30d' | 'all'
type Interval = '6m' | '1h' | '1d'

interface BalanceChartViewProps {
  accountId: number
}

export default function BalanceChartView({ accountId }: BalanceChartViewProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>('24h')
  const [interval, setInterval] = useState<Interval>('6m')
  const [data, setData] = useState<BalanceHistoryPoint[]>([])
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [endTime, setEndTime] = useState<string | undefined>(undefined)

  const timeRangeLabels: Record<TimeRange, string> = {
    '24h': '24 Hours',
    '1w': '1 Week',
    '30d': '30 Days',
    'all': 'All Time'
  }

  const intervalLabels: Record<Interval, string> = {
    '6m': '6 Minutes',
    '1h': '1 Hour',
    '1d': '1 Day'
  }

  const loadData = async (append: boolean = false) => {
    try {
      setLoading(true)
      const result = await getBalanceHistory({
        account_id: accountId,
        time_range: timeRange,
        interval: interval,
        end_time: append ? endTime : undefined,
        limit: 100
      })

      if (append) {
        // 加载历史数据（左侧）
        setData(prev => [...result.data, ...prev])
      } else {
        // 重新加载
        setData(result.data)
      }

      setHasMore(result.has_more)
      if (result.next_end_time) {
        setEndTime(result.next_end_time)
      }
    } catch (error) {
      console.error('Failed to load balance history:', error)
      toast.error('Failed to load chart data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setEndTime(undefined)
    loadData(false)
  }, [accountId, timeRange, interval])

  const handleLoadMore = () => {
    if (hasMore && !loading) {
      loadData(true)
    }
  }

  const handleRefresh = () => {
    setEndTime(undefined)
    loadData(false)
  }

  const chartData = {
    labels: data.map(point => {
      const date = new Date(point.timestamp)
      if (interval === '6m' || interval === '1h') {
        return date.toLocaleString('en-US', { 
          month: 'short', 
          day: 'numeric', 
          hour: '2-digit', 
          minute: '2-digit' 
        })
      } else {
        return date.toLocaleDateString('en-US', { 
          month: 'short', 
          day: 'numeric' 
        })
      }
    }),
    datasets: [
      {
        label: 'Total Balance (USDT)',
        data: data.map(point => point.total_balance),
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        tension: 0.4,
        fill: true,
      },
    ],
  }

  const options: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: `Account Balance History - ${timeRangeLabels[timeRange]} (${intervalLabels[interval]})`,
        font: {
          size: 16,
          weight: 'bold'
        }
      },
      tooltip: {
        callbacks: {
          label: function(context) {
            let label = context.dataset.label || ''
            if (label) {
              label += ': '
            }
            if (context.parsed.y !== null) {
              label += new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 2
              }).format(context.parsed.y)
            }
            return label
          }
        }
      }
    },
    scales: {
      y: {
        beginAtZero: false,
        ticks: {
          callback: function(value) {
            return '$' + Number(value).toLocaleString()
          }
        }
      },
      x: {
        ticks: {
          maxRotation: 45,
          minRotation: 45
        }
      }
    }
  }

  return (
    <div className="h-full flex flex-col space-y-2 md:space-y-4 w-full">
      {/* 控制面板 */}
      <Card className="p-2 md:p-4">
        <div className="flex flex-col gap-3 md:gap-4">
          {/* 时间范围选择 */}
          <div className="flex flex-wrap gap-1 md:gap-2 items-center">
            <span className="text-xs md:text-sm font-medium mr-1 md:mr-2">Time:</span>
            {(['24h', '1w', '30d', 'all'] as TimeRange[]).map(range => (
              <Button
                key={range}
                variant={timeRange === range ? 'default' : 'outline'}
                size="sm"
                onClick={() => setTimeRange(range)}
                disabled={loading}
                className="h-7 md:h-9 text-xs md:text-sm px-2 md:px-3"
              >
                {timeRangeLabels[range]}
              </Button>
            ))}
          </div>

          {/* 时间周期和操作按钮 */}
          <div className="flex flex-wrap gap-1 md:gap-2 items-center justify-between">
            <div className="flex gap-1 md:gap-2 items-center">
              <span className="text-xs md:text-sm font-medium mr-1 md:mr-2">Interval:</span>
              {(['6m', '1h', '1d'] as Interval[]).map(int => (
                <Button
                  key={int}
                  variant={interval === int ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setInterval(int)}
                  disabled={loading}
                  className="h-7 md:h-9 text-xs md:text-sm px-2 md:px-3"
                >
                  {intervalLabels[int]}
                </Button>
              ))}
            </div>

            {/* 操作按钮 */}
            <div className="flex gap-1 md:gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleLoadMore}
                disabled={!hasMore || loading}
                title="Load historical data"
                className="h-7 md:h-9 text-xs md:text-sm px-2 md:px-3"
              >
                <ArrowLeft className="h-3 w-3 md:h-4 md:w-4 md:mr-1" />
                <span className="hidden md:inline">Load More</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleRefresh}
                disabled={loading}
                className="h-7 md:h-9 px-2 md:px-3"
              >
                <RefreshCw className={`h-3 w-3 md:h-4 md:w-4 ${loading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </div>
        </div>
      </Card>

      {/* 图表区域 */}
      <Card className="flex-1 p-2 md:p-4 min-h-0">
        {loading && data.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <RefreshCw className="h-6 w-6 md:h-8 md:w-8 animate-spin mx-auto mb-2 text-gray-400" />
              <p className="text-xs md:text-sm text-gray-500">Loading chart data...</p>
            </div>
          </div>
        ) : data.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <p className="text-xs md:text-sm text-gray-500">No data available for selected time range</p>
              <p className="text-xs text-gray-400 mt-2">Try selecting a different time range or interval</p>
            </div>
          </div>
        ) : (
          <div className="h-full w-full">
            <Line data={chartData} options={options} />
          </div>
        )}
      </Card>

      {/* 提示信息 */}
      {hasMore && !loading && (
        <div className="text-xs text-gray-500 text-center pb-2">
          <ArrowLeft className="inline h-3 w-3 mr-1" />
          Click Load More to see historical data
        </div>
      )}
    </div>
  )
}
