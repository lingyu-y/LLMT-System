// import { createApp } from 'vue'
// import { createPinia } from 'pinia'

// import App from './App.vue'
// import router from './router'

// const app = createApp(App)

// app.use(createPinia())
// app.use(router)

// app.mount('#app')

import { createApp } from 'vue'
import { createPinia } from 'pinia'

// 1. 引入 Element Plus 的核心库
import ElementPlus from 'element-plus'
// 2. 引入 Element Plus 的全局样式文件（必须引入，否则没样式）
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 3. 把 Element Plus 挂载到 Vue 实例上
app.use(ElementPlus)

app.mount('#app')
