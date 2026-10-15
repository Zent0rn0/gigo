// Запасной экран, если приложение не запустилось: скрипт не загрузился (обрыв сети, обновление сервера)
// или старый WebView не понимает код. Без него человек видел бы пустой белый экран.
(function () {
  setTimeout(function () {
    if (window.__gigoStarted) return;
    var root = document.getElementById('root');
    if (!root || root.children.length) return;
    var tg = window.Telegram && window.Telegram.WebApp;
    var dark = tg && tg.colorScheme ? tg.colorScheme === 'dark' : !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    var bg = (tg && tg.themeParams && tg.themeParams.bg_color) || (dark ? '#17212b' : '#ffffff');
    document.body.style.background = bg;
    root.innerHTML =
      '<div style="font-family:-apple-system,system-ui,Roboto,sans-serif;text-align:center;padding:64px 24px;color:' +
      (dark ? '#f2f0f7' : '#1c1b22') +
      '">' +
      '<div style="font-size:20px;font-weight:600;margin-bottom:8px">Не удалось запустить Gigo</div>' +
      '<div style="font-size:15px;opacity:.7;margin-bottom:24px">Проверьте интернет и попробуйте ещё раз. Если не помогает, обновите Telegram.</div>' +
      '<button type="button" onclick="location.reload()" style="font:inherit;font-size:16px;font-weight:600;border:0;border-radius:12px;padding:12px 24px;background:#8A2BF7;color:#fff">Перезапустить</button>' +
      '</div>';
  }, 15000);
})();
