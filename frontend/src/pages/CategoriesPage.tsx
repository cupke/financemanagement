    import { useState } from 'react'
    import {
      ActionIcon,
      Badge,
      Button,
      Card,
      Container,
      Group,
      Loader,
      Stack,
      Tabs,
      Text,
      Title,
    } from '@mantine/core'
    import { modals } from '@mantine/modals'
    import { notifications } from '@mantine/notifications'
    import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

    import {
      deleteCategoryRequest,
      listCategoriesRequest,
      type CategoryKind,
      type CategoryRead,
    } from '../api/categories'
    import { CategoryFormModal } from '../components/CategoryFormModal'
    import { useDocumentTitle } from '../lib/useDocumentTitle'
  
    // Каждый уровень вложенности = 24px отступа слева.
    const INDENT_PX = 24
    // Ширина слота для стрелки expand/collapse — постоянная для выравнивания.
    const TOGGLE_WIDTH = 26
  
    // Строит карту parentId → отсортированный по id массив прямых детей.
    function groupByParent(
      categories: CategoryRead[],
    ): Map<number | null, CategoryRead[]> {
      const map = new Map<number | null, CategoryRead[]>()
      for (const cat of categories) {
        const arr = map.get(cat.parent_id) ?? []
        arr.push(cat)
        map.set(cat.parent_id, arr)
      }
      for (const arr of map.values()) {
        arr.sort((a, b) => a.id - b.id)
      }
      return map
    }
  
    interface RowProps {
      category: CategoryRead
      depth: number
      childrenMap: Map<number | null, CategoryRead[]>
      expanded: Set<number>
      onToggle: (id: number) => void
      onDelete: (cat: CategoryRead) => void
      deletingId: number | undefined
    }
  
    function CategoryRow({
      category,
      depth,
      childrenMap,
      expanded,
      onToggle,
      onDelete,
      deletingId,
    }: RowProps) {
      const children = childrenMap.get(category.id) ?? []
      const hasChildren = children.length > 0
      const isExpanded = expanded.has(category.id)
  
      return (
        <>
          <Card
            withBorder
            p="sm"
            style={{ marginLeft: depth * INDENT_PX }}
          >
            <Group justify="space-between" wrap="nowrap">
              <Group gap="xs" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                {hasChildren ? (
                  <ActionIcon
                    variant="subtle"
                    size="sm"
                    aria-label={isExpanded ? 'Свернуть' : 'Развернуть'}
                    onClick={() => onToggle(category.id)}
                  >
                    <Text size="xs">{isExpanded ? '▼' : '▶'}</Text>
                  </ActionIcon>
                ) : (
                  <div style={{ width: TOGGLE_WIDTH, flexShrink: 0 }} />
                )}
                <Text fw={500} truncate>
                  {category.name}
                </Text>
              </Group>
              <ActionIcon
                variant="subtle"
                color="red"
                aria-label="Удалить категорию"
                onClick={() => onDelete(category)}
                loading={deletingId === category.id}
              >
                🗑️ 
              </ActionIcon>
            </Group>
          </Card>
          {isExpanded &&
            children.map((child) => (
              <CategoryRow
                key={child.id}
                category={child}
                depth={depth + 1}
                childrenMap={childrenMap}
                expanded={expanded}
                onToggle={onToggle}
                onDelete={onDelete}
                deletingId={deletingId}
              />
            ))}
        </>
      )
    }

    // Дерево категорий одного типа (expense или income). Используется внутри
    // каждой вкладки. Если категорий нет — показывает «empty state» с кнопкой
    // создания первой категории нужного типа.
    interface TreeProps {
      kind: CategoryKind
      categories: CategoryRead[]
      onAdd: () => void
      onDelete: (cat: CategoryRead) => void
      deletingId: number | undefined
    }
  
    function CategoryTree({
      kind,
      categories,
      onAdd,
      onDelete,
      deletingId,
    }: TreeProps) {
      const [expanded, setExpanded] = useState<Set<number>>(new Set())

      const toggleExpand = (id: number) => {
        setExpanded((prev) => {
          const next = new Set(prev)
          if (next.has(id)) next.delete(id)
          else next.add(id)
          return next
        })
      }
  
      if (categories.length === 0) {
        return (
          <Card withBorder p="xl">
            <Stack align="center" gap="xs">
              <Text c="dimmed">
                {kind === 'expense'
                  ? 'У вас пока нет расходных категорий.'
                  : 'У вас пока нет доходных категорий.'}
              </Text>
              <Button variant="light" onClick={onAdd}>
                Создать первую категорию
              </Button>
            </Stack>
          </Card>
        )
      }
  
      const childrenMap = groupByParent(categories)
      const roots = childrenMap.get(null) ?? []
  
      return (
        <Stack gap="xs">
          {roots.map((root) => (
            <CategoryRow
              key={root.id}
              category={root}
              depth={0}
              childrenMap={childrenMap}
              expanded={expanded}
              onToggle={toggleExpand}
              onDelete={onDelete}
              deletingId={deletingId}
            />
          ))}
        </Stack>
      )
    }

    export function CategoriesPage() {
      useDocumentTitle('Категории')
      const [modalOpened, setModalOpened] = useState(false)
      // Текущая вкладка — определяет, с каким kind открывается форма создания.
      const [activeKind, setActiveKind] = useState<CategoryKind>('expense')
      const queryClient = useQueryClient()

      const { data: categories, isLoading, isError } = useQuery({
        queryKey: ['categories'],
        queryFn: () => listCategoriesRequest(),
      })

      const deleteMutation = useMutation({
        mutationFn: (id: number) => deleteCategoryRequest(id),
        onSuccess: () => {
          notifications.show({
            title: 'Категория удалена',
            message: 'Все вложенные категории также удалены каскадно',
            color: 'blue',
          })
          queryClient.invalidateQueries({ queryKey: ['categories'] })
        },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        onError: (error: any) => {
          notifications.show({
            title: 'Ошибка',
            message: error.response?.data?.detail || 'Не удалось удалить категорию',
            color: 'red',
          })
        },
      })
  
      const handleDelete = (category: CategoryRead) => {
        modals.openConfirmModal({
          title: 'Удалить категорию?',
          centered: true,
          children: (
            <Text size="sm">
              Удалить категорию «<strong>{category.name}</strong>»? Все вложенные
              подкатегории (если есть) тоже будут удалены. Это действие необратимо.
            </Text>
          ),
          labels: { confirm: 'Удалить', cancel: 'Отмена' },
          confirmProps: { color: 'red' },
          onConfirm: () => deleteMutation.mutate(category.id),
        })
      }

      if (isLoading) {
        return (
          <Container py="xl">
            <Loader />
          </Container>
        )
      }

      if (isError || !categories) {
        return (
          <Container py="xl">
            <Text c="red">Не удалось загрузить категории.</Text>
          </Container>
        )
      }

      // Фильтрация по kind происходит на клиенте — все категории уже в кеше
      // одного запроса GET /categories. Бэкенд тоже поддерживает ?kind=...,
      // но локальная фильтрация даёт мгновенное переключение вкладок без сети.
      const expenseCategories = categories.filter((c) => c.kind === 'expense')
      const incomeCategories = categories.filter((c) => c.kind === 'income')
  
      return (
        <Container size="md" py="xl">
          <Group justify="space-between" mb="lg">
            <Title order={2}>Категории</Title>
            <Button onClick={() => setModalOpened(true)}>
              + Добавить категорию
            </Button>
          </Group>

          <Tabs
            value={activeKind}
            onChange={(v) => v && setActiveKind(v as CategoryKind)}
            // variant="pills" — округлые «таблетки» вместо тонкой линии снизу.
            // Растягиваем через style={{ flex: 1 }} на каждой вкладке —
            // встроенный prop grow с pills работает нестабильно.
            variant="pills"
          >
            <Tabs.List mb="md" style={{ gap: 8 }}>
              <Tabs.Tab
                value="expense"
                style={{ flex: 1, minHeight: 56, padding: '8px 16px' }}
              >
                <Group gap="xs" wrap="nowrap" justify="center">
                  <Text size="lg">💸</Text>
                  <Text fw={500}>Расходы</Text>
                  <Badge
                    variant={activeKind === 'expense' ? 'white' : 'light'}
                    color={activeKind === 'expense' ? 'blue' : 'gray'}
                    size="sm"
                  >
                    {expenseCategories.length}
                  </Badge>
                </Group>
              </Tabs.Tab>
              <Tabs.Tab
                value="income"
                style={{ flex: 1, minHeight: 56, padding: '8px 16px' }}
              >
                <Group gap="xs" wrap="nowrap" justify="center">
                  <Text size="lg">💰</Text>
                  <Text fw={500}>Доходы</Text>
                  <Badge
                    variant={activeKind === 'income' ? 'white' : 'light'}
                    color={activeKind === 'income' ? 'blue' : 'gray'}
                    size="sm"
                  >
                    {incomeCategories.length}
                  </Badge>
                </Group>
              </Tabs.Tab>
            </Tabs.List>
  
            <Tabs.Panel value="expense">
              <CategoryTree
                kind="expense"
                categories={expenseCategories}
                onAdd={() => setModalOpened(true)}
                onDelete={handleDelete}
                deletingId={deleteMutation.variables}
              />
            </Tabs.Panel>

            <Tabs.Panel value="income">
              <CategoryTree
                kind="income"
                categories={incomeCategories}
                onAdd={() => setModalOpened(true)}
                onDelete={handleDelete}
                deletingId={deleteMutation.variables}
              />
            </Tabs.Panel>
          </Tabs>

          <CategoryFormModal
            opened={modalOpened}
            onClose={() => setModalOpened(false)}
            initialKind={activeKind}
          />
        </Container>
      )
    }