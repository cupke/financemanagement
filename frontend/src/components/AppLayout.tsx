  import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
  import {
    ActionIcon,
    AppShell,
    Burger,
    Group,
    NavLink,
    Stack,
    Text,
    Title,
    Tooltip,
    UnstyledButton,
    useMantineColorScheme,
  } from '@mantine/core'
  import { useDisclosure } from '@mantine/hooks'
  import { notifications } from '@mantine/notifications'
  import { useQuery } from '@tanstack/react-query'

  import { getMeRequest } from '../api/auth'
  import { useAuthStore } from '../stores/auth'

  // Главный layout для авторизованных пользователей: header сверху + sidebar слева
  // + основной контент через <Outlet />. На мобильных sidebar сворачивается в
  // бургер-меню (breakpoint sm = 768px).
  export function AppLayout() {
    const navigate = useNavigate()
    // useLocation даёт текущий URL — нужен для подсветки активного пункта sidebar.
    const location = useLocation()
    const clearToken = useAuthStore((state) => state.clearToken)
    // useDisclosure — Mantine-хук для пары {opened, toggle/close/open}. Здесь
    // управляет видимостью sidebar на мобильных.
    const [opened, { toggle, close }] = useDisclosure()
    // Mantine сам хранит выбор темы в localStorage и применяет на каждой загрузке.
    const { colorScheme, toggleColorScheme } = useMantineColorScheme()

    // Email текущего юзера — показываем в правой части header. queryKey совпадает
    // с тем, что использует /me и axios-интерсептор; данные кешированы.
    const { data: user } = useQuery({
      queryKey: ['me'],
      queryFn: getMeRequest,
    })

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
      { to: '/', label: 'Главная', icon: '📊' },
      { to: '/accounts', label: 'Счета', icon: '🏦' },
      { to: '/transactions', label: 'История', icon: '📝' },
      { to: '/categories', label: 'Категории', icon: '📂' },
      { to: '/budgets', label: 'Бюджеты', icon: '💰' },
      { to: '/rates', label: 'Курсы валют', icon: '💱' },
      { to: '/me', label: 'Профиль', icon: '👤' },
    ]

    // Проверка «активен ли пункт»: совпадает с текущим путём или это его
    // префикс (для будущих детальных страниц вроде /accounts/123 — корневой
    // пункт «Счета» останется подсвеченным).
    function isActive(itemPath: string): boolean {
      return (
        location.pathname === itemPath ||
        location.pathname.startsWith(itemPath + '/')
      )
    }

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
            {/* Email юзера в header — показывает, в чьём аккаунте сидишь.
                Пока useQuery загружается — пусто, не дёргаемся placeholder'ом. */}
            <Group gap="sm">
              {user && (
                <Text size="sm" c="dimmed" truncate>
                  {user.email}
                </Text>
              )}
              <Tooltip
                label={colorScheme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
              >
                <ActionIcon
                  variant="default"
                  onClick={toggleColorScheme}
                  aria-label="Переключить тему"
                >
                  {colorScheme === 'dark' ? '☀️' : '🌙'}
                </ActionIcon>
              </Tooltip>
            </Group>
          </Group>
        </AppShell.Header>

        <AppShell.Navbar p="md">
          <Stack justify="space-between" h="100%">
            <Stack gap="xs">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  component={Link}
                  to={item.to}
                  label={item.label}
                  leftSection={<Text>{item.icon}</Text>}
                  onClick={close}
                  // active — подсветка текущего пункта sidebar. Без неё пользователь
                  // не понимает по визуалу, на какой странице сейчас находится.
                  active={isActive(item.to)}
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