import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import { createApp } from 'vue';
import App from './App.vue';
import { router } from './router';
import { requestHealth } from './services/http';
import { pinia } from './stores';
import './styles/tokens.css';
import './styles/base.css';
import './styles/utilities.css';

const app = createApp(App);
app.use(ElementPlus).use(pinia).use(router).mount('#app');
if (import.meta.env.DEV)
  void requestHealth().catch((error: unknown) => {
    console.warn('[LearnPilot] Backend health check failed.', error);
  });
