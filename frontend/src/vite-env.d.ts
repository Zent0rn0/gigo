/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_YANDEX_MAPS_KEY?: string;
  readonly VITE_MOCK?: string;
  /** Имя бота без @: ссылки «Поделиться» вида t.me/<бот>?startapp=job_42. */
  readonly VITE_BOT_USERNAME?: string;
  /** Короткое имя Mini App из BotFather (необязательно): t.me/<бот>/<имя>?startapp=… */
  readonly VITE_MINIAPP_NAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
