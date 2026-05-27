  import { Routes, Route, Navigate } from 'react-router-dom'

  import { LoginPage } from './pages/LoginPage'
  import { RegisterPage } from './pages/RegisterPage'
  import { MePage } from './pages/MePage'
  import { AccountsPage } from './pages/AccountsPage'
  import { CategoriesPage } from './pages/CategoriesPage'
  import { RatesPage } from './pages/RatesPage'
  import { TransactionsPage } from './pages/TransactionsPage'
  import { ProtectedRoute } from './components/ProtectedRoute'
  import { AppLayout } from './components/AppLayout'
  import { BudgetsPage } from './pages/BudgetsPage'
  import { DashboardPage } from './pages/DashboardPage'

  // Корневой компонент приложения — задаёт карту маршрутов.
  // React Router сопоставляет URL в адресной строке с одним из <Route> и рендерит его element.
  //
  // Структура:
  // - Публичные роуты (/login, /register) — без layout, open для всех.
  // - Защищённая группа: ProtectedRoute проверяет токен, AppLayout даёт sidebar+header.
  //   Дочерние роуты (/accounts, /me) рендерятся в <Outlet /> AppLayout.
  // - Корневой /  → редирект на /accounts (главный экран после логина).
  export default function App() {
    return (
      <Routes>
        {/* Публичные страницы */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Защищённая группа: токен проверяется один раз на уровне ProtectedRoute,
            AppLayout даёт sidebar+header, дочерние роуты подставляются через Outlet. */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/accounts" element={<AccountsPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/categories" element={<CategoriesPage />} />
            <Route path="/budgets" element={<BudgetsPage />} />
            <Route path="/rates" element={<RatesPage />} />
            <Route path="/me" element={<MePage />} />
            <Route path="/" element={<DashboardPage />} />
          </Route>
        </Route>

        {/* Корень → главный экран */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    )
  }