import { Bar } from 'react-chartjs-2'
import { primaryChartColor } from '@/lib/chartColors'

export function PatientAppearanceChart({ distribution }) {
  const data = {
    labels: distribution.labels,
    datasets: [{ data: distribution.counts, backgroundColor: primaryChartColor, borderRadius: 4 }],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: () => null,
          afterLabel: (context) => `${context.parsed.y} patient${context.parsed.y !== 1 ? 's' : ''}`,
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { stepSize: 1, font: { size: 10 } },
        title: { display: true, text: 'Number of Patients', font: { size: 11, weight: 'bold' } },
      },
      x: {
        ticks: { font: { size: 10 } },
        title: { display: true, text: 'Number of Rows', font: { size: 11, weight: 'bold' } },
      },
    },
  }

  return (
    <div className="max-w-full overflow-x-auto">
      <Bar data={data} options={options} height={100} />
    </div>
  )
}
