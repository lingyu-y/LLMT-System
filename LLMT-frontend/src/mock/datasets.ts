export const datasetStats = [
  { title: '数据集总数', value: 12 },
  { title: '数据总量', value: '2.8 TB' },
  { title: '处理中', value: 3 },
  { title: '已完成', value: 9 },
]

export const datasets = [
  { name: '电商评论文本数据', type: '文本', samples: '1,250,000', size: '2.4 GB', status: '已完成', statusType: 'success' as const, createdAt: '2024-01-15' },
  { name: '产品图像分类集', type: '图像', samples: '125,000', size: '15.6 GB', status: '已完成', statusType: 'success' as const, createdAt: '2024-01-14' },
  { name: '语音指令识别数据', type: '音频', samples: '32,000', size: '8.2 GB', status: '处理中', statusType: 'info' as const, createdAt: '2024-01-14' },
  { name: '用户行为日志数据', type: '文本', samples: '5,800,000', size: '12.3 GB', status: '已完成', statusType: 'success' as const, createdAt: '2024-01-13' },
  { name: '医学影像数据集', type: '图像', samples: '45,000', size: '28.5 GB', status: '处理中', statusType: 'info' as const, createdAt: '2024-01-12' },
]

export const processingJobs = [
  { name: '语音指令识别数据', percent: 68, detail: '已处理: 21,760 / 32,000 样本', color: 'blue' },
  { name: '医学影像数据集', percent: 35, detail: '已处理: 15,750 / 45,000 样本', color: 'orange' },
  { name: '视频片段数据', percent: 12, detail: '已处理: 2,400 / 20,000 样本', color: 'green' },
]
