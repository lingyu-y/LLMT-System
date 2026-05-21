export const models = [
  { id: 'bert', name: 'BERT-Sentiment', type: 'NLP · 文本分类', version: 'v3.2.0', accuracy: '94.5%', params: '110M', color: 'linear-gradient(135deg, #3b82f6, #2563eb)' },
  { id: 'resnet', name: 'ResNet-Classifier', type: 'CV · 图像分类', version: 'v2.1.0', accuracy: '97.8%', params: '25.6M', color: 'linear-gradient(135deg, #10b981, #059669)' },
  { id: 'gpt', name: 'GPT-Generator', type: 'NLP · 文本生成', version: 'v1.5.0', accuracy: '89.2%', params: '355M', color: 'linear-gradient(135deg, #8b5cf6, #7c3aed)' },
  { id: 'whisper', name: 'Whisper-ASR', type: 'Audio · 语音识别', version: 'v2.3.0', accuracy: '96.7%', params: '244M', color: 'linear-gradient(135deg, #f59e0b, #d97706)' },
  { id: 'yolo', name: 'YOLO-Detector', type: 'CV · 目标检测', version: 'v4.0.0', accuracy: '91.3%', params: '61M', color: 'linear-gradient(135deg, #06b6d4, #0891b2)' },
  { id: 'layout', name: 'LayoutLMv3', type: 'MultiModal · 文档理解', version: 'v2.0.0', accuracy: '93.2%', params: '133M', color: 'linear-gradient(135deg, #64748b, #475569)' },
]

export const modelParams = [
  ['学习率', '2e-5'],
  ['批次大小', '32'],
  ['训练轮次', '10'],
  ['预热步数', '1000'],
  ['权重衰减', '0.01'],
  ['优化器', 'AdamW'],
]

export const versionHistory = [
  { version: 'v3.2.0', status: '当前版本', date: '2024-01-15 14:30', metrics: '准确率 94.5% · 延迟 45ms · 1.25M样本', params: '框架 DeepSpeed · 4x A100 · 数据并行 + 流水线并行', training: '来源任务 TR-20260425-01 · 数据集 电商评论文本数据 v2.3', current: true },
  { version: 'v3.1.0', status: '稳定版本', date: '2024-01-12 09:15', metrics: '准确率 93.8% · 延迟 42ms · 1.0M样本', params: '框架 DeepSpeed · 4x A100 · 数据并行', training: '来源任务 TR-20260412-04 · 数据集 电商评论文本数据 v2.1' },
  { version: 'v3.0.0', status: '', date: '2024-01-08 16:45', metrics: '准确率 92.1% · 延迟 40ms · 800K样本', params: '框架 PyTorch · 2x A100 · 数据并行', training: '来源任务 TR-20260408-03 · 数据集 电商评论文本数据 v1.8' },
  { version: 'v2.0.0', status: '', date: '2024-01-01 10:00', metrics: '准确率 89.5% · 延迟 38ms · 500K样本', params: '框架 PyTorch · 1x A100 · 数据并行', training: '来源任务 TR-20260401-01 · 数据集 电商评论文本数据 v1.0' },
]

export const performanceTrend = [89.5, 92.1, 93.8, 94.5]
