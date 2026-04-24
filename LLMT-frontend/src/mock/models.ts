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
  { version: 'v3.2.0', status: '当前版本', date: '2024-01-15 14:30', metrics: '准确率 94.5% · 延迟 45ms · 1.25M样本', params: 'lr=2e-5, batch=32, epochs=10, warmup=1000, weight_decay=0.01', current: true },
  { version: 'v3.1.0', status: '稳定版本', date: '2024-01-12 09:15', metrics: '准确率 93.8% · 延迟 42ms · 1.0M样本', params: 'lr=3e-5, batch=32, epochs=8, warmup=500, weight_decay=0.01' },
  { version: 'v3.0.0', status: '', date: '2024-01-08 16:45', metrics: '准确率 92.1% · 延迟 40ms · 800K样本', params: 'lr=5e-5, batch=16, epochs=5, warmup=200, weight_decay=0.02' },
  { version: 'v2.0.0', status: '', date: '2024-01-01 10:00', metrics: '准确率 89.5% · 延迟 38ms · 500K样本', params: 'lr=1e-4, batch=16, epochs=3, warmup=100, weight_decay=0.05' },
]

export const performanceTrend = [89.5, 92.1, 93.8, 94.5]
