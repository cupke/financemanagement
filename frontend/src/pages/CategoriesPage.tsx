  import { useState } from 'react'
  import {
    ActionIcon,
    Button,
    Card,
    Container,
    Group,
    Loader,
    Stack,
    Text,
    Title,
  } from '@mantine/core'
  import { modals } from '@mantine/modals'
  import { notifications } from '@mantine/notifications'
  import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

  import {
    deleteCategoryRequest,
    listCategoriesRequest,
    type CategoryRead,
  } from '../api/categories'
  import { CategoryFormModal } from '../components/CategoryFormModal'

  // Каждый уровень вложенности = 24px отступа слева. На больших глубинах
  // (> 6 уровней) отступы будут уезжать — это разумное ограничение для UX.
  const INDENT_PX = 24

  // Ширина «слота» стрелки/спейсера — фиксированная, чтобы названия категорий
  // без детей выравнивались по тем же координатам, что и с детьми.
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

  // Рекурсивный компонент строки. Карточка категории + стрелка expand/collapse
  // слева (если есть дети) + дети рендерятся только при isExpanded.
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
                  {/* ▶ / ▼ — unicode-стрелки. Чище любого эмодзи и не требуют
                      отдельной библиотеки иконок. */}
                  <Text size="xs">{isExpanded ? '▼' : '▶'}</Text>
                </ActionIcon>
              ) : (
                // Спейсер той же ширины — чтобы названия категорий без детей
                // не выравнивались по другой оси, чем с детьми.
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
        {/* Дети рендерятся только если родитель развёрнут. */}
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

  export function CategoriesPage() {
    const [modalOpened, setModalOpened] = useState(false)
    // Set развёрнутых категорий по id. По умолчанию пустой — все свёрнуты.
    const [expanded, setExpanded] = useState<Set<number>>(new Set())
    const queryClient = useQueryClient()

    const { data: categories, isLoading, isError } = useQuery({
      queryKey: ['categories'],
      queryFn: listCategoriesRequest,
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

    // Toggle развёрнутости отдельной категории. Immutable обновление Set —
    // создаём новый, чтобы React заметил изменение.
    const toggleExpand = (id: number) => {
      setExpanded((prev) => {
        const next = new Set(prev)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      })
    }

    // После создания новой категории автоматически разворачиваем её родителя
    // и всех вышестоящих предков. Иначе пользователь создаст «Хлеб» в свёрнутых
    // «Продукты» в «Расходы» — и не увидит результат.
    const handleCategoryCreated = (newCat: CategoryRead) => {
      if (newCat.parent_id === null) return // корневая — нет предков для разворота
      if (!categories) return

      const ancestorsToExpand = new Set<number>()
      let currentParentId: number | null = newCat.parent_id
      while (currentParentId !== null) {
        ancestorsToExpand.add(currentParentId)
        const parent = categories.find((c) => c.id === currentParentId)
        currentParentId = parent?.parent_id ?? null
      }

      setExpanded((prev) => new Set([...prev, ...ancestorsToExpand]))
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

    const childrenMap = groupByParent(categories)
    const roots = childrenMap.get(null) ?? []

    return (
      <Container size="md" py="xl">
        <Group justify="space-between" mb="lg">
          <Title order={2}>Категории</Title>
          <Button onClick={() => setModalOpened(true)}>
            + Добавить категорию
          </Button>
        </Group>

        {categories.length === 0 ? (
          <Card withBorder p="xl">
            <Stack align="center" gap="xs">
              <Text c="dimmed">У вас пока нет категорий.</Text>
              <Button variant="light" onClick={() => setModalOpened(true)}>
                Создать первую категорию
              </Button>
            </Stack>
          </Card>
        ) : (
          <Stack gap="xs">
            {roots.map((root) => (
              <CategoryRow
                key={root.id}
                category={root}
                depth={0}
                childrenMap={childrenMap}
                expanded={expanded}
                onToggle={toggleExpand}
                onDelete={handleDelete}
                deletingId={deleteMutation.variables}
              />
            ))}
          </Stack>
        )}

        <CategoryFormModal
          opened={modalOpened}
          onClose={() => setModalOpened(false)}
          onCreated={handleCategoryCreated}
        />
      </Container>
    )
  }