import { useState } from 'react'
import { useNavigate } from 'react-router'
import { auth, setAuthToken, type AuthUser } from '@/lib/api'
import AnimatedMascot from '@/components/AnimatedMascot'

interface LoginPageProps {
  onLogin: (user: AuthUser) => void
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = mode === 'login'
        ? await auth.login(email, password)
        : await auth.register(email, name, password)
      setAuthToken(res.access_token)
      onLogin(res.user)
      navigate('/')
    } catch {
      setError(mode === 'login' ? 'Неверный email или пароль' : 'Ошибка регистрации')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center justify-center min-h-[100dvh] px-4 bg-[var(--bg-primary)]">
      <div className="w-full max-w-[380px]">
        <div className="text-center mb-8">
          <AnimatedMascot state="ready" size={64} className="mx-auto mb-4" />
          <h1 className="text-[22px] font-semibold text-[var(--text-primary)]">Колибри</h1>
          <p className="text-[14px] text-[var(--text-secondary)] mt-1">
            {mode === 'login' ? 'Войдите в аккаунт' : 'Создайте аккаунт'}
          </p>
        </div>

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
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="email@example.com"
              className="w-full h-10 px-3 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[14px] outline-none focus:border-[var(--accent-teal)] transition-colors"
              required
            />
          </div>
          <div>
            <label className="block text-[12px] text-[var(--text-tertiary)] mb-1">Пароль</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Минимум 6 символов"
              className="w-full h-10 px-3 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[14px] outline-none focus:border-[var(--accent-teal)] transition-colors"
              required
              minLength={6}
            />
          </div>

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

        <p className="text-center text-[13px] text-[var(--text-tertiary)] mt-4">
          {mode === 'login' ? 'Нет аккаунта? ' : 'Уже есть аккаунт? '}
          <button
            onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
            className="text-[var(--accent-teal)] hover:underline"
          >
            {mode === 'login' ? 'Зарегистрироваться' : 'Войти'}
          </button>
        </p>
      </div>
    </div>
  )
}
