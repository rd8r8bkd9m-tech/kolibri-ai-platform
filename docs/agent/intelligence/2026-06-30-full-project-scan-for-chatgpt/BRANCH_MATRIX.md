# Branch Matrix

- Метод: `git ls-remote --heads origin` и `git clone --mirror "$(git remote get-url origin)"` во временный mirror clone.
- Checkout веток не выполнялся.
- Dirty-worktree checkout не выполнялся.
- Remote branch count: 93.
- Local heads: `main`, `agent/2026-06-30-full-project-scan-for-chatgpt/read-only-scan`.

## Группы веток

- `agent/*`: 41 ветка, в основном Telegram/task/generic implementation artifacts.
- `codex/*`: 36 веток, активная линия Codex feature/factory работ.
- `factory/*`: 14 веток, factory/control-plane/status/mobile/pdf/telegram работы.
- `main`: основная ветка.
- `p0/telegram-miniapp-kolibriai-deploy`: P0 ветка Telegram miniapp deploy.

## GitHub/auth/network classification

- `git ls-remote --heads origin`: success.
- Mirror clone через URL origin: success.
- Ошибка `fatal: repository 'origin' does not exist`: local command-form error от первой попытки `git clone --mirror origin ...`, не GitHub/auth/network failure.
- Fallback: локальные refs были доступны через `git for-each-ref refs/heads refs/remotes`; fallback не потребовался.
