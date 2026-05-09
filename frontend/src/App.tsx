import { Routes, Route, Navigate } from 'react-router-dom'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { MePage } from './pages/MePage'
import { ProtectedRoute } from './components/ProtectedRoute'

// Корневой компонент приложения — задаёт карту маршрутов.
// React Router сопоставляет URL в адресной строке с одним из <Route> и рендерит его element.
export default function App() {
  return (
    <Routes>
      {/* Публичные страницы — доступны без авторизации. */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Защищённая страница — обёртка ProtectedRoute проверит наличие токена,
          и если его нет — перебросит на /login. На текущем шаге обёртка ещё не умеет
          проверять токен (это сделаем на следующем шаге), поэтому пока пускает всех. */}
      <Route
        path="/me"
        element={
          <ProtectedRoute>
            <MePage />
          </ProtectedRoute>
        }
      />

      {/* Корень / — редирект на /me. Если токена нет, ProtectedRoute дальше перебросит на /login. */}
      <Route path="/" element={<Navigate to="/me" replace />} />

      {/* Любой неизвестный URL — тоже редирект на /me (потом, при желании, заменим на 404-страницу). */}
      <Route path="*" element={<Navigate to="/me" replace />} />
    </Routes>
  )
}
