const { app, BrowserWindow } = require('electron');
const path = require('path');
const isDev = require('electron-is-dev');

// ФОРСИРУЕМ АППАРАТНОЕ УСКОРЕНИЕ WEBGPU (Ring 0 GPU Access)
app.commandLine.appendSwitch('enable-unsafe-webgpu');
app.commandLine.appendSwitch('enable-features', 'Vulkan,VulkanFromANGLE,DefaultANGLEVulkan');
app.commandLine.appendSwitch('ignore-gpu-blocklist');
// Отключаем ограничение FPS для максимальной производительности
app.commandLine.appendSwitch('disable-frame-rate-limit');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 768,
    backgroundColor: '#020202', // Черный фон в стиле киберпанк
    frame: false, // Отключаем стандартную рамку Windows/Mac
    titleBarStyle: 'hidden', // Скрываем верхнюю полосу
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      webgl: true, // Включаем поддержку 3D (GPU) для Deck.GL
    }
  });

  // В режиме разработки грузим с localhost, в проде — из собранных статических файлов
  const startUrl = isDev
    ? 'http://localhost:3000'
    : `file://${path.join(__dirname, '../build/index.html')}`;

  mainWindow.loadURL(startUrl);

  if (isDev) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
