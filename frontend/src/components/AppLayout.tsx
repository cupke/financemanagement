  import { Link, NavLink as RouterNavLink, Outlet, useNavigate } from 'react-router-dom'
  import {
    AppShell,
    Burger,
    Group,
    NavLink,
    Stack,
    Text,
    Title,
    UnstyledButton,
  } from '@mantine/core'
  import { useDisclosure } from '@mantine/hooks'
  import { notifications } from '@mantine/notifications'

  import { useAuthStore } from '../stores/auth'

  // Главный layout для авторизованных пользователей: header сверху + sidebar слева
  // + основной контент через <Outlet />. На мобильных sidebar сворачивается в
  // бургер-меню (breakpoint sm = 768px).
  export function AppLayout() {
    const navigate = useNavigate()
    const clearToken = useAuthStore((state) => state.clearToken)
    // useDisclosure — Mantine-хук для пары {opened, toggle/close/open}. Здесь
    // управляет видимостью sidebar на мобильных.
    const [opened, { toggle, close }] = useDisclosure()

    const handleLogout = () => {
      clearToken()
      notifications.show({
        title: 'Выход',
        message: 'Вы вышли из аккаунта',
        color: 'blue',
      })
      navigate('/login')
    }

    // Пункты sidebar — массив, чтобы добавлять новые (категории, история) одной строкой.
    const navItems = [
      { to: '/accounts', label: 'Счета', icon: '🏦' },
      { to: '/categories', label: 'Категории', icon: '📂' },
      { to: '/me', label: 'Профиль', icon: '👤' },
    ]

    return (
      <AppShell
        header={{ height: 60 }}
        navbar={{
          width: 220,
          breakpoint: 'sm',
          // collapsed — на мобильных sidebar скрыт по умолчанию, открывается бургером.
          collapsed: { mobile: !opened },
        }}
        padding="md"
      >
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between">
            <Group>
              {/* Burger виден только на мобильных (hiddenFrom='sm') */}
              <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
              <UnstyledButton component={Link} to="/accounts">
                <Title order={3}>FinTrack</Title>
              </UnstyledButton>
            </Group>
            <Text size="sm" c="dimmed">
              Личные финансы
            </Text>
          </Group>
        </AppShell.Header>

        <AppShell.Navbar p="md">
          <Stack justify="space-between" h="100%">
            <Stack gap="xs">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  component={RouterNavLink}
                  to={item.to}
                  label={item.label}
                  leftSection={<Text>{item.icon}</Text>}
                  onClick={close}
                />
              ))}
            </Stack>

            <NavLink
              label="Выйти"
              leftSection={<Text>🚪</Text>}
              onClick={handleLogout}
              color="red"
            />
          </Stack>
        </AppShell.Navbar>

        <AppShell.Main>
          {/* Outlet — точка вставки дочерних роутов (см. App.tsx) */}
          <Outlet />
        </AppShell.Main>
      </AppShell>
    )
  }