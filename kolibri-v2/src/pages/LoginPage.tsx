import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { ArrowLeft, CheckCircle2, Mail } from 'lucide-react'
import { ApiError, auth, type AuthUser } from '@/lib/api'
import CartoonMascot from '@/components/CartoonMascot'

interface LoginPageProps {
  onLogin: (user: AuthUser) => void
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const resetToken = useMemo(() => searchParams.get('reset_token')?.trim() ?? '', [searchParams])
  const [mode, setMode] = useState<'login' | 'register' | 'recover' | 'reset'>(
    resetToken ? 'reset' : 'login',
  )
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setNotice('')
    setLoading(true)
    try {
      if (mode === 'recover') {
        const result = await auth.requestPasswordReset(email)
        setNotice(result.message)
        return
      }
      if (mode === 'reset') {
        if (!resetToken) {
          setError('Ссылка восстановления неполная. Запросите новую.')
          return
        }
        if (password !== passwordConfirmation) {
          setError('Пароли не совпадают')
          return
        }
        await auth.confirmPasswordReset(resetToken, password)
        setSearchParams({}, { replace: true })
        setPassword('')
        setPasswordConfirmation('')
        setMode('login')
        setNotice('Пароль изменён. Теперь войдите с новым паролем.')
        return
      }
      const res = mode === 'login'
        ? await auth.login(email, password)
        : await auth.register(email, name, password)
      onLogin(res.user)
      navigate('/app')
    } catch (caught) {
      if (caught instanceof ApiError && caught.detail) {
        setError(caught.detail)
      } else {
        setError(
          mode === 'login'
            ? 'Неверный email или пароль'
            : mode === 'register'
              ? 'Ошибка регистрации'
              : 'Не удалось выполнить запрос. Повторите позже.',
        )
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center justify-center min-h-[100dvh] px-4 bg-[var(--bg-primary)]">
      <div className="w-full max-w-[380px]">
        <div className="text-center mb-8">
          <CartoonMascot state="ready" size={64} className="mx-auto mb-4" />
          <h1 className="text-[22px] font-semibold text-[var(--text-primary)]">Колибри</h1>
          <p className="text-[14px] text-[var(--text-secondary)] mt-1">
            {mode === 'login'
              ? 'Войдите в аккаунт'
              : mode === 'register'
                ? 'Создайте аккаунт'
                : mode === 'reset'
                  ? 'Новый пароль'
                  : 'Восстановление доступа'}
          </p>
        </div>

        {mode === 'recover' || mode === 'reset' ? (
          <section
            aria-labelledby="password-recovery-title"
            className="auth-recovery-card"
          >
            <button
              type="button"
              onClick={() => {
                setSearchParams({}, { replace: true })
                setMode('login')
                setError('')
                setNotice('')
              }}
              className="auth-back-button"
            >
              <ArrowLeft size={18} aria-hidden="true" />
              Назад ко входу
            </button>
            <h2 id="password-recovery-title" className="text-[18px] font-semibold text-[var(--text-primary)]">
              {mode === 'reset' ? 'Задайте новый пароль' : 'Забыли пароль?'}
            </h2>
            <p className="mt-2 text-[14px] leading-6 text-[var(--text-secondary)]">
              {mode === 'reset'
                ? 'Ссылка одноразовая. После сохранения старый пароль перестанет работать.'
                : 'Укажите email аккаунта. Мы отправим одноразовую ссылку, действующую 30 минут.'}
            </p>
            <form className="mt-5 space-y-3" onSubmit={handleSubmit}>
              {mode === 'recover' ? (
                <label className="auth-field">
                  <span>Email</span>
                  <div className="auth-input-shell">
                    <Mail size={18} aria-hidden="true" />
                    <input
                      type="email"
                      name="recovery-email"
                      autoComplete="email"
                      value={email}
                      onChange={event => setEmail(event.target.value)}
                      placeholder="email@example.com"
                      required
                    />
                  </div>
                </label>
              ) : (
                <>
                  <label className="auth-field">
                    <span>Новый пароль</span>
                    <input
                      type="password"
                      name="new-password"
                      autoComplete="new-password"
                      value={password}
                      onChange={event => setPassword(event.target.value)}
                      minLength={8}
                      placeholder="Минимум 8 символов"
                      required
                    />
                  </label>
                  <label className="auth-field">
                    <span>Повторите пароль</span>
                    <input
                      type="password"
                      name="new-password-confirmation"
                      autoComplete="new-password"
                      value={passwordConfirmation}
                      onChange={event => setPasswordConfirmation(event.target.value)}
                      minLength={8}
                      placeholder="Ещё раз"
                      required
                    />
                  </label>
                </>
              )}

              {error && <p className="auth-form-message is-error" role="alert">{error}</p>}
              {notice && (
                <p className="auth-form-message is-success" role="status">
                  <CheckCircle2 size={17} aria-hidden="true" />
                  {notice}
                </p>
              )}

              <button type="submit" disabled={loading || Boolean(notice)} className="auth-primary-button">
                {loading
                  ? 'Отправляем…'
                  : mode === 'reset'
                    ? 'Сохранить новый пароль'
                    : notice
                      ? 'Письмо отправлено'
                      : 'Отправить ссылку'}
              </button>
            </form>
          </section>
        ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          {mode === 'register' && (
            <div>
              <label className="block text-[12px] text-[var(--text-tertiary)] mb-1">Имя</label>
              <input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Ваше имя"
                className="w-full h-10 px-3 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[14px] outline-none focus:border-[var(--accent-teal)] transition-colors"
                required
              />
            </div>
          )}
          <div>
            <label className="block text-[12px] text-[var(--text-tertiary)] mb-1">Email</label>
            <input
              type="email"
              name="email"
              autoComplete="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="email@example.com"
              className="w-full h-10 px-3 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[14px] outline-none focus:border-[var(--accent-teal)] transition-colors"
              required
            />
          </div>
          <div>
            <div className="mb-1 flex items-center justify-between gap-3">
              <label className="block text-[12px] text-[var(--text-tertiary)]">Пароль</label>
              {mode === 'login' && (
                <button
                  type="button"
                  onClick={() => { setMode('recover'); setError('') }}
                  className="min-h-8 text-[12px] font-medium text-[var(--accent-teal)] hover:underline"
                >
                  Забыли пароль?
                </button>
              )}
            </div>
            <input
              type="password"
              name="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Минимум 6 символов"
              className="w-full h-10 px-3 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[14px] outline-none focus:border-[var(--accent-teal)] transition-colors"
              required
              minLength={6}
            />
          </div>

          {notice && (
            <p className="auth-form-message is-success" role="status">
              <CheckCircle2 size={17} aria-hidden="true" />
              {notice}
            </p>
          )}
          {error && (
            <p className="text-[13px] text-[var(--status-error)] text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full h-10 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[14px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors disabled:opacity-50"
          >
            {loading ? 'Загрузка...' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'}
          </button>
        </form>
        )}

        {mode !== 'recover' && (
        <p className="text-center text-[13px] text-[var(--text-tertiary)] mt-4">
          {mode === 'login' ? 'Нет аккаунта? ' : 'Уже есть аккаунт? '}
          <button
            onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
            className="text-[var(--accent-teal)] hover:underline"
          >
            {mode === 'login' ? 'Зарегистрироваться' : 'Войти'}
          </button>
        </p>
        )}
      </div>
    </div>
  )
}
