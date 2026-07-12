const { app, BrowserWindow } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 800,
    webPreferences: {
      nodeIntegration: true,
    }
  });

  // Trỏ vào file index.html từ Vibe Code của bạn
  mainWindow.loadFile('index.html'); 

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

app.on('ready', () => {
  createWindow();
  // Khởi chạy tiến trình kiểm tra cập nhật ngầm khi mở app
  autoUpdater.checkForUpdatesAndNotify();
});

// Khi có bản cập nhật mới, tự động tải về và báo cho khách
autoUpdater.on('update-downloaded', () => {
  autoUpdater.quitAndInstall(); // Tự đóng app cũ và cài bản mới đè lên
});