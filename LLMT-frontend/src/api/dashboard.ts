import {
  dashboardMetrics,
  gpuSeries,
  latencySeries,
  lossSeries,
  recentActivities,
  trainingTasks,
} from '@/mock/dashboard'

export const getDashboardMock = () =>
  Promise.resolve({
    dashboardMetrics,
    gpuSeries,
    latencySeries,
    lossSeries,
    recentActivities,
    trainingTasks,
  })
