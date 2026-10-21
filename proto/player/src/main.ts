import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';
import { player } from './lib/player.svelte';
import { view } from './lib/view.svelte';

// Solo en desarrollo: permite que las pruebas automáticas lean el reproductor.
if (import.meta.env.DEV) Object.assign(window, { __player: player, __view: view });

mount(App, { target: document.getElementById('app')! });
