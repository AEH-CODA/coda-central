import { Bar, Pie, Doughnut } from 'react-chartjs-2'
import { chartColors, primaryChartColor } from '@/lib/chartColors'

const baseOptions = {
  responsive: true,
  maintainAspectRatio: true,
  plugins: { legend: { display: false } },
}

/**
 * Categorical charts: 2-4 categories -> pie, 5-6 -> doughnut, 7+ -> bar.
 * Skewed distributions (max/min ratio >= 10:1) always fall back to bar,
 * since pie/doughnut slices become illegible at that skew.
 */
function decideCategoricalChartType(column) {
  const unique = column.unique_values || 0
  if (unique < 2) return 'bar'

  const counts = column.distribution.counts || []
  if (counts.length > 0) {
    const max = Math.max(...counts)
    const min = Math.min(...counts)
    const ratio = min > 0 ? max / min : Infinity
    if (ratio >= 10) return 'bar'
  }

  if (unique <= 4) return 'pie'
  if (unique <= 6) return 'doughnut'
  return 'bar'
}

function percentTooltip(context) {
  const total = context.dataset.data.reduce((sum, value) => sum + value, 0)
  const percentage = total > 0 ? ((context.parsed / total) * 100).toFixed(1) : '0'
  return `${context.label}: ${context.parsed} (${percentage}%)`
}

export function DistributionChart({ column }) {
  if (!column.distribution) return null

  if (column.dtype === 'numeric') {
    const data = {
      labels: column.distribution.bins ?? [],
      datasets: [
        {
          label: 'Frequency',
          data: column.distribution.counts ?? [],
          backgroundColor: `${primaryChartColor}99`,
          borderColor: primaryChartColor,
          borderWidth: 1,
          borderRadius: 3,
        },
      ],
    }
    return (
      <Bar
        data={data}
        options={{ ...baseOptions, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } }}
        height={140}
      />
    )
  }

  if (column.dtype === 'categorical') {
    const chartType = decideCategoricalChartType(column)
    const categories = column.distribution.categories ?? []
    const counts = column.distribution.counts ?? []

    if (chartType === 'bar') {
      const data = {
        labels: categories,
        datasets: [
          {
            label: 'Count',
            data: counts,
            backgroundColor: `${primaryChartColor}99`,
            borderColor: primaryChartColor,
            borderWidth: 1,
            borderRadius: 3,
          },
        ],
      }
      return (
        <Bar
          data={data}
          options={{
            ...baseOptions,
            scales: {
              x: { ticks: { autoSkip: false, maxRotation: 45, minRotation: 45, font: { size: 10 } } },
              y: { beginAtZero: true },
            },
          }}
          height={140}
        />
      )
    }

    const data = {
      labels: categories,
      datasets: [{ data: counts, backgroundColor: chartColors, borderColor: '#fff', borderWidth: 2 }],
    }
    const options = {
      ...baseOptions,
      plugins: {
        legend: { display: true, position: 'right', labels: { padding: 10, font: { size: 11 } } },
        tooltip: { callbacks: { label: percentTooltip } },
      },
    }
    return chartType === 'pie' ? (
      <Pie data={data} options={options} height={140} />
    ) : (
      <Doughnut data={data} options={options} height={140} />
    )
  }

  return null
}
