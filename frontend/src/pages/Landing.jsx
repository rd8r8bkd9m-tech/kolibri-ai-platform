import { useState, useEffect } from "react"
import { motion } from "framer-motion"
import { KolibriBird } from "../components/KolibriBird"

const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
  ? `http://${window.location.hostname}:8000`
  : ""

function Header() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener("scroll", onScroll)
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  const navItems = [
    { href: "#features", label: "Возможности" },
    { href: "#how-it-works", label: "Как работает" },
    { href: "#for-whom", label: "Для кого" },
    { href: "#documents", label: "Документы" },
  ]

  return (
    <header className={`landing-header ${scrolled ? "scrolled" : ""}`}>
      <div className="landing-header-inner">
        <a href="/" className="header-logo">
          <KolibriBird size={32} state="idle" />
          <span className="header-logo-text">Kolibri</span>
        </a>

        <nav className="header-nav desktop-only">
          {navItems.map(item => (
            <a key={item.href} href={item.href} className="header-nav-link">{item.label}</a>
          ))}
        </nav>

        <div className="header-actions desktop-only">
          <a href="/app" className="btn btn-ghost">Войти</a>
          <a href="/app" className="btn btn-primary">Открыть Kolibri</a>
        </div>

        <button 
          className="mobile-menu-btn mobile-only"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Меню"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            {mobileMenuOpen ? (
              <path d="M18 6L6 18M6 6l12 12" />
            ) : (
              <path d="M3 12h18M3 6h18M3 18h18" />
            )}
          </svg>
        </button>
      </div>

      {mobileMenuOpen && (
        <motion.div 
          className="mobile-menu mobile-only"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
        >
          {navItems.map(item => (
            <a 
              key={item.href} 
              href={item.href} 
              className="mobile-nav-link"
              onClick={() => setMobileMenuOpen(false)}
            >
              {item.label}
            </a>
          ))}
          <div className="mobile-menu-actions">
            <a href="/app" className="btn btn-ghost">Войти</a>
            <a href="/app" className="btn btn-primary">Открыть Kolibri</a>
          </div>
        </motion.div>
      )}
    </header>
  )
}

function Hero() {
  return (
    <section className="hero-section">
      <div className="container hero-container">
        <div className="hero-content">
          <motion.h1 
            className="hero-title"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            Смета и строительные документы из одного описания
          </motion.h1>
          
          <motion.p 
            className="hero-subtitle"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
          >
            Опишите объект или загрузите данные — Kolibri сформирует структурированную смету, 
            покажет источники цен и допущения, позволит редактировать расчёт и создаст связанные документы.
          </motion.p>

          <motion.div 
            className="hero-cta"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
          >
            <a href="/app" className="btn btn-primary btn-lg">Создать смету</a>
            <a href="#how-it-works" className="btn btn-ghost btn-lg">Посмотреть, как работает</a>
          </motion.div>

          <motion.div 
            className="hero-trust"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.3 }}
          >
            <span className="trust-item">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20,6 9,17 4,12" />
              </svg>
              Редактируемые расчёты
            </span>
            <span className="trust-item">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20,6 9,17 4,12" />
              </svg>
              Источники цен
            </span>
            <span className="trust-item">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20,6 9,17 4,12" />
              </svg>
              Версии документов
            </span>
            <span className="trust-item">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20,6 9,17 4,12" />
              </svg>
              Экспорт PDF/XLSX
            </span>
          </motion.div>
        </div>

        <motion.div 
          className="hero-preview"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
        >
          <div className="preview-card">
            <div className="preview-header">
              <div className="preview-user-request">
                <span className="user-avatar">У</span>
                <span className="user-text">Дом 109 м² в Альметьевске. Монолитная плита, кирпичные стены, мягкая кровля, инженерные сети и отделка</span>
              </div>
            </div>
            
            <div className="preview-body">
              <div className="estimate-preview">
                <div className="estimate-row estimate-header">
                  <span className="col-name">Наименование</span>
                  <span className="col-unit">Ед.</span>
                  <span className="col-qty">Кол-во</span>
                  <span className="col-price">Цена</span>
                  <span className="col-total">Сумма</span>
                </div>
                
                <div className="estimate-row">
                  <span className="col-name">Подготовка основания</span>
                  <span className="col-unit">м²</span>
                  <span className="col-qty">109</span>
                  <span className="col-price">450 ₽</span>
                  <span className="col-total">49 050 ₽</span>
                </div>
                
                <div className="estimate-row">
                  <span className="col-name">Монолитная плита фундамента</span>
                  <span className="col-unit">м³</span>
                  <span className="col-qty">32.7</span>
                  <span className="col-price">12 500 ₽</span>
                  <span className="col-total">408 750 ₽</span>
                </div>
                
                <div className="estimate-row">
                  <span className="col-name">Кирпичная кладка стен</span>
                  <span className="col-unit">м³</span>
                  <span className="col-qty">87.2</span>
                  <span className="col-price">8 900 ₽</span>
                  <span className="col-total">776 080 ₽</span>
                </div>
                
                <div className="estimate-row">
                  <span className="col-name">Мягкая кровля</span>
                  <span className="col-unit">м²</span>
                  <span className="col-qty">125</span>
                  <span className="col-price">1 850 ₽</span>
                  <span className="col-total">231 250 ₽</span>
                </div>
                
                <div className="estimate-total">
                  <span className="total-label">Итого:</span>
                  <span className="total-value">1 465 130 ₽</span>
                </div>
                
                <div className="estimate-sources">
                  <span className="source-badge source-verified">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="20,6 9,17 4,12" />
                    </svg>
                    Цены проверены
                  </span>
                  <span className="source-badge source-note">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 16v-4M12 8h.01" />
                    </svg>
                    3 позиции требуют уточнения
                  </span>
                </div>
              </div>
              
              <button className="preview-action-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
                Открыть в редакторе
              </button>
            </div>
            
            <div className="preview-footer">
              <span className="version-badge">Версия 1.2</span>
              <span className="status-badge status-ready">Готово к редактированию</span>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

function HowItWorks() {
  const steps = [
    {
      num: "01",
      title: "Опишите объект",
      desc: "Введите параметры строительства или загрузите имеющиеся данные",
      example: "«Дом 109 м² в Альметьевске. Монолитная плита, кирпичные стены, мягкая кровля, инженерные сети и отделка»",
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
        </svg>
      ),
    },
    {
      num: "02",
      title: "Kolibri структурирует данные",
      desc: "AI анализирует описание и выделяет ключевые параметры для расчёта",
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14,2 14,8 20,8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
        </svg>
      ),
    },
    {
      num: "03",
      title: "Формирует смету",
      desc: "Система создаёт детализированную смету с работами и материалами",
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2v20M2 12h20" />
        </svg>
      ),
    },
    {
      num: "04",
      title: "Проверяет цены и допущения",
      desc: "Kolibri показывает источники цен и отмечает позиции, требующие подтверждения",
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
      ),
    },
    {
      num: "05",
      title: "Создаёт документы",
      desc: "На основе сметы генерируются коммерческое предложение, договор, акт и другие документы",
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14,2 14,8 20,8" />
        </svg>
      ),
    },
  ]

  return (
    <section id="how-it-works" className="section how-it-works">
      <div className="container">
        <div className="section-header">
          <h2 className="section-title">Как работает Kolibri</h2>
          <p className="section-subtitle">
            Единый поток от описания объекта до готового пакета документов
          </p>
        </div>

        <div className="steps-container">
          {steps.map((step, i) => (
            <motion.div 
              key={step.num}
              className="step-card"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              transition={{ duration: 0.4, delay: i * 0.1 }}
            >
              <div className="step-number">{step.num}</div>
              <div className="step-icon">{step.icon}</div>
              <h3 className="step-title">{step.title}</h3>
              <p className="step-desc">{step.desc}</p>
              {step.example && (
                <div className="step-example">
                  <span className="example-label">Пример запроса:</span>
                  <p>{step.example}</p>
                </div>
              )}
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

function EditorSection() {
  return (
    <section id="features" className="section editor-section">
      <div className="container">
        <div className="section-header">
          <h2 className="section-title">Редактор сметы</h2>
          <p className="section-subtitle">
            Полный контроль над расчётом с автоматическим пересчётом
          </p>
        </div>

        <div className="editor-grid">
          <div className="editor-content">
            <div className="feature-list">
              <div className="feature-item">
                <div className="feature-icon">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </div>
                <div className="feature-text">
                  <h4>Разделы и позиции</h4>
                  <p>Работы и материалы сгруппированы по разделам сметы</p>
                </div>
              </div>

              <div className="feature-item">
                <div className="feature-icon">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4 12.5-12.5z" />
                  </svg>
                </div>
                <div className="feature-text">
                  <h4>Редактирование</h4>
                  <p>Изменяйте объёмы, цены, единицы измерения — итог пересчитывается автоматически</p>
                </div>
              </div>

              <div className="feature-item">
                <div className="feature-icon">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  </svg>
                </div>
                <div className="feature-text">
                  <h4>Источники и проверка</h4>
                  <p>Kolibri отделяет факты от допущений и показывает источники данных</p>
                </div>
              </div>

              <div className="feature-item">
                <div className="feature-icon">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
                  </svg>
                </div>
                <div className="feature-text">
                  <h4>Версионность</h4>
                  <p>Сохраняйте версии сметы и возвращайтесь к предыдущим редакциям</p>
                </div>
              </div>
            </div>
          </div>

          <div className="editor-preview">
            <div className="editor-mockup">
              <div className="mockup-header">
                <span className="mockup-title">Смета №2024-001</span>
                <span className="mockup-status">Черновик</span>
              </div>
              
              <div className="mockup-table">
                <div className="mockup-row mockup-head">
                  <span>Раздел 1. Подготовительные работы</span>
                </div>
                <div className="mockup-row">
                  <span className="mockup-name">Подготовка основания</span>
                  <span className="mockup-unit">м²</span>
                  <span className="mockup-qty">109</span>
                  <span className="mockup-price">450 ₽</span>
                  <span className="mockup-total">49 050 ₽</span>
                </div>
                <div className="mockup-row">
                  <span className="mockup-name">Геодезическая разбивка</span>
                  <span className="mockup-unit">шт</span>
                  <span className="mockup-qty">1</span>
                  <span className="mockup-price">15 000 ₽</span>
                  <span className="mockup-total">15 000 ₽</span>
                </div>
                
                <div className="mockup-row mockup-head">
                  <span>Раздел 2. Фундамент</span>
                </div>
                <div className="mockup-row">
                  <span className="mockup-name">Монолитная плита</span>
                  <span className="mockup-unit">м³</span>
                  <span className="mockup-qty editable">32.7</span>
                  <span className="mockup-price editable">12 500 ₽</span>
                  <span className="mockup-total">408 750 ₽</span>
                </div>
                <div className="mockup-row">
                  <span className="mockup-name">Армирование</span>
                  <span className="mockup-unit">т</span>
                  <span className="mockup-qty">2.8</span>
                  <span className="mockup-price">65 000 ₽</span>
                  <span className="mockup-total">182 000 ₽</span>
                </div>
                
                <div className="mockup-total-row">
                  <span>Итого по смете:</span>
                  <span className="mockup-total-value">1 465 130 ₽</span>
                </div>
              </div>
              
              <div className="mockup-sources">
                <span className="source-tag verified">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="20,6 9,17 4,12" />
                  </svg>
                  Проверено
                </span>
                <span className="source-tag needs-review">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M12 8v4M12 16h.01" />
                  </svg>
                  Требует уточнения
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function SourcesSection() {
  return (
    <section className="section sources-section">
      <div className="container">
        <div className="section-header">
          <h2 className="section-title">Источники и проверяемость</h2>
          <p className="section-subtitle">
            Прозрачность данных — основа доверия к расчётам
          </p>
        </div>

        <div className="sources-grid">
          <div className="source-card">
            <div className="source-icon source-facts">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                <polyline points="14,2 14,8 20,8" />
              </svg>
            </div>
            <h3>Исходные факты</h3>
            <p>Данные из проектной документации и нормативных источников</p>
          </div>

          <div className="source-card">
            <div className="source-icon source-user">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </div>
            <h3>Пользовательские данные</h3>
            <p>Параметры, которые вы указали при описании объекта</p>
          </div>

          <div className="source-card">
            <div className="source-icon source-norms">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </div>
            <h3>Нормативные основания</h3>
            <p>Ссылки на СНиП, ГОСТ, ФЕР, ТЕР и другие нормативы</p>
          </div>

          <div className="source-card">
            <div className="source-icon source-market">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2v20M2 12h20" />
              </svg>
            </div>
            <h3>Рыночные цены</h3>
            <p>Актуальные цены поставщиков и подрядчиков в вашем регионе</p>
          </div>

          <div className="source-card">
            <div className="source-icon source-assumptions">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 16v-4M12 8h.01" />
              </svg>
            </div>
            <h3>Допущения</h3>
            <p>Явно обозначенные предположения там, где данных недостаточно</p>
          </div>

          <div className="source-card">
            <div className="source-icon source-review">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </div>
            <h3>Требует подтверждения</h3>
            <p>Позиции, которые необходимо проверить перед использованием</p>
          </div>
        </div>
      </div>
    </section>
  )
}

function DocumentsSection() {
  const documents = [
    { name: "Смета", format: "PDF/XLSX", icon: "📊" },
    { name: "Коммерческое предложение", format: "PDF/DOCX", icon: "📄" },
    { name: "Счёт", format: "PDF", icon: "🧾" },
    { name: "Договор", format: "DOCX", icon: "📝" },
    { name: "Акт выполненных работ", format: "PDF/DOCX", icon: "✅" },
    { name: "КС-2", format: "XLSX", icon: "📋" },
    { name: "КС-3", format: "XLSX", icon: "📈" },
  ]

  return (
    <section id="documents" className="section documents-section">
      <div className="container">
        <div className="section-header">
          <h2 className="section-title">Документы</h2>
          <p className="section-subtitle">
            Единое пространство связанных строительных документов
          </p>
        </div>

        <div className="documents-grid">
          {documents.map((doc, i) => (
            <motion.div 
              key={doc.name}
              className="document-card"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
            >
              <div className="doc-icon">{doc.icon}</div>
              <h3 className="doc-name">{doc.name}</h3>
              <span className="doc-format">{doc.format}</span>
            </motion.div>
          ))}
        </div>

        <div className="documents-preview">
          <div className="preview-doc">
            <div className="preview-doc-header">
              <span className="preview-doc-title">Коммерческое предложение №2024-001</span>
              <span className="preview-doc-date">от 15 января 2024</span>
            </div>
            <div className="preview-doc-body">
              <p><strong>Заказчик:</strong> Иванов И.И.</p>
              <p><strong>Объект:</strong> Строительство жилого дома 109 м²</p>
              <p><strong>Адрес:</strong> г. Альметьевск, ул. Примерная, д. 1</p>
              <div className="preview-doc-table">
                <div className="preview-doc-row">
                  <span>Подготовительные работы</span>
                  <span>64 050 ₽</span>
                </div>
                <div className="preview-doc-row">
                  <span>Фундамент</span>
                  <span>590 750 ₽</span>
                </div>
                <div className="preview-doc-row">
                  <span>Стены</span>
                  <span>776 080 ₽</span>
                </div>
                <div className="preview-doc-row preview-doc-total">
                  <span>Итого:</span>
                  <span>1 465 130 ₽</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function ForWhomSection() {
  const segments = [
    {
      title: "Строительные подрядчики",
      desc: "Быстрая подготовка смет и коммерческих предложений для тендеров",
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 21h18M5 21V7l8-4 8 4v14M8 21v-4a2 2 0 012-2h4a2 2 0 012 2v4" />
        </svg>
      ),
    },
    {
      title: "Сметчики",
      desc: "Автоматизация рутинных расчётов и проверка актуальности цен",
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
          <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
        </svg>
      ),
    },
    {
      title: "Ремонтные бригады",
      desc: "Прозрачные расчёты для клиентов и упрощение документооборота",
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" />
        </svg>
      ),
    },
    {
      title: "Индивидуальные предприниматели",
      desc: "Профессиональные документы без необходимости нанимать сметчика",
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
          <path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16" />
        </svg>
      ),
    },
    {
      title: "Заказчики и технические специалисты",
      desc: "Контроль обоснованности смет и проверка исполнителей",
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
      ),
    },
  ]

  return (
    <section id="for-whom" className="section for-whom-section">
      <div className="container">
        <div className="section-header">
          <h2 className="section-title">Для кого</h2>
          <p className="section-subtitle">
            Kolibri помогает всем участникам строительного процесса
          </p>
        </div>

        <div className="segments-grid">
          {segments.map((segment, i) => (
            <motion.div 
              key={segment.title}
              className="segment-card"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.3, delay: i * 0.08 }}
            >
              <div className="segment-icon">{segment.icon}</div>
              <h3 className="segment-title">{segment.title}</h3>
              <p className="segment-desc">{segment.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

function WorkspaceSection() {
  return (
    <section className="section workspace-section">
      <div className="container">
        <div className="section-header">
          <h2 className="section-title">Рабочее пространство</h2>
          <p className="section-subtitle">
            Всё необходимое для строительных расчётов в одном месте
          </p>
        </div>

        <div className="workspace-grid">
          <div className="workspace-item">
            <div className="workspace-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
              </svg>
            </div>
            <h3>Чат</h3>
            <p>Диалог с AI для уточнения параметров и получения рекомендаций</p>
          </div>

          <div className="workspace-item">
            <div className="workspace-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
              </svg>
            </div>
            <h3>Проекты</h3>
            <p>Организация объектов и связанных с ними документов</p>
          </div>

          <div className="workspace-item">
            <div className="workspace-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2v20M2 12h20" />
              </svg>
            </div>
            <h3>Сметы</h3>
            <p>Детализированные расчёты с работами и материалами</p>
          </div>

          <div className="workspace-item">
            <div className="workspace-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              </svg>
            </div>
            <h3>Документы</h3>
            <p>Коммерческие предложения, договоры, акты и формы КС</p>
          </div>

          <div className="workspace-item">
            <div className="workspace-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
              </svg>
            </div>
            <h3>Справочники</h3>
            <p>Нормативные базы, прайсы поставщиков и шаблоны документов</p>
          </div>

          <div className="workspace-item">
            <div className="workspace-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3>Версии</h3>
            <p>История изменений и возможность отката к предыдущим редакциям</p>
          </div>
        </div>
      </div>
    </section>
  )
}

function CTASection() {
  return (
    <section className="section cta-section">
      <div className="container">
        <div className="cta-card">
          <h2 className="cta-title">
            Опишите объект — Kolibri подготовит структуру сметы и покажет, какие данные требуется уточнить
          </h2>
          <div className="cta-buttons">
            <a href="/app" className="btn btn-primary btn-lg">Создать смету</a>
            <a href="/app" className="btn btn-ghost btn-lg">Открыть приложение</a>
          </div>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="landing-footer">
      <div className="container">
        <div className="footer-grid">
          <div className="footer-brand">
            <a href="/" className="footer-logo">
              <KolibriBird size={28} state="idle" />
              <span className="footer-logo-text">Kolibri</span>
            </a>
            <p className="footer-desc">
              AI-рабочее пространство для строительных расчётов и документов
            </p>
          </div>

          <div className="footer-links">
            <h4>Продукт</h4>
            <a href="#features">Возможности</a>
            <a href="#how-it-works">Как работает</a>
            <a href="#documents">Документы</a>
          </div>

          <div className="footer-links">
            <h4>Документы</h4>
            <a href="/privacy">Политика конфиденциальности</a>
            <a href="/terms">Условия использования</a>
          </div>

          <div className="footer-contact">
            <h4>Контакты</h4>
            <a href="mailto:support@kolibriai.ru">support@kolibriai.ru</a>
          </div>
        </div>

        <div className="footer-bottom">
          <p>© {currentYear} Kolibri AI. Все права защищены.</p>
        </div>
      </div>
    </footer>
  )
}

export default function Landing() {
  useEffect(() => {
    document.title = "Kolibri — Смета и строительные документы из одного описания"
    
    const metaDescription = document.querySelector('meta[name="description"]')
    if (metaDescription) {
      metaDescription.setAttribute("content", "Kolibri — AI-рабочее пространство для строительных расчётов. Создавайте сметы, проверяйте цены, формируйте документы из одного описания объекта.")
    }

    return () => {
      document.title = "Kolibri AI"
    }
  }, [])

  return (
    <div className="landing-page">
      <Header />
      <main>
        <Hero />
        <HowItWorks />
        <EditorSection />
        <SourcesSection />
        <DocumentsSection />
        <ForWhomSection />
        <WorkspaceSection />
        <CTASection />
      </main>
      <Footer />
    </div>
  )
}
