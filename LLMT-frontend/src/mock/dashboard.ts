export const dashboardMetrics = [
  { title: 'GPU显存', value: '78.5%', progress: 78.5, color: '#f59e0b', bg: '#fed7aa' },
  { title: '通信延迟', value: '2.3ms', progress: 23, color: '#10b981', bg: '#d1fae5' },
  { title: '训练进度', value: '45%', progress: 45, color: '#2563eb', bg: '#dbeafe' },
  { title: '运行任务', value: '3', progress: 60, color: '#8b5cf6', bg: '#e9d5ff' },
]

export const trainingTasks = [
  { name: 'BERT情感分析微调', meta: 'Epoch 45/100 · Loss: 0.0234', progress: 45, type: 'success' as const },
  { name: 'ResNet图像分类', meta: 'Epoch 78/100 · Loss: 0.0089', progress: 78, type: 'success' as const },
  { name: 'GPT文本生成', meta: '排队中 · 预计等待 2小时', progress: 0, type: 'warning' as const },
  { name: 'Whisper语音识别', meta: 'Epoch 12/50 · Loss: 0.0567', progress: 24, type: 'success' as const },
]

export const recentActivities = [
  { text: 'ResNet-50-v2 训练完成', time: '30分钟前', color: '#10b981' },
  { text: '用户评论数据导入成功', time: '1小时前', color: '#2563eb' },
  { text: 'GPU使用率达到 85%', time: '2小时前', color: '#f59e0b' },
  { text: '新用户 张三 加入项目', time: '3小时前', color: '#06b6d4' },
  { text: 'Whisper模型训练完成', time: '5小时前', color: '#8b5cf6' },
  { text: 'YOLO检测任务已部署', time: '6小时前', color: '#f59e0b' },
]

export const lossSeries = [0.49, 0.41, 0.35, 0.27, 0.21, 0.17, 0.12, 0.09, 0.056, 0.023]
export const gpuSeries = [62, 68, 73, 76, 75, 80, 82, 79, 78, 81]
export const latencySeries = [2.1, 2.4, 2.2, 2.8, 2.3, 2.0, 2.5, 2.7, 2.2, 2.3]
