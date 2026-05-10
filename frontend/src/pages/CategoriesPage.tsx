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

  // Строит карту parentId → отсортированный по id массив прямых детей.
  // Из неё рекурсивно рендерится дерево.
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
    onDelete: (cat: CategoryRead) => void
    deletingId: number | undefined
  }

  // Рекурсивный компонент строки. Рендерит карточку категории + детей через
  // тот же CategoryRow с depth+1.
  function CategoryRow({
    category,
    depth,
    childrenMap,
    onDelete,
    deletingId,
  }: RowProps) {
    const children = childrenMap.get(category.id) ?? []
    return (
      <>
        <Card
          withBorder
          p="sm"
          // marginLeft через style — Mantine ml ожидает числовые отступы
          // из своей шкалы (xs/sm/md/...), произвольное значение проще через style.
          style={{ marginLeft: depth * INDENT_PX }}
        >
          <Group justify="space-between" wrap="nowrap">
            <Stack gap={2}>
              <Text fw={500}>{category.name}</Text>
              <Text size="xs" c="dimmed">
                ID #{category.id}
                {category.parent_id !== null &&
                  ` · родитель #${category.parent_id}`}
              </Text>
            </Stack>
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
        {children.map((child) => (
          <CategoryRow
            key={child.id}
            category={child}
            depth={depth + 1}
            childrenMap={childrenMap}
            onDelete={onDelete}
            deletingId={deletingId}
          />
        ))}
      </>
    )
  }

  export function CategoriesPage() {
    const [modalOpened, setModalOpened] = useState(false)
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
          <Button onClick={() => setModalOpened(true)}>+ Добавить категорию</Button>
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
                onDelete={handleDelete}
                deletingId={deleteMutation.variables}
              />
            ))}
          </Stack>
        )}

        <CategoryFormModal
          opened={modalOpened}
          onClose={() => setModalOpened(false)}
        />
      </Container>
    )
  }