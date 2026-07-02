import { createApp } from 'vue'
import '@picocss/pico/css/pico.min.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(router)
app.mount('#app')
