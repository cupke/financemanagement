  import { Routes, Route, Navigate } from 'react-router-dom'

  import { LoginPage } from './pages/LoginPage'
  import { RegisterPage } from './pages/RegisterPage'
  import { MePage } from './pages/MePage'
  import { AccountsPage } from './pages/AccountsPage'
  import { CategoriesPage } from './pages/CategoriesPage'
  import { ProtectedRoute } from './components/ProtectedRoute'
  import { AppLayout } from './components/AppLayout'

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
            <Route path="/categories" element={<CategoriesPage />} />
            <Route path="/me" element={<MePage />} />
          </Route>
        </Route>

        {/* Корень → главный экран */}
        <Route path="/" element={<Navigate to="/accounts" replace />} />
        <Route path="*" element={<Navigate to="/accounts" replace />} />
      </Routes>
    )
  }