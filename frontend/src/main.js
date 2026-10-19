import { createApp } from 'vue'
import App from './App.vue'
import { projectName } from './app-config.js'
import './style.css'
// Les adaptations doivent suivre les styles généraux.
import './account-history.css'
import './identity.css'

document.title = projectName
createApp(App).mount('#app')
